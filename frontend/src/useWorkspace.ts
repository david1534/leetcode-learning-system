import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { readStored, storeDraft } from "./persistence";
import type { CoachStatus, Progress, Queue, StudyState } from "./types";

export function useWorkspace(minutes: number, includeNew: boolean) {
  const [state, setState] = useState<StudyState | null>(null);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [coach, setCoach] = useState<CoachStatus | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [saveStatus, setSaveStatus] = useState("Saved locally");
  const [conflict, setConflict] = useState(false);
  const [storageError, setStorageError] = useState(false);
  const latest = useRef<StudyState | null>(null);
  const text = useRef("");
  const dirty = useRef(false);
  const activeId = useRef("");
  const base = useRef({ revision: 0, digest: "" });
  const saving = useRef<Promise<void> | null>(null);
  const conflictRef = useRef(false);
  const apply = (next: StudyState) => {
    const s = next.session;
    const previous = latest.current?.session;
    if (
      s &&
      previous?.session_id === s.session_id &&
      s.revision < previous.revision
    )
      return;
    latest.current = next;
    setState(next);
    if (!s || s.code === null) return;
    if (activeId.current !== s.session_id) {
      activeId.current = s.session_id;
      const saved = readStored<{ code: string; digest: string } | null>(
        "code-" + s.session_id,
        null,
      );
      dirty.current = Boolean(saved && saved.code !== s.code);
      text.current = dirty.current ? saved!.code : s.code;
      base.current = {
        revision: s.revision,
        digest: dirty.current ? saved!.digest : s.code_digest,
      };
      conflictRef.current =
        dirty.current && base.current.digest !== s.code_digest;
      setConflict(conflictRef.current);
      setDraft(text.current);
      setSaveStatus(
        dirty.current ? "Recovered browser draft" : "Saved locally",
      );
    } else if (dirty.current) {
      if (base.current.digest !== s.code_digest) {
        conflictRef.current = true;
        setConflict(true);
      }
    } else {
      base.current = { revision: s.revision, digest: s.code_digest };
      text.current = s.code;
      setDraft(s.code);
    }
  };
  const refresh = async () => {
    const results = await Promise.allSettled([
      api<StudyState>("state"),
      api<Queue>(`queue?minutes=${minutes}&include_new=${includeNew}`),
      api<Progress>("progress"),
    ]);
    if (results[0].status === "fulfilled") {
      apply(results[0].value);
      setConnectionError("");
    } else {
      setConnectionError(
        "The local app is unreachable. Keep this window open; your browser draft is preserved.",
      );
    }
    if (results[1].status === "fulfilled") setQueue(results[1].value);
    if (results[2].status === "fulfilled") setProgress(results[2].value);
  };
  useEffect(() => {
    void refresh();
  }, [minutes, includeNew]);
  useEffect(() => {
    const timer = setInterval(() => {
      api<StudyState>("state")
        .then((s) => {
          apply(s);
          setConnectionError("");
        })
        .catch(() =>
          setConnectionError(
            "Connection lost. Your browser draft is preserved; retry the connection.",
          ),
        );
    }, 2000);
    const warning = () => setStorageError(true);
    const unload = (event: BeforeUnloadEvent) => {
      if (dirty.current) event.preventDefault();
    };
    window.addEventListener("practice-storage-error", warning);
    window.addEventListener("beforeunload", unload);
    return () => {
      clearInterval(timer);
      window.removeEventListener("practice-storage-error", warning);
      window.removeEventListener("beforeunload", unload);
    };
  }, []);
  useEffect(() => {
    const sid = state?.session?.session_id;
    const events = new EventSource(
      "/api/coach/events" + (sid ? `?session_id=${sid}` : ""),
    );
    events.onmessage = async (e) => {
      try {
        const incoming = JSON.parse(e.data) as CoachStatus;
        const current = latest.current?.session;
        if (
          current &&
          incoming.requests.some(
            (r) =>
              r.session_id === current.session_id &&
              (r.application_revision ?? 0) > current.revision,
          )
        ) {
          apply(await api<StudyState>("state"));
        }
        setCoach(incoming);
      } catch {
        setError("Coach status could not be read. Reconnect coaching.");
      }
    };
    events.onerror = () =>
      setCoach((current) =>
        current
          ? {
              ...current,
              connection: "unavailable",
              message:
                "Coach status connection lost. Reconnect coaching; your editor remains available.",
            }
          : null,
      );
    return () => events.close();
  }, [state?.session?.session_id]);
  const save = async (): Promise<void> => {
    if (saving.current) {
      await saving.current;
      if (dirty.current) await save();
      return;
    }
    if (!dirty.current) return;
    if (conflictRef.current)
      throw new Error("Compare the two saved versions before continuing.");
    const s = latest.current?.session;
    if (!s)
      throw new Error(
        "No active exercise. Export your draft before starting another.",
      );
    const candidate = text.current;
    const pending = (async () => {
      try {
        setSaveStatus("Saving…");
        const response = await api<StudyState>("action/save", {
          code: candidate,
          revision: base.current.revision,
          code_digest: base.current.digest,
        });
        base.current = {
          revision: response.session!.revision,
          digest: response.session!.code_digest,
        };
        dirty.current = text.current !== candidate;
        apply(response);
        storeDraft("code-" + s.session_id, {
          code: text.current,
          digest: base.current.digest,
        });
        setSaveStatus(dirty.current ? "Unsaved changes" : "Saved locally");
      } catch (e) {
        setSaveStatus("Saved in browser");
        if (e instanceof ApiError && e.status === 409) {
          conflictRef.current = true;
          setConflict(true);
        }
        throw e;
      } finally {
        saving.current = null;
      }
    })();
    saving.current = pending;
    await pending;
  };
  const change = (value: string) => {
    if (!dirty.current && latest.current?.session)
      base.current = {
        revision: latest.current.session.revision,
        digest: latest.current.session.code_digest,
      };
    text.current = value;
    dirty.current = true;
    setDraft(value);
    setSaveStatus("Unsaved changes");
    storeDraft("code-" + activeId.current, {
      code: value,
      digest: base.current.digest,
    });
  };
  useEffect(() => {
    if (!dirty.current || conflict) return;
    const timer = setTimeout(
      () => void save().catch((e) => setError((e as Error).message)),
      700,
    );
    return () => clearTimeout(timer);
  }, [draft, conflict]);
  const operate = async <T = unknown>(
    path: string,
    data: unknown = {},
  ): Promise<T> => {
    setBusy(true);
    setError("");
    try {
      if (
        !["action/stop", "coach/interrupt", "coach/disconnect"].includes(path)
      )
        await save();
      const result = await api<T>(path, data);
      if (result && typeof result === "object" && "connection" in result)
        setCoach(result as unknown as CoachStatus);
      if (result && typeof result === "object" && "session" in result)
        apply(result as unknown as StudyState);
      await refresh();
      return result;
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy(false);
    }
  };
  const mutate = async <T = unknown>(
    path: string,
    data: Record<string, unknown> = {},
  ): Promise<T> => {
    await save();
    return operate<T>(path, {
      ...data,
      revision: latest.current?.session?.revision,
    });
  };
  const send = async (
    message: string,
    kind: "question" | "approach" | "check" | "review" = "question",
    allowCode = false,
  ) => {
    await save();
    const previousSession = latest.current?.session;
    const freshState = await api<StudyState>("state");
    apply(freshState);
    const s = freshState.session;
    if (!s) return;
    if (
      previousSession &&
      (previousSession.session_id !== s.session_id ||
        previousSession.code_digest !== s.code_digest)
    ) {
      throw new Error(
        "Your code changed in another window. Review the saved version before sending this question.",
      );
    }
    const fresh = {
      request_id: crypto.randomUUID(),
      session_id: s.session_id,
      revision: s.revision,
      code_digest: s.code_digest,
      message,
      kind,
      allow_code: allowCode,
    };
    const key = "coach-pending-" + s.session_id;
    const previous = readStored<typeof fresh | null>(key, null);
    const same =
      previous &&
      previous.message === message &&
      previous.kind === kind &&
      previous.code_digest === s.code_digest &&
      previous.allow_code === allowCode;
    if (
      previous &&
      !same &&
      !coach?.requests.some((r) => r.request_id === previous.request_id)
    )
      throw new Error(
        "The previous question has an uncertain acknowledgement. Reconnect coaching before sending a different question.",
      );
    const pending = same ? previous : fresh;
    storeDraft(key, pending);
    try {
      const result = await operate("coach/requests", pending);
      storeDraft(key, null);
      return result;
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500)
        storeDraft(key, null);
      throw e;
    }
  };
  const resolveConflict = async (keepDraft: boolean) => {
    const s = latest.current?.session;
    if (!s) return;
    if (!keepDraft) {
      text.current = s.code || "";
      dirty.current = false;
      setDraft(text.current);
    }
    base.current = { revision: s.revision, digest: s.code_digest };
    conflictRef.current = false;
    setConflict(false);
    storeDraft("code-" + s.session_id, {
      code: text.current,
      digest: s.code_digest,
    });
    await save();
  };
  return {
    state,
    queue,
    progress,
    coach,
    error,
    setError,
    connectionError,
    busy,
    draft,
    change,
    saveStatus,
    conflict,
    storageError,
    refresh,
    operate,
    mutate,
    send,
    resolveConflict,
    save,
    latest,
  };
}
