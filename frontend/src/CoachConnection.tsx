import { useRef, useState } from "react";
import { Plug } from "lucide-react";
import type { CoachStatus } from "./types";

export default function CoachConnection({
  status,
  operate,
  showMessage = true,
}: {
  status: CoachStatus | null;
  operate: (path: string, data?: unknown) => Promise<unknown>;
  showMessage?: boolean;
}) {
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const act = async (path: string) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      await operate(path, {});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  };
  const connected = status?.connection === "connected";
  return (
    <div className="coach-setup">
      {showMessage && (
        <p role="status">
          {pending
            ? "Connecting to Codex…"
            : status?.message ||
              "Connect your ChatGPT account for optional coaching."}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        {!connected && !status?.auth_url && (
          <button
            className="secondary small"
            disabled={pending}
            onClick={() => void act("coach/connect")}
          >
            <Plug size={15} />
            {pending ? "Connecting…" : "Connect Codex"}
          </button>
        )}
        {status?.auth_url && (
          <a
            className="primary small"
            href={status.auth_url}
            target="_blank"
            rel="noreferrer"
          >
            Sign in with ChatGPT
          </a>
        )}
        {(connected || status?.auth_url) && (
          <button
            className="text-button"
            disabled={pending}
            onClick={() => void act("coach/refresh")}
          >
            Refresh connection
          </button>
        )}
      </div>
      {status?.connection === "unavailable" && (
        <details className="coach-setup-help">
          <summary>Help connecting Codex</summary>
          <p>
            Practice Room checks your installed Codex desktop app and CLI. If
            neither has the supported version, install Codex CLI 0.153.4 in a
            terminal:
          </p>
          <pre>npm install -g @openai/codex@0.153.4</pre>
          <p>
            Then choose Connect Codex again. Your practice remains available
            while you set this up.
          </p>
          <a
            href="https://learn.chatgpt.com/docs/codex/cli"
            target="_blank"
            rel="noreferrer"
          >
            Codex installation guide
          </a>
        </details>
      )}
    </div>
  );
}
