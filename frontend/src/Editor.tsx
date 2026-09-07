import { useEffect, useRef } from "react";
import * as monaco from "monaco-editor/editor/editor.api.js";
import "monaco-editor/languages/definitions/python/register.js";
import EditorWorker from "monaco-editor/editor/editor.worker.js?worker";

(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

export default function Editor({
  value,
  onChange,
}: {
  value: string;
  onChange: (text: string) => void;
}) {
  const element = useRef<HTMLDivElement>(null);
  const instance = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const updating = useRef(false);
  const change = useRef(onChange);
  change.current = onChange;
  useEffect(() => {
    monaco.editor.defineTheme("practice", {
      base: "vs-dark",
      inherit: true,
      rules: [],
      colors: {
        "editor.background": "#20232b",
        "editorLineNumber.foreground": "#727583",
        "editor.foreground": "#e1e3ed",
      },
    });
    const editor = monaco.editor.create(element.current!, {
      value,
      language: "python",
      theme: "practice",
      fontSize: 14,
      fontFamily: "Cascadia Code, Consolas, monospace",
      lineHeight: 24,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      automaticLayout: true,
      tabSize: 4,
      padding: { top: 18, bottom: 20 },
      wordWrap: "on",
      ariaLabel: "Python solution editor",
      quickSuggestions: false,
      suggestOnTriggerCharacters: false,
    });
    instance.current = editor;
    const listener = editor.onDidChangeModelContent(() => {
      if (!updating.current) change.current(editor.getValue());
    });
    return () => {
      listener.dispose();
      editor.getModel()?.dispose();
      editor.dispose();
      instance.current = null;
    };
  }, []);
  useEffect(() => {
    const editor = instance.current;
    if (editor && editor.getValue() !== value) {
      const position = editor.getPosition();
      updating.current = true;
      editor.setValue(value);
      updating.current = false;
      if (position) editor.setPosition(position);
    }
  }, [value]);
  return <div className="editor" ref={element} />;
}
