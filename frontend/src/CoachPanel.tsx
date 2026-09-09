import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { Bot, Send, Square, ChevronDown } from "lucide-react";
import CoachConnection from "./CoachConnection";
import type { CoachStatus, Session } from "./types";
import { useDraft, exportText } from "./persistence";

interface Props {
  session: Session;
  status: CoachStatus | null;
  send: (
    message: string,
    kind?: "question" | "approach" | "check" | "review",
    allowCode?: boolean,
  ) => Promise<unknown>;
  operate: (path: string, data?: unknown) => Promise<unknown>;
  convert: () => Promise<unknown>;
}
export default function CoachPanel({
  session,
  status,
  send,
  operate,
  convert,
}: Props) {
  const [message, setMessage] = useDraft("question-" + session.session_id, "");
  const [allowCode, setAllowCode] = useState(false);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [working, setWorking] = useState(false);
  const actionPending = useRef(0);
  const submitting = useRef(false);
  const currentMessage = useRef(message);
  currentMessage.current = message;
  const [conversion, setConversion] = useState(false);
  const [auto, setAuto] = useState(status?.preferences.automatic ?? true);
  useEffect(
    () => setAuto(status?.preferences.automatic ?? true),
    [status?.preferences.automatic],
  );
  const messages =
    status?.requests.filter((r) => r.session_id === session.session_id) || [];
  const stream = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const independent =
    session.assessment_mode !== "practice" && session.activity !== "learn";
  useEffect(() => {
    if (following.current)
      stream.current?.scrollTo({ top: stream.current.scrollHeight });
  }, [JSON.stringify(messages)]);
  const act = async (callback: () => Promise<unknown>) => {
    actionPending.current += 1;
    setWorking(true);
    setError("");
    try {
      return await callback();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      actionPending.current -= 1;
      setWorking(actionPending.current > 0);
    }
  };
  const submit = async () => {
    if (
      submitting.current ||
      actionPending.current ||
      !message.trim() ||
      status?.active_request ||
      status?.connection !== "connected" ||
      status.usage.blocked ||
      (!session.initial_reasoning && session.activity !== "learn")
    )
      return;
    setError("");
    if (independent) {
      setConversion(true);
      return;
    }
    setSending(true);
    submitting.current = true;
    try {
      await send(message, "question", allowCode);
      if (currentMessage.current === message) setMessage("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
      submitting.current = false;
    }
  };
  return (
    <aside
      className="coach-panel panel"
      id="practice-panel-coach"
      aria-label="Codex coach"
    >
      <header className="panel-heading">
        <div>
          <Bot size={20} />
          <h2>Learning coach</h2>
        </div>
        <span
          className={
            status?.connection === "connected" ? "badge success" : "badge"
          }
        >
          {status?.connection === "connected" ? "Connected" : "Optional"}
        </span>
      </header>
      <div className="coach-connection">
        <p>
          {status?.connection === "connected"
            ? status.usage.known
              ? `${Math.round(status.usage.remaining || 0)}% of included allowance remaining`
              : "Allowance unavailable · refresh to continue"
            : status?.message ||
              "Connect your ChatGPT account for coaching here."}
        </p>
        {status?.connection === "connected" && status.usage.conserving && (
          <p className="warning-text">
            Conserving allowance. Automatic checkpoints are paused.
          </p>
        )}
        {status?.connection === "connected" &&
          status.usage.windows.map((w, i) =>
            w.resets_at ? (
              <small key={i}>
                Window resets {new Date(w.resets_at * 1000).toLocaleString()}
              </small>
            ) : null,
          )}
        <CoachConnection
          status={status}
          operate={operate}
          showMessage={false}
        />
      </div>
      {independent && (
        <div className="assessment-notice">
          <strong>Independent attempt</strong>
          <p>
            Try your approach first. Your pre-help work will be preserved if you
            switch to guided practice.
          </p>
          <button className="text-button" onClick={() => setConversion(true)}>
            Get guided help
          </button>
          <details>
            <summary>How independent practice works</summary>
            <p>
              Record your own idea, edit your code, and run tests. Pause saves
              your work. Finish opens a review before anything is published. You
              can use these controls without ending the assessment; hints and
              solution discussion need guided practice.
            </p>
          </details>
        </div>
      )}
      {conversion && independent && (
        <div
          className="conversion-card"
          role="region"
          aria-label="Assessment help choice"
        >
          <h3>Switch to guided practice?</h3>
          <p>
            This ends the independent assessment. Your draft stays, and further
            work is recorded as assisted learning.
          </p>
          <div className="button-row">
            <button
              className="secondary small"
              onClick={() => setConversion(false)}
            >
              Continue independently
            </button>
            <button
              className="primary small"
              onClick={() =>
                void act(async () => {
                  await convert();
                  setConversion(false);
                })
              }
            >
              Switch to guided practice
            </button>
          </div>
        </div>
      )}
      <div
        className="coach-messages"
        ref={stream}
        onScroll={() => {
          const e = stream.current!;
          following.current =
            e.scrollHeight - e.scrollTop - e.clientHeight < 70;
        }}
      >
        {!messages.length && (
          <div className="coach-empty">
            <Bot size={32} />
            <h3>A little help, when it matters.</h3>
            <p>
              Explain an idea, untangle a mistake, or ask for the smallest
              useful hint.
            </p>
          </div>
        )}
        {messages.map((m) => (
          <article className="exchange" key={m.request_id}>
            <div className="learner-message">
              <small>{m.kind === "question" ? "You" : "Checkpoint"}</small>
              <p>{m.message}</p>
            </div>
            <div className="coach-message">
              <small>
                Codex{" "}
                {m.assistance && m.assistance !== "none"
                  ? `· ${m.assistance} help`
                  : ""}
              </small>
              {m.reply && (
                <Markdown
                  skipHtml
                  components={{ img: () => <span>Image omitted</span> }}
                >
                  {m.reply}
                </Markdown>
              )}
              {m.diff && (
                <details>
                  <summary>Preview proposed code change</summary>
                  <pre className="diff">{m.diff}</pre>
                  <button
                    className="secondary small"
                    disabled={
                      m.proposal_applied ||
                      m.code_digest !== session.code_digest
                    }
                    onClick={() =>
                      void act(() =>
                        operate("coach/apply", {
                          request_id: m.request_id,
                          kind: "code",
                          revision: m.application_revision,
                        }),
                      )
                    }
                  >
                    {m.proposal_applied ? "Applied" : "Apply this change"}
                  </button>
                  <p className="muted">
                    Reviewing this proposal counts as assistance. Applying it
                    requires a new test run.
                  </p>
                </details>
              )}
              {m.error && <p className="warning-text">{m.error}</p>}
              {["queued", "sending", "running"].includes(m.status) && (
                <p role="status" className="working">
                  Considering your saved approach…
                </p>
              )}
            </div>
          </article>
        ))}
      </div>
      {error && (
        <div className="inline-error" role="alert">
          {error}
        </div>
      )}
      <form
        className="coach-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="coach-question" className="sr-only">
          Ask your learning coach
        </label>
        <textarea
          id="coach-question"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask a question or explain where you’re stuck…"
          rows={3}
          onKeyDown={(e) => {
            if (
              (e.ctrlKey || e.metaKey) &&
              e.key === "Enter" &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={allowCode}
            onChange={(e) => setAllowCode(e.target.checked)}
          />
          Include a code-change preview if useful
        </label>
        <div className="button-row">
          <small>Ctrl + Enter to send</small>
          <span className="spacer" />
          {status?.active_request ? (
            <button
              type="button"
              className="secondary"
              onClick={() => void act(() => operate("coach/interrupt", {}))}
            >
              <Square size={15} />
              Stop coach
            </button>
          ) : (
            <button
              className="primary"
              disabled={
                sending ||
                working ||
                !message.trim() ||
                status?.connection !== "connected" ||
                status?.usage.blocked ||
                (!session.initial_reasoning && session.activity !== "learn")
              }
            >
              <Send size={15} />
              Send
            </button>
          )}
        </div>
      </form>
      <details className="coach-options">
        <summary>
          <ChevronDown size={14} />
          Coach preferences
        </summary>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={auto}
            onChange={(e) => {
              setAuto(e.target.checked);
              void act(() =>
                operate("coach/preferences", {
                  ...status?.preferences,
                  automatic: e.target.checked,
                }),
              );
            }}
          />
          Automatic practice checkpoints
        </label>
        {(["approach", "check"] as const).map((kind) => (
          <label className="checkbox" key={kind}>
            <input
              type="checkbox"
              checked={status?.preferences[kind] ?? true}
              onChange={(e) =>
                void act(() =>
                  operate("coach/preferences", {
                    ...status?.preferences,
                    [kind]: e.target.checked,
                  }),
                )
              }
            />
            {kind === "approach"
              ? "After my initial approach"
              : "After meaningful test results"}
          </label>
        ))}
        <label>
          Model
          <select
            value={status?.preferences.model || ""}
            onChange={(e) =>
              void act(() =>
                operate("coach/preferences", {
                  ...status?.preferences,
                  model: e.target.value || null,
                  effort: null,
                }),
              )
            }
          >
            <option value="">Codex default</option>
            {status?.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        {status?.preferences.model && (
          <label>
            Reasoning effort
            <select
              value={status.preferences.effort || ""}
              onChange={(e) =>
                void act(() =>
                  operate("coach/preferences", {
                    ...status.preferences,
                    effort: e.target.value || null,
                  }),
                )
              }
            >
              <option value="">Model default</option>
              {status.models
                .find((m) => m.id === status.preferences.model)
                ?.efforts.map((e) => (
                  <option value={e} key={e}>
                    {e}
                  </option>
                ))}
            </select>
          </label>
        )}
        <button
          className="text-button"
          onClick={() => void act(() => operate("coach/disconnect", {}))}
        >
          Disconnect coaching
        </button>
        <button
          className="text-button"
          onClick={() =>
            exportText(
              JSON.stringify(
                { question: message, conversation: messages },
                null,
                2,
              ),
              "private-coaching-backup.json",
            )
          }
        >
          Export private conversation
        </button>
        <p className="muted">
          Conversations stay on this computer and in Codex’s managed storage.
          Approved learning summaries can be published. No API billing or credit
          purchases.
        </p>
      </details>
    </aside>
  );
}
