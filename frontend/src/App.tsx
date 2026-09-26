import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Code2,
  Download,
  Home,
  Lightbulb,
  Pause,
  Play,
  RefreshCw,
  Settings,
  Square,
  TrendingUp,
  X,
} from "lucide-react";
import CoachPanel from "./CoachPanel";
import CompletionDialog, {
  Dialog,
  type CompletionValues,
} from "./CompletionDialog";
import ReasoningForm from "./ReasoningForm";
import { api, formatTime, metricLabel } from "./api";
import { exportText, useDraft } from "./persistence";
import { useTheme, type Theme } from "./theme";
import { useWorkspace } from "./useWorkspace";
import type { Evaluation, Metric, Problem, StudyState } from "./types";
const Editor = lazy(() => import("./Editor"));
type View = "today" | "practice" | "progress";

function ProblemContext({ problem }: { problem: Problem }) {
  return (
    <section
      className="panel problem-context"
      aria-label="Problem and examples"
      id="problem-context"
    >
      <span className="eyebrow">Problem</span>
      <h2>{problem.title}</h2>
      <p className="problem-prompt">{problem.prompt}</p>
      <h3>Function</h3>
      <pre>{problem.signature}</pre>
      <h3>Constraints</h3>
      <ul>
        {problem.constraints.map((text, i) => (
          <li key={i}>{text}</li>
        ))}
      </ul>
      <h3>Examples</h3>
      {problem.examples.map((example, i) => (
        <article className="example" key={i}>
          <strong>Example {i + 1}</strong>
          <pre>
            {Object.entries(example.inputs)
              .map(([key, value]) => `${key} = ${JSON.stringify(value)}`)
              .join("\n")}
            {"\n"}Output: {JSON.stringify(example.output)}
          </pre>
          {example.explanation && <p>{example.explanation}</p>}
        </article>
      ))}
    </section>
  );
}

function Signal({
  title,
  metric,
  description,
}: {
  title: string;
  metric?: Metric;
  description: string;
}) {
  return (
    <article className="panel signal">
      <h2>{title}</h2>
      <strong>{metricLabel(metric)}</strong>
      <p>{description}</p>
    </article>
  );
}

export default function App() {
  const [view, setView] = useState<View>("today");
  const [theme, setTheme] = useTheme();
  const [minutes, setMinutes] = useDraft("minutes", 60);
  const [includeNew, setIncludeNew] = useDraft("weekend-override", false);
  const w = useWorkspace(minutes, includeNew);
  const s = w.state?.session;
  const repair = w.state?.repair;
  const [coachVisible, setCoachVisible] = useDraft("coach-visible", false);
  const [answer, setAnswer] = useDraft(
    "reasoning-" + (s?.session_id || "none"),
    "",
  );
  const [retry, setRetry] = useDraft("retry-" + (s?.session_id || "none"), "");
  const [takeaway, setTakeaway] = useDraft(
    "takeaway-" + (s?.session_id || "none"),
    "",
  );
  const [repairAnswer, setRepairAnswer] = useDraft(
    "repair-" + (repair?.error_id || "none"),
    repair?.application || "",
  );
  const [repairVersion, setRepairVersion] = useDraft<number | null>(
    "repair-version-" + (repair?.error_id || "none"),
    null,
  );
  const [repairPassed, setRepairPassed] = useState(false);
  const [facts, setFacts] = useState<Evaluation | null>(null);
  const [hintChoice, setHintChoice] = useState<"hint" | "example" | null>(null);
  const [converting, setConverting] = useState(false);
  const [publication, setPublication] = useState<{
    sessions: {
      session_id: string;
      title: string;
      rating: string;
      files: string[];
    }[];
    files: string[];
    destination: string;
  } | null>(null);
  const [excludedSessions, setExcludedSessions] = useState<string[]>([]);
  useEffect(() => setExcludedSessions([]), [publication]);
  const beforeFinishPhase = useRef("implementation");
  const opened = useRef(false);
  const receivedAt = useMemo(() => Date.now(), [w.state]);
  const [, tick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!opened.current && w.state) {
      opened.current = true;
      if (w.state.session || w.state.repair) setView("practice");
      if (w.state.session?.phase === "administration") {
        const sid = w.state.session.session_id;
        beforeFinishPhase.current =
          w.state.session.previous_phase || "implementation";
        void api<Evaluation>("action/evaluate", {})
          .then((value) => {
            if (w.latest.current?.session?.session_id === sid) setFacts(value);
          })
          .catch((error) => w.setError(error.message));
      }
    }
  }, [w.state]);
  const elapsed =
    (s?.elapsed_seconds ?? w.state?.practice?.elapsed_seconds ?? 0) +
    (s?.phase_started_at ? Math.max(0, (Date.now() - receivedAt) / 1000) : 0);
  const checked = w.state?.check;
  const running = checked?.status === "running";
  const currentCheck =
    !!s &&
    checked?.code_digest === s.code_digest &&
    w.saveStatus === "Saved on this computer";
  const review = w.coach?.requests
    .filter(
      (r) =>
        r.session_id === s?.session_id &&
        r.kind === "review" &&
        r.status === "completed" &&
        r.code_digest === s?.code_digest,
    )
    .at(-1);
  const safely = (fn: () => Promise<unknown>) => {
    void fn().catch((error) =>
      w.setError(
        error instanceof Error
          ? error.message
          : "This action could not be completed.",
      ),
    );
  };
  const downloadWork = () =>
    exportText(
      JSON.stringify(
        {
          problem: s?.problem,
          session_id: s?.session_id,
          code: w.draft,
          reasoning: answer || s?.initial_reasoning?.approach,
          takeaway,
          repair: repairAnswer,
        },
        null,
        2,
      ),
      "practice-work.json",
    );
  const start = async (synchronize = true) => {
    const next = await w.operate<StudyState & { message?: string }>(
      "practice/start",
      { minutes, include_new: includeNew, synchronize },
    );
    if (next.session || next.repair) setView("practice");
    else if (next.message) w.setError(next.message);
  };
  const saveRepair = async () => {
    await w.operate("practice/repair-draft", {
      session_id: repair?.session_id,
      answer: repairAnswer,
      revision: repairVersion ?? repair?.revision ?? 0,
    });
    setRepairVersion(null);
  };
  const repairAction = async (
    path: string,
    extra: Record<string, unknown> = {},
  ) => {
    await saveRepair();
    return w.operate(path, {
      session_id: repair?.session_id,
      answer: repairAnswer,
      revision: w.latest.current?.repair?.revision ?? 0,
      ...extra,
    });
  };
  const pause = async () => {
    if (repair) await saveRepair();
    await w.operate("practice/pause", {});
    setView("today");
  };
  const convert = async () => {
    setConverting(true);
    try {
      return await w.mutate("practice/convert");
    } finally {
      setConverting(false);
    }
  };
  const help = async (kind: "hint" | "example") => {
    if (s?.assessment_mode === "independent") {
      setHintChoice(kind);
      return;
    }
    await w.mutate(kind === "hint" ? "action/hint" : "action/worked-example");
  };
  const finishPreview = async () => {
    beforeFinishPhase.current =
      w.latest.current?.session?.phase || "implementation";
    await w.mutate("action/phase", { phase: "administration" });
    setFacts(await w.operate<Evaluation>("action/evaluate", {}));
  };
  const cancelFinish = () =>
    safely(async () => {
      setFacts(null);
      await w.mutate("action/phase", { phase: beforeFinishPhase.current });
    });
  const finish = async (values: CompletionValues) => {
    if (!s || !facts) return;
    if (facts.session_id !== w.latest.current?.session?.session_id) {
      setFacts(null);
      throw new Error(
        "The active problem changed. Open a fresh completion summary.",
      );
    }
    if (values.findings.length)
      await w.mutate("action/evidence", { findings: values.findings });
    const now = await w.operate<Evaluation>("action/evaluate", {});
    await w.mutate("practice/finish", {
      session_id: w.latest.current!.session!.session_id,
      rating: now.recall_outcome === "failure" ? "again" : values.rating,
      recall_confirmed: values.recallConfirmed,
      expected_session_ids: values.publish
        ? [
            ...(facts.unpublished_session_ids || []),
            w.latest.current!.session!.session_id,
          ]
        : undefined,
      takeaway: values.takeaway,
      explained: values.explained,
      constraints_met: values.constraints,
      minutes: values.minutes,
      publish: values.publish,
      stopped:
        !now.tests_passed && s.activity !== "recall" && s.activity !== "learn",
    });
    setFacts(null);
    setView("today");
  };
  const automatic = useRef(new Set<string>());
  useEffect(() => {
    if (
      !s?.initial_reasoning ||
      s.assessment_mode === "independent" ||
      !w.coach?.preferences.automatic ||
      w.coach.connection !== "connected" ||
      w.coach.usage.blocked ||
      w.coach.usage.conserving ||
      w.coach.active_request ||
      facts
    )
      return;
    const checkpoint =
      checked?.status === "complete" && checked.code_digest === s.code_digest;
    const kind = checkpoint ? "check" : "approach";
    if (!w.coach.preferences[kind]) return;
    const key = s.session_id + kind + (checkpoint ? s.code_digest : "");
    if (automatic.current.has(key)) return;
    automatic.current.add(key);
    safely(() =>
      w.send(
        checkpoint
          ? "Review this check and suggest one useful next step."
          : "Review my initial approach briefly. Follow up only on important missing reasoning.",
        kind,
      ),
    );
  }, [
    s?.initial_reasoning,
    s?.code_digest,
    w.coach?.preferences,
    w.coach?.active_request,
    checked?.status,
  ]);

  if (!w.state)
    return (
      <main className="loading">
        <Code2 size={30} />
        <h1>Opening your practice room</h1>
        <p>{w.connectionError || "Loading your saved work…"}</p>
        {w.connectionError && (
          <>
            <p>
              Open Start Study on this computer to start or reconnect the app.
            </p>
            <button className="primary" onClick={() => void w.refresh()}>
              Retry connection
            </button>
          </>
        )}
      </main>
    );

  return (
    <div className="app-shell">
      <header className="app-header">
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            setView("today");
          }}
        >
          <Code2 size={22} />
          <span>Practice Room</span>
        </a>
        <nav aria-label="Main navigation">
          <button
            className={view === "today" ? "selected" : ""}
            aria-current={view === "today" ? "page" : undefined}
            onClick={() => setView("today")}
          >
            <Home size={17} />
            Today
          </button>
          <button
            className={view === "practice" ? "selected" : ""}
            aria-current={view === "practice" ? "page" : undefined}
            onClick={() => (s || repair ? setView("practice") : safely(start))}
          >
            <BookOpen size={17} />
            Practice
          </button>
          <button
            className={view === "progress" ? "selected" : ""}
            aria-current={view === "progress" ? "page" : undefined}
            onClick={() => setView("progress")}
          >
            <TrendingUp size={17} />
            Progress
          </button>
        </nav>
        <details className="settings">
          <summary aria-label="Settings">
            <Settings size={20} />
            <span>Settings</span>
          </summary>
          <div className="settings-menu">
            <label>
              Theme
              <select
                value={theme}
                onChange={(event) => setTheme(event.target.value as Theme)}
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="system">System</option>
              </select>
            </label>
            <button
              className="secondary"
              onClick={() =>
                safely(async () =>
                  exportText(
                    JSON.stringify(await api("diagnostics"), null, 2),
                    "practice-diagnostics.json",
                  ),
                )
              }
            >
              Download diagnostics
            </button>
            {w.recoveredDrafts.length > 0 && (
              <button
                className="secondary"
                onClick={() =>
                  exportText(
                    JSON.stringify(w.recoveredDrafts, null, 2),
                    "recovered-practice-drafts.json",
                  )
                }
              >
                Download recovered drafts
              </button>
            )}
            <button
              className="secondary"
              disabled={w.busy}
              onClick={() =>
                safely(async () => {
                  await w.operate("app/restart", {});
                  w.setError(
                    "Restarting the app. Reconnect in a moment; your work is saved.",
                  );
                })
              }
            >
              Restart app
            </button>
            <small>Practice Room 0.4 · personal ChatGPT coaching</small>
          </div>
        </details>
      </header>
      <main className="page">
        {(w.error || w.connectionError || w.storageError) && (
          <section className="notice warning" role="alert">
            <div>
              <strong>
                {w.connectionError ? "App connection" : "Needs attention"}
              </strong>
              <p>{w.connectionError || w.error}</p>
              {w.storageError && (
                <p>
                  Browser recovery storage is unavailable. Save to the app or
                  download your work before closing this page.
                </p>
              )}
            </div>
            <div className="button-row">
              <button className="secondary" onClick={() => void w.refresh()}>
                <RefreshCw size={16} />
                Retry connection
              </button>
              <button className="secondary" onClick={downloadWork}>
                <Download size={16} />
                Download work
              </button>
              {!w.connectionError && (
                <button
                  className="icon-button"
                  aria-label="Dismiss message"
                  onClick={() => w.setError("")}
                >
                  <X size={17} />
                </button>
              )}
            </div>
          </section>
        )}
        {w.recoveredDrafts
          .filter((item) => !item.dismissed)
          .map((item) => (
            <section
              className="notice warning"
              key={item.id}
              aria-label="Earlier draft recovered"
            >
              <div>
                <strong>An earlier draft is available</strong>
                <p>
                  Another window finished or changed the problem. Your unsaved
                  code is kept in browser recovery.
                </p>
              </div>
              <div className="button-row">
                <button
                  className="secondary"
                  onClick={() => exportText(item.code, "recovered-practice.py")}
                >
                  Download earlier draft
                </button>
                <button
                  className="text-button"
                  onClick={() => w.dismissRecovered(item.id)}
                >
                  Keep backup and continue
                </button>
              </div>
            </section>
          ))}
        {w.state.recovery.length > 0 && (
          <section className="notice warning">
            <strong>Other saved versions are preserved</strong>
            <p>
              {w.state.recovery.length} imported item(s) differ from this
              computer's saved copy.
            </p>
            <details>
              <summary>Review recovery items</summary>
              {w.state.recovery.map((item) => (
                <p key={item.id}>
                  {item.path} · {item.source}
                  <button
                    className="text-button"
                    onClick={() =>
                      safely(async () => {
                        const versions = await api("recovery/" + item.id);
                        exportText(
                          JSON.stringify(versions, null, 2),
                          "practice-recovery.json",
                        );
                      })
                    }
                  >
                    Download both versions
                  </button>
                </p>
              ))}
            </details>
          </section>
        )}

        {view === "today" && (
          <div className="today-view">
            <div className="page-heading">
              <span className="eyebrow">One problem at a time</span>
              <h1>
                {s || repair
                  ? "Pick up where you left off"
                  : "Your next practice"}
              </h1>
            </div>
            {(w.state.completion || w.state.unpublished_count > 0) && (
              <section
                className="panel saved-learning"
                aria-label="Saved learning"
              >
                <div>
                  <h2>Session saved</h2>
                  <p>
                    {w.state.completion?.message ||
                      "Your completed work is saved on this computer."}
                  </p>
                  {w.state.unpublished_count > 0 && (
                    <p>
                      {w.state.unpublished_count} saved session(s) available to
                      publish.
                    </p>
                  )}
                </div>
                {w.state.unpublished_count > 0 && (
                  <button
                    className="secondary"
                    onClick={() =>
                      safely(async () =>
                        setPublication(await api("publication-preview")),
                      )
                    }
                  >
                    Review & publish
                  </button>
                )}
              </section>
            )}
            <section className="panel start-card">
              <div>
                <span className="badge">
                  {s
                    ? "Saved problem"
                    : repair
                      ? "Saved repair"
                      : w.queue?.activity === "transfer"
                        ? "Independent assessment"
                        : "Recommended"}
                </span>
                <h2>
                  {s?.problem.title ||
                    (repair
                      ? "Apply a corrected rule"
                      : w.queue?.main?.title || "Plan your next practice")}
                </h2>
                <p>
                  {s
                    ? "Your problem, draft, and initial reasoning are ready to resume."
                    : repair
                      ? "Your fresh application is saved. Continue this repair before choosing another problem."
                      : w.queue?.reason || "Checking your practice schedule…"}
                </p>
                {s?.saved_at && (
                  <small>
                    Last saved {new Date(s.saved_at).toLocaleString()}
                  </small>
                )}
              </div>
              <div className="start-actions">
                <button
                  className="primary"
                  disabled={w.busy}
                  onClick={() => safely(start)}
                >
                  <Play size={18} />
                  {s || repair ? "Resume practice" : "Start practice"}
                </button>
                {w.state.sync.status === "pending" && (
                  <button
                    className="secondary"
                    disabled={w.busy}
                    onClick={() => safely(() => start(false))}
                  >
                    Continue locally
                  </button>
                )}
              </div>
            </section>
            <div className="today-details">
              <section className="panel">
                <h2>Time for today</h2>
                <label>
                  Available minutes
                  <input
                    type="number"
                    min={5}
                    max={180}
                    value={minutes}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      if (next >= 5 && next <= 180) setMinutes(next);
                    }}
                  />
                </label>
                {w.queue?.weekend && (
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={includeNew}
                      onChange={(event) => setIncludeNew(event.target.checked)}
                    />
                    Include new material this weekend
                  </label>
                )}
                <p className="muted">
                  A break is suggested at 45 minutes. You can pause sooner and
                  resume this problem later.
                </p>
              </section>
              <section className="panel">
                <h2>Upcoming reviews</h2>
                <p>
                  {w.queue?.due.length || 0} implementation review(s) are
                  waiting. Reviews are scheduled between sessions.
                </p>
                {w.queue?.due.slice(0, 4).map((problem) => (
                  <p key={problem.id}>{problem.title}</p>
                ))}
                {!w.queue?.due.length && (
                  <p className="muted">
                    Completed implementation reviews determine your next due
                    dates.
                  </p>
                )}
              </section>
            </div>
            {w.state.remote_attempts.length > 0 && (
              <section className="panel">
                <h2>Choose your saved attempt</h2>
                <p>
                  These drafts are preserved on GitHub. Choose which one to
                  resume.
                </p>
                {w.state.remote_attempts.map((branch) => (
                  <button
                    key={branch}
                    className="secondary branch-choice"
                    onClick={() =>
                      safely(async () => {
                        await w.operate("action/choose-attempt", { branch });
                        setView("practice");
                      })
                    }
                  >
                    {branch}
                  </button>
                ))}
              </section>
            )}
            {w.queue &&
              (w.queue.repairs.length > 0 || w.queue.support.length > 0) && (
                <details className="panel">
                  <summary>Repairs and learning examples</summary>
                  {w.queue.repairs.map((gate) => (
                    <article key={gate.event_id}>
                      <h3>{gate.skill}</h3>
                      <p>{gate.repair_prompt}</p>
                      <button
                        className="secondary"
                        disabled={w.busy || !gate.eligible || !!s || !!repair}
                        onClick={() =>
                          safely(async () => {
                            await w.operate("action/begin-repair", {
                              error_id: gate.event_id,
                            });
                            setView("practice");
                          })
                        }
                      >
                        {gate.eligible
                          ? "Practice this repair"
                          : "Available after the delay"}
                      </button>
                    </article>
                  ))}
                  {w.queue.support.map((problem) => (
                    <p key={problem.id}>
                      {problem.title}
                      <button
                        className="text-button"
                        disabled={w.busy || !!s || !!repair}
                        onClick={() =>
                          safely(async () => {
                            await w.operate("action/start", {
                              problem_id: problem.id,
                              activity: "learn",
                              include_new: includeNew,
                              synchronize: false,
                            });
                            setView("practice");
                          })
                        }
                      >
                        Open example
                      </button>
                    </p>
                  ))}
                </details>
              )}
          </div>
        )}

        {view === "practice" && (
          <section className="practice-view">
            {!s && !repair ? (
              <section className="panel empty">
                <h1>Your work is saved</h1>
                <p>Start another session when you're ready.</p>
                <button className="primary" onClick={() => setView("today")}>
                  Back to Today
                </button>
              </section>
            ) : (
              <>
                <div className="practice-heading">
                  <div>
                    <span className="eyebrow">
                      {repair
                        ? "Repair"
                        : s?.activity === "recall"
                          ? "Review the approach"
                          : s?.assessment_mode === "independent"
                            ? "Independent assessment"
                            : "Practice"}
                    </span>
                    <h1>{s?.problem.title || "Apply a corrected rule"}</h1>
                  </div>
                  <div className="button-row">
                    <span className="time" aria-label="Active study time">
                      {formatTime(elapsed)}
                    </span>
                    <button
                      className="secondary"
                      disabled={w.busy}
                      onClick={() => safely(pause)}
                    >
                      <Pause size={16} />
                      Pause
                    </button>
                    {s && (
                      <button
                        className="primary"
                        disabled={w.busy || running}
                        onClick={() => safely(finishPreview)}
                      >
                        Finish
                      </button>
                    )}
                  </div>
                </div>
                {s && !s.phase_started_at && (
                  <section className="notice">
                    <div>
                      <strong>Paused · saved on this computer</strong>
                      <p>The full problem and your saved work are below.</p>
                    </div>
                    <button
                      className="primary"
                      disabled={w.busy}
                      onClick={() =>
                        safely(() =>
                          s.budget_reached
                            ? w.operate("action/continue", { minutes: 10 })
                            : start(false),
                        )
                      }
                    >
                      {s.budget_reached
                        ? "Continue for 10 minutes"
                        : "Resume practice"}
                    </button>
                  </section>
                )}
                {s?.break_suggested && s.phase_started_at && (
                  <section className="notice">
                    <p>
                      {s.budget_reached
                        ? "Your planned time is up. Pause or finish when ready."
                        : "You've practiced for 45 minutes. This is a good point to take a break."}
                    </p>
                    <button
                      className="text-button"
                      onClick={() => safely(pause)}
                    >
                      Pause here
                    </button>
                  </section>
                )}
                {s?.timing_uncertain && (
                  <p className="muted">
                    {s.timing_uncertain.reason} You can correct minutes when
                    finishing.
                  </p>
                )}
                <div className="workspace">
                  {s ? (
                    <ProblemContext problem={s.problem} />
                  ) : repair?.problem ? (
                    <ProblemContext problem={repair.problem} />
                  ) : (
                    <section className="panel problem-context">
                      <h2>Fresh application</h2>
                      <p>
                        {repair?.prompt ||
                          w.queue?.repairs.find(
                            (gate) => gate.event_id === repair?.error_id,
                          )?.repair_prompt}
                      </p>
                    </section>
                  )}
                  <div className="work-column">
                    {repair ? (
                      <section className="panel repair-card">
                        <h2>Apply the corrected rule</h2>
                        <p>
                          {repair.prompt ||
                            w.queue?.repairs.find(
                              (gate) => gate.event_id === repair.error_id,
                            )?.repair_prompt}
                        </p>
                        {repair.corrected_rule && (
                          <p>
                            <strong>Rule to practice:</strong>{" "}
                            {repair.corrected_rule}
                          </p>
                        )}
                        <label htmlFor="repair-answer">
                          Your fresh application
                        </label>
                        <textarea
                          id="repair-answer"
                          rows={9}
                          value={repairAnswer}
                          onChange={(event) => {
                            if (repairVersion === null)
                              setRepairVersion(repair.revision ?? 0);
                            setRepairAnswer(event.target.value);
                          }}
                        />
                        <div className="button-row">
                          <button
                            className="secondary"
                            disabled={w.busy}
                            onClick={() => safely(saveRepair)}
                          >
                            Save application
                          </button>
                          <button
                            className="secondary"
                            disabled={w.busy}
                            onClick={() =>
                              safely(() =>
                                repairAction("practice/repair-check"),
                              )
                            }
                          >
                            Run repair assertions
                          </button>
                          {repair.check?.status === "running" && (
                            <button
                              className="secondary"
                              onClick={() =>
                                safely(() =>
                                  w.operate("practice/repair-stop", {}),
                                )
                              }
                            >
                              Stop tests
                            </button>
                          )}
                        </div>
                        {repair.check?.message && (
                          <p role="status">{repair.check.message}</p>
                        )}
                        <p className="muted">
                          Passing your assertions checks the example. Confirm
                          conceptual correctness separately.
                        </p>
                        <div className="button-row">
                          <button
                            className="secondary"
                            disabled={
                              w.busy || w.coach?.connection === "connecting"
                            }
                            onClick={() =>
                              safely(() => w.operate("coach/connect", {}))
                            }
                          >
                            Connect Codex
                          </button>
                          {w.coach?.auth_url && (
                            <a
                              href={w.coach.auth_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Sign in with ChatGPT
                            </a>
                          )}
                          <button
                            className="secondary"
                            disabled={
                              w.busy ||
                              w.coach?.connection !== "connected" ||
                              !!w.coach.active_request ||
                              !repairAnswer.trim()
                            }
                            onClick={() =>
                              safely(() =>
                                repairAction("practice/repair-review", {
                                  request_id: crypto.randomUUID(),
                                }),
                              )
                            }
                          >
                            Check application with Codex
                          </button>
                        </div>
                        {repair.coach_review && (
                          <p>
                            Coach judgment: {repair.coach_review.value}.{" "}
                            {repair.coach_review.explanation}
                          </p>
                        )}
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={repairPassed}
                            onChange={(event) =>
                              setRepairPassed(event.target.checked)
                            }
                          />
                          I reviewed a correct fresh application, with Codex or
                          an external coach
                        </label>
                        <button
                          className="primary"
                          disabled={
                            w.busy ||
                            !repairAnswer.trim() ||
                            repair.check?.status === "running"
                          }
                          onClick={() =>
                            safely(async () => {
                              await repairAction("practice/advance", {
                                passed: repairPassed,
                              });
                              setView("today");
                            })
                          }
                        >
                          Finish repair locally
                        </button>
                        <button
                          className="text-button"
                          disabled={w.busy}
                          onClick={() =>
                            safely(async () => {
                              await repairAction("practice/advance", {
                                skip: true,
                              });
                              setView("today");
                            })
                          }
                        >
                          Keep draft for later
                        </button>
                      </section>
                    ) : (
                      s && (
                        <>
                          {!s.initial_reasoning && s.activity !== "learn" ? (
                            <ReasoningForm
                              answer={answer}
                              busy={w.busy}
                              setAnswer={setAnswer}
                              submit={(text, quality) =>
                                safely(async () => {
                                  await w.mutate("action/reasoning", {
                                    answer: text,
                                    quality,
                                  });
                                  setAnswer(text);
                                })
                              }
                            />
                          ) : (
                            <>
                              <details className="panel original-idea">
                                <summary>Your initial idea</summary>
                                <p>
                                  {s.initial_reasoning?.approach ||
                                    "Learning from an example."}
                                </p>
                              </details>
                              {s.worked_example && (
                                <details className="panel worked-example" open>
                                  <summary>
                                    Worked example · assistance recorded
                                  </summary>
                                  <p>{s.worked_explanation}</p>
                                  <pre>{s.worked_example}</pre>
                                </details>
                              )}
                              {w.conflict && (
                                <section
                                  className="panel conflict"
                                  role="alert"
                                >
                                  <h2>Two versions of your code</h2>
                                  <p>
                                    Your text is preserved below. Compare the
                                    version saved by the other window before
                                    choosing.
                                  </p>
                                  <details>
                                    <summary>Other saved version</summary>
                                    <pre>{s.code}</pre>
                                  </details>
                                  <div className="button-row">
                                    <button
                                      className="secondary"
                                      onClick={() =>
                                        safely(() => w.resolveConflict(false))
                                      }
                                    >
                                      Use other saved version
                                    </button>
                                    <button
                                      className="primary"
                                      onClick={() =>
                                        safely(() => w.resolveConflict(true))
                                      }
                                    >
                                      Keep my draft
                                    </button>
                                    <button
                                      className="text-button"
                                      onClick={downloadWork}
                                    >
                                      Download work
                                    </button>
                                  </div>
                                </section>
                              )}
                              {s.activity !== "recall" && (
                                <section className="panel editor-shell">
                                  <div className="editor-toolbar">
                                    <span className="save-status" role="status">
                                      {w.saveStatus}
                                    </span>
                                    <div className="button-row">
                                      {running ? (
                                        <button
                                          className="secondary"
                                          onClick={() =>
                                            safely(() =>
                                              w.operate("action/stop", {}),
                                            )
                                          }
                                        >
                                          <Square size={15} />
                                          Stop tests
                                        </button>
                                      ) : (
                                        <button
                                          className="primary"
                                          disabled={w.busy || w.conflict}
                                          onClick={() =>
                                            safely(() =>
                                              w.mutate("action/check"),
                                            )
                                          }
                                        >
                                          <Play size={15} />
                                          Check solution
                                        </button>
                                      )}
                                      <button
                                        className="icon-button"
                                        aria-label="Download candidate"
                                        title="Download candidate"
                                        onClick={() => exportText(w.draft)}
                                      >
                                        <Download size={17} />
                                      </button>
                                    </div>
                                  </div>
                                  <Suspense
                                    fallback={
                                      <div className="editor-loading">
                                        Opening the Python editor…
                                      </div>
                                    }
                                  >
                                    <Editor
                                      key={s.session_id}
                                      value={w.draft}
                                      onChange={w.change}
                                      sessionId={s.session_id}
                                    />
                                  </Suspense>
                                </section>
                              )}
                              {s.activity === "recall" && (
                                <section className="panel">
                                  <h2>Review your reconstruction</h2>
                                  <p>
                                    This session revisits the approach. A full
                                    implementation review remains separately
                                    scheduled.
                                  </p>
                                  <button
                                    className="primary"
                                    disabled={w.busy}
                                    onClick={() => safely(finishPreview)}
                                  >
                                    Finish recall
                                  </button>
                                </section>
                              )}
                              {checked?.status && (
                                <section
                                  className="panel test-panel"
                                  aria-label="Test results"
                                >
                                  <h2>
                                    {running
                                      ? "Checking your saved code…"
                                      : currentCheck && checked.all_passed
                                        ? "All checks passed"
                                        : currentCheck
                                          ? "Check results"
                                          : "Run a check for your current code"}
                                  </h2>
                                  <p role="status">
                                    {currentCheck || running
                                      ? checked.message
                                      : "The previous result does not cover your current draft."}
                                  </p>
                                  {currentCheck &&
                                    checked.total_cases !== undefined && (
                                      <p>
                                        {checked.passed_cases} /{" "}
                                        {checked.total_cases} checks passed
                                      </p>
                                    )}
                                  {currentCheck &&
                                    checked.public_failures?.map(
                                      (failure, index) => (
                                        <p key={index}>
                                          Example {failure.example}:{" "}
                                          {failure.error}
                                        </p>
                                      ),
                                    )}
                                </section>
                              )}
                              <section className="panel help-panel">
                                <div className="button-row">
                                  <button
                                    className="secondary"
                                    onClick={() =>
                                      setCoachVisible(!coachVisible)
                                    }
                                  >
                                    <Lightbulb size={17} />
                                    {coachVisible ? "Hide coach" : "Ask coach"}
                                  </button>
                                  <button
                                    className="secondary"
                                    disabled={w.busy}
                                    onClick={() => safely(() => help("hint"))}
                                  >
                                    Give me a hint
                                  </button>
                                  <button
                                    className="text-button"
                                    disabled={w.busy}
                                    onClick={() =>
                                      safely(() => help("example"))
                                    }
                                  >
                                    Study a worked example
                                  </button>
                                </div>
                                {hintChoice && (
                                  <div className="assessment-notice">
                                    <h3>
                                      End the independent assessment for help?
                                    </h3>
                                    <p>
                                      Your pre-help work will be preserved.
                                      Further work records the assistance.
                                    </p>
                                    <div className="button-row">
                                      <button
                                        className="secondary"
                                        onClick={() => setHintChoice(null)}
                                      >
                                        Continue independently
                                      </button>
                                      <button
                                        className="primary"
                                        disabled={converting}
                                        onClick={() =>
                                          safely(async () => {
                                            const kind = hintChoice;
                                            await convert();
                                            setHintChoice(null);
                                            await w.mutate(
                                              kind === "hint"
                                                ? "action/hint"
                                                : "action/worked-example",
                                            );
                                          })
                                        }
                                      >
                                        Switch to guided practice
                                      </button>
                                    </div>
                                  </div>
                                )}
                                {s.revealed_hints?.map((hint, index) => (
                                  <p className="revealed-hint" key={index}>
                                    <strong>Hint {index + 1}:</strong> {hint}
                                  </p>
                                ))}
                                <details>
                                  <summary>Record a reasoning retry</summary>
                                  <label htmlFor="retry">
                                    What did you try or change?
                                  </label>
                                  <textarea
                                    id="retry"
                                    value={retry}
                                    rows={2}
                                    onChange={(event) =>
                                      setRetry(event.target.value)
                                    }
                                  />
                                  <button
                                    className="secondary"
                                    disabled={w.busy || !retry.trim()}
                                    onClick={() =>
                                      safely(async () => {
                                        await w.mutate("practice/retry", {
                                          answer: retry,
                                        });
                                        setRetry("");
                                      })
                                    }
                                  >
                                    Save retry
                                  </button>
                                </details>
                              </section>
                            </>
                          )}
                          {coachVisible && (
                            <CoachPanel
                              session={s}
                              status={w.coach}
                              send={w.send}
                              operate={w.operate}
                              convert={convert}
                              converting={converting}
                              busy={w.busy}
                            />
                          )}
                          {!s.initial_reasoning && s.activity !== "learn" && (
                            <button
                              className="text-button"
                              onClick={() => setCoachVisible(!coachVisible)}
                            >
                              {coachVisible
                                ? "Hide coach"
                                : "Connect your learning coach"}
                            </button>
                          )}
                        </>
                      )
                    )}
                  </div>
                </div>
              </>
            )}
          </section>
        )}

        {view === "progress" && (
          <section className="progress-view">
            <div className="page-heading">
              <span className="eyebrow">Evidence over time</span>
              <h1>Your learning progress</h1>
              <p>
                Practice helps build understanding. Retention and independent
                transfer need repeated evidence.
              </p>
            </div>
            <div className="signal-grid">
              <Signal
                title="Independent implementations"
                metric={w.progress?.independent}
                description="Passing code, reconstructed reasoning, and reviewed explanation and complexity."
              />
              <Signal
                title="Delayed implementation"
                metric={w.progress?.delayed}
                description="Full implementation attempts after at least 24 hours."
              />
              <Signal
                title="Unseen transfer"
                metric={w.progress?.unseen}
                description="First attempts at unfamiliar assessment problems."
              />
            </div>
            <section className="panel">
              <h2>Practice history</h2>
              <p>
                {Math.round(w.progress?.recorded_total_minutes || 0)} recorded
                minutes · {w.progress?.baseline_sessions || 0} /{" "}
                {w.progress?.baseline_target || 12} sessions in the new workflow
                baseline.
              </p>
              <p className="muted">
                Historical grouped sessions remain in your history. This
                baseline tracks one-problem sessions separately.
              </p>
            </section>
            <div className="topic-grid">
              {w.progress?.topics.map((topic) => (
                <article className="panel" key={topic.id}>
                  <h2>{topic.title || topic.name || topic.id}</h2>
                  <span className="badge">
                    {topic.status === "planned"
                      ? "Planned"
                      : topic.retained
                        ? "Retention evidence established"
                        : topic.ready
                          ? "Ready for dependent topics"
                          : "Building foundations"}
                  </span>
                </article>
              ))}
            </div>
          </section>
        )}
        <footer className="sync-note">
          <div>
            <strong>
              {w.state.sync.status === "synced"
                ? "Last sync succeeded"
                : w.state.sync.status === "pending"
                  ? "GitHub sync pending"
                  : "Local practice"}
            </strong>
            <p>{w.state.sync.message}</p>
          </div>
          <button
            className="text-button"
            disabled={w.busy}
            onClick={() => safely(() => w.operate("action/sync", {}))}
          >
            <RefreshCw size={15} />
            Sync
          </button>
        </footer>
      </main>
      {facts && s && (
        <CompletionDialog
          session={s}
          facts={facts}
          review={review}
          elapsed={elapsed}
          unpublishedCount={w.state.unpublished_count}
          busy={w.busy}
          takeaway={takeaway}
          setTakeaway={setTakeaway}
          cancel={cancelFinish}
          onFinish={(values) => safely(() => finish(values))}
        />
      )}
      {publication && (
        <Dialog
          titleId="publish-title"
          closeLabel="Cancel publication"
          cancel={() => setPublication(null)}
        >
          <h2 id="publish-title">Publish saved learning</h2>
          <p>Destination: {publication.destination}</p>
          <p>
            Your approved code, review evidence, and reflections will be public.
            Coach conversations stay private.
          </p>
          <ul>
            {publication.sessions.map((session) => (
              <li key={session.session_id}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={!excludedSessions.includes(session.session_id)}
                    onChange={(event) =>
                      setExcludedSessions((previous) =>
                        event.target.checked
                          ? previous.filter((id) => id !== session.session_id)
                          : [...previous, session.session_id],
                      )
                    }
                  />
                  {session.title} - recall {session.rating}
                </label>
              </li>
            ))}
          </ul>
          <details>
            <summary>
              Files to publish (
              {
                Array.from(
                  new Set(
                    publication.sessions
                      .filter(
                        (session) =>
                          !excludedSessions.includes(session.session_id),
                      )
                      .flatMap((session) => session.files),
                  ),
                ).length
              }
              )
            </summary>
            <ul>
              {Array.from(
                new Set(
                  publication.sessions
                    .filter(
                      (session) =>
                        !excludedSessions.includes(session.session_id),
                    )
                    .flatMap((session) => session.files),
                ),
              ).map((file) => (
                <li key={file}>{file}</li>
              ))}
            </ul>
          </details>
          <div className="button-row">
            <button className="secondary" onClick={() => setPublication(null)}>
              Keep locally
            </button>
            <button
              className="primary"
              disabled={
                w.busy ||
                publication.sessions.length === excludedSessions.length
              }
              onClick={() =>
                safely(async () => {
                  await w.operate("action/publish", {
                    session_id: publication.sessions.find(
                      (session) =>
                        !excludedSessions.includes(session.session_id),
                    )!.session_id,
                    session_ids: publication.sessions
                      .filter(
                        (session) =>
                          !excludedSessions.includes(session.session_id),
                      )
                      .map((session) => session.session_id),
                  });
                  setPublication(null);
                })
              }
            >
              Publish {publication.sessions.length - excludedSessions.length}{" "}
              saved session(s)
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
