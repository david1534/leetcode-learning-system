import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  Clock3,
  Code2,
  Download,
  Home,
  Lightbulb,
  Moon,
  Pause,
  Play,
  RefreshCw,
  Settings,
  ShieldCheck,
  Square,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import CoachPanel from "./CoachPanel";
import CoachConnection from "./CoachConnection";
import { formatTime, metricLabel } from "./api";
import { exportText, useDraft } from "./persistence";
import { useTheme, type Theme } from "./theme";
import { useWorkspace } from "./useWorkspace";
import { useStudyClock } from "./useStudyClock";
import type { Evaluation, Finding, Metric, StudyState } from "./types";
const Editor = lazy(() => import("./Editor"));
type View = "today" | "practice" | "progress";
const phases: Record<string, string> = {
  recall: "Thinking & recall",
  implementation: "Coding",
  learning: "Guided learning",
  explanation: "Testing & explanation",
  administration: "Finishing up",
  repair: "Repair",
};

function Signal({
  title,
  metric,
  description,
}: {
  title: string;
  metric: Metric | undefined;
  description: string;
}) {
  return (
    <article className="signal panel">
      <span className="eyebrow">{title}</span>
      <strong>
        {metric?.total ? `${Math.round((metric.rate || 0) * 100)}%` : "—"}
      </strong>
      <p>
        {metric?.total
          ? `${metric.passed} of ${metric.total} attempts`
          : "Not measured yet"}
      </p>
      <small>{description}</small>
    </article>
  );
}
function Dialog({
  children,
  cancel,
}: {
  children: React.ReactNode;
  cancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="finish-title"
      onCancel={(e) => {
        e.preventDefault();
        cancel();
      }}
    >
      <button
        className="icon-button dialog-close"
        aria-label="Cancel completion"
        onClick={cancel}
      >
        <X />
      </button>
      {children}
    </dialog>
  );
}

export default function App() {
  const [view, setView] = useState<View>("today");
  const [theme, setTheme] = useTheme();
  const [minutes, setMinutes] = useDraft("minutes", 60);
  const [includeNew, setIncludeNew] = useDraft("weekend-override", false);
  const w = useWorkspace(minutes, includeNew);
  const s = w.state?.session;
  const parent =
    w.state?.practice?.status === "active" ? w.state.practice : null;
  const stage = parent?.stages[parent.index];
  const [pane, setPane] = useState("code");
  const [coachVisible, setCoachVisible] = useDraft("coach-visible", true);
  const [coachWidth, setCoachWidth] = useDraft("coach-width", 360);
  const panes = ["problem", "code", ...(coachVisible ? ["coach"] : [])];
  const [answer, setAnswer] = useDraft(
    "reasoning-" + (s?.session_id || parent?.practice_id || "none"),
    "",
  );
  const [quality, setQuality] = useState("complete");
  const [retry, setRetry] = useDraft("retry-" + (s?.session_id || "none"), "");
  const [takeaway, setTakeaway] = useDraft(
    "takeaway-" + (s?.session_id || "none"),
    "",
  );
  const [repairAnswer, setRepairAnswer] = useDraft(
    "repair-" + (w.state?.repair?.error_id || "none"),
    w.state?.repair?.application || "",
  );
  const [repairPassed, setRepairPassed] = useState(false);
  const [repairVersion, setRepairVersion] = useDraft<number | null>(
    "repair-version-" + (w.state?.repair?.error_id || "none"),
    null,
  );
  const saveRepair = async () => {
    await w.operate("practice/repair-draft", {
      answer: repairAnswer,
      revision: repairVersion ?? w.state?.repair?.revision ?? 0,
    });
    setRepairVersion(null);
  };
  const repairAction = async (
    path: string,
    extra: Record<string, unknown> = {},
  ) => {
    await saveRepair();
    return w.operate(path, {
      answer: repairAnswer,
      revision: w.latest.current?.repair?.revision ?? 0,
      ...extra,
    });
  };
  const [facts, setFacts] = useState<Evaluation | null>(null);
  const [rating, setRating] = useState("good");
  const [explained, setExplained] = useState(false);
  const [constraints, setConstraints] = useState(false);
  const [actualMinutes, setActualMinutes] = useState("");
  const [finishFindings, setFinishFindings] = useState<Finding[]>([]);
  const beforeFinishPhase = useRef("implementation");
  const [hintChoice, setHintChoice] = useState(false);
  const elapsed = useStudyClock(w.state);
  const safely = (fn: () => Promise<unknown>) => {
    void fn().catch(() => {});
  };
  const start = async () => {
    await w.operate("practice/start", { minutes, include_new: includeNew });
    setView("practice");
  };
  const convert = () => w.mutate("practice/convert");
  const checked = w.state?.check;
  const running = checked?.status === "running";
  const currentCheck =
    !!s &&
    checked?.code_digest === s.code_digest &&
    w.saveStatus === "Saved locally";
  const review = w.coach?.requests
    .filter(
      (r) =>
        r.session_id === s?.session_id &&
        r.kind === "review" &&
        r.status === "completed" &&
        r.code_digest === s?.code_digest,
    )
    .at(-1);
  useEffect(() => {
    if (facts && review?.findings) {
      setFinishFindings(review.findings);
      setExplained(
        review.findings.some(
          (f) => f.dimension === "explanation" && f.value === "success",
        ),
      );
      setConstraints(
        review.findings.some(
          (f) => f.dimension === "constraints" && f.value === "success",
        ),
      );
    }
  }, [review?.request_id, !!facts]);
  const automatic = useRef(new Set<string>());
  useEffect(() => {
    if (
      !s?.initial_reasoning ||
      s.activity !== "learn" ||
      w.coach?.connection !== "connected" ||
      !w.coach.preferences.automatic ||
      w.coach.usage.blocked ||
      w.coach.usage.conserving ||
      w.coach.active_request ||
      facts
    )
      return;
    const checkpoint =
      checked?.status === "complete" && checked.code_digest === s.code_digest;
    if (
      !(checkpoint ? w.coach.preferences.check : w.coach.preferences.approach)
    )
      return;
    const key =
      s.session_id +
      (checkpoint ? "-check-" + checked?.code_digest : "-approach");
    if (automatic.current.has(key)) return;
    automatic.current.add(key);
    safely(() =>
      w.send(
        checkpoint
          ? "Review this check. Focus on one useful next step; don't repeat prior advice."
          : "Review my initial approach briefly. Ask only if something important is missing.",
        checkpoint ? "check" : "approach",
      ),
    );
  }, [
    s?.initial_reasoning,
    s?.activity,
    checked?.code_digest,
    checked?.status,
    w.coach?.connection,
    w.coach?.active_request,
    w.coach?.preferences,
  ]);
  const finishPreview = async () => {
    beforeFinishPhase.current =
      w.latest.current?.session?.phase || "implementation";
    await w.mutate("action/phase", { phase: "administration" });
    const result = await w.operate<Evaluation>("action/evaluate", {});
    setFacts(result);
    setRating(result.recommended_rating);
    setActualMinutes("");
    setExplained(false);
    setConstraints(false);
    setFinishFindings(result.evidence || []);
    if (
      w.coach?.connection === "connected" &&
      !w.coach.usage.blocked &&
      !w.coach.usage.conserving &&
      w.coach.preferences.automatic &&
      !w.coach.active_request
    )
      safely(() =>
        w.send(
          "Assess only the recorded reasoning and current code. Do not teach or add missing explanations. Learner takeaway: " +
            takeaway,
          "review",
        ),
      );
  };
  const cancelFinish = () =>
    safely(async () => {
      setFacts(null);
      await w.mutate("action/phase", { phase: beforeFinishPhase.current });
    });
  const finish = async (publish: boolean) => {
    if (!s || !facts) return;
    if (finishFindings.length) {
      await w.mutate("action/evidence", { findings: finishFindings });
    }
    const now = await w.operate<Evaluation>("action/evaluate", {});
    const session = w.latest.current!.session!;
    await w.mutate("practice/finish", {
      session_id: session.session_id,
      rating: now.recall_outcome === "failure" ? "again" : rating,
      takeaway,
      explained,
      constraints_met: constraints,
      minutes: actualMinutes ? Number(actualMinutes) : null,
      publish,
      stopped: !now.tests_passed,
    });
    setFacts(null);
    setView("today");
  };
  if (!w.state)
    return (
      <main className="loading">
        <Code2 size={30} />
        <h1>Opening your practice room</h1>
        <p>{w.connectionError || "Loading your locally saved learning…"}</p>
        {w.connectionError && (
          <button className="primary" onClick={() => void w.refresh()}>
            Retry connection
          </button>
        )}
      </main>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setView("today");
          }}
          aria-label="Practice Room home"
        >
          <span className="brand-mark">
            <Code2 />
          </span>
          <span>
            practice<span className="brand-light">room</span>
          </span>
        </a>
        <small className="sidebar-caption">
          A LITTLE PRACTICE. LASTING SKILL.
        </small>
        <nav aria-label="Main navigation">
          {(
            [
              ["today", Home, "Today"],
              ["practice", Code2, "Practice"],
              ["progress", TrendingUp, "Progress"],
            ] as const
          ).map(([id, Icon, label]) => (
            <button
              key={id}
              aria-label={label}
              className={view === id ? "nav-item selected" : "nav-item"}
              aria-current={view === id ? "page" : undefined}
              onClick={() => setView(id)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {id === "practice" && s && <span className="live-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <BookOpen size={23} />
          <p>
            Understand the pattern.
            <br />
            Make it your own.
          </p>
          <small>Independent thinking comes first.</small>
        </div>
        <details className="settings">
          <summary aria-label="Settings">
            <Settings size={17} />
            <span>Settings</span>
          </summary>
          <label>
            Appearance
            <select
              aria-label="Appearance"
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
            >
              <option value="dark">Dark</option>
              <option value="light">Light</option>
              <option value="system">System</option>
            </select>
          </label>
          <CoachConnection status={w.coach} operate={w.operate} />
        </details>
        <div className="sidebar-bottom">
          <span
            className={
              w.state.sync.status === "pending"
                ? "status-dot amber"
                : "status-dot"
            }
          />
          <span>
            {w.state.sync.status === "pending"
              ? "Sync pending"
              : "Saved locally"}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh workspace"
            onClick={() => void w.refresh()}
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>YOUR LEARNING WORKSPACE</span>
          <div>
            <ShieldCheck size={15} />
            <span>Thinking stays yours</span>
            <button
              className="icon-button"
              aria-label="Toggle dark mode"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              <Moon size={17} />
            </button>
          </div>
        </header>
        {w.connectionError && (
          <div className="notice warning" role="alert">
            <p>{w.connectionError}</p>
            <button
              className="secondary small"
              onClick={() => void w.refresh()}
            >
              Retry connection
            </button>
          </div>
        )}
        {w.storageError && (
          <div className="notice warning" role="alert">
            <p>
              Browser storage is unavailable. Keep this page open until saved
              locally, or export your draft.
            </p>
            <button
              className="secondary small"
              onClick={() => exportText(w.draft)}
            >
              <Download size={15} />
              Export draft
            </button>
          </div>
        )}
        {w.error && (
          <div className="notice error" role="alert">
            <p>{w.error}</p>
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => w.setError("")}
            >
              <X size={17} />
            </button>
          </div>
        )}
        {view === "today" && (
          <div className="page today">
            <header className="page-heading">
              <span className="eyebrow">
                {new Date().toLocaleDateString(undefined, {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })}
              </span>
              <h1>
                Small steps.
                <br />
                <span>Deeper understanding.</span>
              </h1>
              <p>One clear next step, with room to think.</p>
            </header>
            <div className="today-grid">
              <section className="focus-card panel">
                <div className="card-top">
                  <span className="eyebrow">TODAY’S FOCUS</span>
                  <span className="badge">
                    {parent?.budget_minutes || minutes} min
                  </span>
                </div>
                <div className="focus-symbol">
                  <Code2 size={54} />
                </div>
                <h2>
                  {s || parent
                    ? "Your work is here. Pick up where you left off."
                    : w.queue?.main
                      ? "Build a little more fluency."
                      : "A lighter day is still useful."}
                </h2>
                <p>
                  {s
                    ? "Your code, reasoning, and place in the session are saved together."
                    : w.queue?.reason}
                </p>
                <button
                  className="primary"
                  disabled={
                    w.busy ||
                    (!s &&
                      !parent &&
                      !w.queue?.main &&
                      !w.queue?.repairs.some((r) => r.eligible))
                  }
                  onClick={() => safely(start)}
                >
                  {s || parent ? (
                    <>
                      <Play size={17} />
                      Resume practice
                    </>
                  ) : (
                    <>
                      Start practice
                      <ArrowRight size={17} />
                    </>
                  )}
                </button>
              </section>
              <section className="panel session-card">
                <h2>Your session</h2>
                <label>
                  Time available
                  <select
                    value={minutes}
                    onChange={(e) => setMinutes(Number(e.target.value))}
                  >
                    {[15, 30, 45, 60, 90].map((n) => (
                      <option key={n} value={n}>
                        {n} minutes
                      </option>
                    ))}
                  </select>
                </label>
                <ol className="timeline">
                  <li>
                    <strong>Retrieve & repair</strong>
                    <span>A brief warm-up when useful</span>
                  </li>
                  <li>
                    <strong>Think & implement</strong>
                    <span>One main activity</span>
                  </li>
                  <li>
                    <strong>Explain & reflect</strong>
                    <span>Keep the useful lesson</span>
                  </li>
                </ol>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={includeNew}
                    onChange={(e) => setIncludeNew(e.target.checked)}
                  />
                  Allow new material on weekends
                </label>
                <small>
                  One shared budget. A break is offered at 45 active minutes.
                </small>
              </section>
            </div>
            <div className="section-heading">
              <h2>A few useful signals</h2>
              <button
                className="text-button"
                onClick={() => setView("progress")}
              >
                View progress
                <ChevronRight size={15} />
              </button>
            </div>
            <div className="signal-grid">
              <Signal
                title="Delayed implementation"
                metric={w.progress?.delayed}
                description="Reconstructing an approach after time away"
              />
              <Signal
                title="Unseen transfer"
                metric={w.progress?.unseen}
                description="Choosing an approach on a new problem"
              />
              <article className="signal panel">
                <span className="eyebrow">PROSPECTIVE BASELINE</span>
                <strong>
                  {w.progress?.baseline_sessions || 0}
                  <small> / 12</small>
                </strong>
                <p>Guided sessions completed</p>
                <small>Measuring learning and administration time</small>
              </article>
            </div>
            {w.state.completion && !s && (
              <section className="notice success">
                <div>
                  <strong>Session saved</strong>
                  <p>{w.state.completion.message}</p>
                </div>
                {!w.state.completion.published && (
                  <button
                    className="primary small"
                    onClick={() =>
                      safely(() =>
                        w.operate("action/publish", {
                          session_id: w.state!.completion!.session_id,
                          include_saved: true,
                        }),
                      )
                    }
                  >
                    Publish saved learning ({w.state.unpublished_count})
                  </button>
                )}
              </section>
            )}
            <section className="panel review-list">
              <h2>
                Reviews waiting{" "}
                <span className="badge">{w.queue?.due.length || 0}</span>
              </h2>
              <p>
                {w.queue?.postponed.length || 0} full reviews remain postponed.
                A short retrieval does not extend their implementation
                intervals.
              </p>
              <details>
                <summary>Available learning support</summary>
                {w.queue?.support.map((p) => (
                  <div className="list-row" key={p.id}>
                    <span>{p.title}</span>
                    <button
                      className="secondary small"
                      disabled={!!s || !!parent}
                      onClick={() =>
                        safely(async () => {
                          await w.operate("action/start", {
                            problem_id: p.id,
                            activity: "learn",
                            include_new: includeNew,
                            minutes,
                          });
                          await start();
                        })
                      }
                    >
                      Learn
                    </button>
                  </div>
                ))}
              </details>
            </section>
            {!!w.state.remote_attempts.length && (
              <section className="panel">
                <h2>Choose a saved attempt</h2>
                {w.state.remote_attempts.map((a) => (
                  <button
                    key={a.branch}
                    className="secondary"
                    onClick={() =>
                      safely(() =>
                        w.operate("action/choose-attempt", {
                          branch: a.branch,
                        }),
                      )
                    }
                  >
                    {a.branch}
                  </button>
                ))}
              </section>
            )}
            <div className="sync-note">
              <p>{w.state.sync.message}</p>
              <div className="button-row">
                <button
                  className="text-button"
                  onClick={() => safely(() => w.operate("action/sync", {}))}
                >
                  Retry sync
                </button>
                <button
                  className="text-button"
                  onClick={() => safely(() => w.operate("action/recover", {}))}
                >
                  Recover a draft
                </button>
              </div>
            </div>
          </div>
        )}
        {view === "practice" && (
          <div className="practice-page">
            <header className="practice-heading">
              <div>
                <span className="eyebrow">SPACE TO THINK</span>
                <h1>
                  {stage?.type === "repair"
                    ? "One small repair."
                    : stage?.type === "recall"
                      ? "Bring the idea back."
                      : "Your next good attempt."}
                </h1>
              </div>
              {(s || parent) && (
                <div
                  className="timer"
                  role="timer"
                  aria-label="Active study time"
                >
                  <Clock3 size={19} />
                  <span className="timer-digits">{formatTime(elapsed)}</span>
                  <small>
                    / {parent?.budget_minutes || s?.budget_minutes} min
                  </small>
                </div>
              )}
            </header>
            {parent && (
              <ol className="stage-strip">
                {parent.stages.map((p, i) => (
                  <li
                    key={i}
                    aria-current={i === parent.index ? "step" : undefined}
                    className={i === parent.index ? "active" : ""}
                  >
                    <span>
                      {p.status === "completed" ? <Check size={13} /> : i + 1}
                    </span>
                    {p.label}
                  </li>
                ))}
              </ol>
            )}
            {!s && stage?.type !== "repair" ? (
              <section className="empty panel">
                <Code2 size={40} />
                <h2>Your next step is ready.</h2>
                <p>
                  {w.queue?.reason ||
                    "Start from Today for an activity suited to your progress."}
                </p>
                <button className="primary" onClick={() => setView("today")}>
                  Go to Today
                  <ArrowRight size={17} />
                </button>
              </section>
            ) : stage?.type === "repair" ? (
              <section className="panel support-card">
                <Lightbulb />
                <h2>Apply the corrected rule</h2>
                {w.state.repair?.timing_uncertain && (
                  <p className="warning-text">
                    A timer gap was detected. Review your total active minutes
                    when finishing.
                  </p>
                )}
                {!w.state.repair?.started_at && (
                  <p role="status">Paused. No active time is being counted.</p>
                )}
                <p>
                  {
                    w.queue?.repairs.find((r) => r.event_id === stage.error_id)
                      ?.repair_prompt
                  }
                </p>
                <p className="muted">
                  Give one fresh application. For a coding repair, include an
                  assertion that checks your corrected rule on new data.
                </p>
                <label>
                  A fresh application
                  <textarea
                    rows={7}
                    value={repairAnswer}
                    onChange={(e) => {
                      if (repairVersion === null)
                        setRepairVersion(w.state?.repair?.revision ?? 0);
                      setRepairAnswer(e.target.value);
                      setRepairPassed(false);
                    }}
                  />
                </label>
                <div className="button-row">
                  {w.coach?.connection !== "connected" ? (
                    <CoachConnection status={w.coach} operate={w.operate} />
                  ) : (
                    <button
                      className="secondary"
                      disabled={
                        !repairAnswer.trim() || !!w.coach?.active_request
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
                  )}
                  {w.coach?.active_request && (
                    <button
                      className="secondary"
                      onClick={() =>
                        safely(() => w.operate("coach/interrupt", {}))
                      }
                    >
                      Stop coach
                    </button>
                  )}
                  {w.state?.repair?.check?.status === "running" ? (
                    <button
                      className="secondary"
                      onClick={() =>
                        safely(() => w.operate("practice/repair-stop", {}))
                      }
                    >
                      Stop repair test
                    </button>
                  ) : (
                    <button
                      className="secondary"
                      disabled={!repairAnswer.trim()}
                      onClick={() =>
                        safely(() => repairAction("practice/repair-check"))
                      }
                    >
                      Run repair assertions
                    </button>
                  )}
                </div>
                {w.state?.repair?.check && (
                  <p role="status">
                    {w.state.repair.check.message || "Checking repair…"}
                  </p>
                )}
                {w.state?.repair?.coach_review && (
                  <p role="status">
                    Coach judgment: {w.state.repair.coach_review.value}.{" "}
                    {w.state.repair.coach_review.explanation}
                  </p>
                )}
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={repairPassed}
                    onChange={(e) => setRepairPassed(e.target.checked)}
                  />
                  I reviewed the fresh application and confirmed it succeeds
                </label>
                <div className="button-row">
                  <button
                    className="secondary"
                    disabled={w.busy}
                    onClick={() =>
                      safely(async () => {
                        await saveRepair();
                        await w.operate("practice/pause", {});
                      })
                    }
                  >
                    Pause & save repair
                  </button>
                  {!w.state?.repair?.started_at && (
                    <button className="secondary" onClick={() => safely(start)}>
                      Resume repair
                    </button>
                  )}
                  <button
                    className="text-button"
                    onClick={() => exportText(repairAnswer, "repair-draft.txt")}
                  >
                    Export repair draft
                  </button>
                  <button
                    className="secondary"
                    onClick={() =>
                      safely(() =>
                        repairAction("practice/advance", {
                          skip: true,
                        }),
                      )
                    }
                  >
                    Skip for now
                  </button>
                  <button
                    className="primary"
                    disabled={!repairAnswer.trim() || w.busy}
                    onClick={() =>
                      safely(() =>
                        repairAction("practice/advance", {
                          passed: repairPassed,
                        }),
                      )
                    }
                  >
                    Save repair & continue
                    <ArrowRight size={16} />
                  </button>
                </div>
              </section>
            ) : (
              s && (
                <>
                  {s.timing_uncertain && (
                    <div className="notice warning">
                      <p>
                        {s.timing_uncertain.reason} You can correct total active
                        minutes when finishing.
                      </p>
                    </div>
                  )}
                  {(elapsed >= 45 * 60 ||
                    elapsed >=
                      (parent?.budget_minutes || s.budget_minutes) * 60) && (
                    <div className="notice">
                      <p>
                        {elapsed >=
                        (parent?.budget_minutes || s.budget_minutes) * 60
                          ? "Your session budget is reached. Your work is preserved; finish, pause, or continue at your own pace."
                          : "A focused stretch. A short break may help."}
                      </p>
                      <button
                        className="secondary small"
                        onClick={() =>
                          safely(() => w.operate("practice/pause", {}))
                        }
                      >
                        Pause
                      </button>
                    </div>
                  )}
                  {!s.phase_started_at && (
                    <div className="notice">
                      <Pause size={17} />
                      <p>Paused. No active time is being counted.</p>
                      <button
                        className="primary small"
                        onClick={() => safely(start)}
                      >
                        Resume
                      </button>
                    </div>
                  )}
                  <div className="practice-toolbar">
                    <span className="badge">
                      {s.assessment_mode === "practice"
                        ? "Guided practice"
                        : s.activity === "transfer"
                          ? "Unseen assessment"
                          : s.activity}
                    </span>
                    <label className="phase-select">
                      <span className="sr-only">Current study phase</span>
                      <select
                        value={s.phase}
                        onChange={(e) =>
                          safely(() =>
                            w.mutate("action/phase", { phase: e.target.value }),
                          )
                        }
                      >
                        {Object.entries(phases).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span className="spacer" />
                    <button
                      className="secondary small"
                      disabled={w.busy || running}
                      onClick={() =>
                        safely(() => w.operate("practice/pause", {}))
                      }
                    >
                      <Pause size={15} />
                      Pause
                    </button>
                    {stage?.type !== "recall" && (
                      <button
                        className="primary small"
                        disabled={w.busy || running}
                        onClick={() => safely(finishPreview)}
                      >
                        Finish / stop for today
                        <Check size={16} />
                      </button>
                    )}
                    <button
                      className="text-button"
                      onClick={() => {
                        if (coachVisible && pane === "coach") setPane("code");
                        setCoachVisible(!coachVisible);
                      }}
                    >
                      {coachVisible ? "Hide coach" : "Show coach"}
                    </button>
                  </div>
                  <div
                    className="practice-tabs"
                    role="tablist"
                    aria-label="Practice panels"
                  >
                    {panes.map((p) => (
                      <button
                        role="tab"
                        id={`practice-tab-${p}`}
                        aria-controls={`practice-panel-${p}`}
                        aria-selected={pane === p}
                        tabIndex={pane === p ? 0 : -1}
                        key={p}
                        className={pane === p ? "selected" : ""}
                        onClick={() => setPane(p)}
                        onKeyDown={(event) => {
                          if (
                            ![
                              "ArrowLeft",
                              "ArrowRight",
                              "Home",
                              "End",
                            ].includes(event.key)
                          )
                            return;
                          event.preventDefault();
                          const index = panes.indexOf(p);
                          const next =
                            panes[
                              event.key === "Home"
                                ? 0
                                : event.key === "End"
                                  ? panes.length - 1
                                  : (index +
                                      (event.key === "ArrowRight" ? 1 : -1) +
                                      panes.length) %
                                    panes.length
                            ];
                          setPane(next);
                          document
                            .getElementById(`practice-tab-${next}`)
                            ?.focus();
                        }}
                      >
                        {p.charAt(0).toUpperCase() + p.slice(1)}
                      </button>
                    ))}
                  </div>
                  <div
                    className={`practice-grid ${coachVisible ? "with-coach" : ""} tab-${pane}`}
                    style={
                      {
                        "--coach-width": `${coachWidth}px`,
                      } as React.CSSProperties
                    }
                  >
                    <section
                      className="problem-panel panel"
                      id="practice-panel-problem"
                      role="tabpanel"
                      aria-labelledby="practice-tab-problem"
                    >
                      <span className="eyebrow">THE PROBLEM</span>
                      <h2>{s.problem.title}</h2>
                      <p className="prompt">{s.problem.prompt}</p>
                      <code className="signature">{s.problem.signature}</code>
                      <h3>Constraints</h3>
                      <ul>
                        {s.problem.constraints.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                      <h3>Public examples</h3>
                      {s.problem.examples.map((e, i) => (
                        <div className="example" key={i}>
                          <small>Example {i + 1}</small>
                          <pre>{JSON.stringify(e.inputs, null, 2)}</pre>
                          <strong>Result</strong>
                          <pre>{JSON.stringify(e.output)}</pre>
                          {e.explanation && <p>{e.explanation}</p>}
                        </div>
                      ))}
                      {s.initial_reasoning && (
                        <details>
                          <summary>Your original reasoning</summary>
                          <p>{s.initial_reasoning.approach}</p>
                        </details>
                      )}
                      {s.revealed_hints?.map((h, i) => (
                        <div key={i} className="hint-box">
                          <small>Hint {i + 1}</small>
                          <p>{h}</p>
                        </div>
                      ))}
                    </section>
                    <section
                      className="work-panel"
                      id="practice-panel-code"
                      role="tabpanel"
                      aria-labelledby="practice-tab-code"
                    >
                      {!s.initial_reasoning && s.activity !== "learn" ? (
                        <div className="panel reasoning-card">
                          <Lightbulb size={28} />
                          <h2>Start with your idea.</h2>
                          <p>
                            What approach would you try, why does it fit, and
                            what should remain true—or which edge case matters?
                          </p>
                          <label htmlFor="reasoning">
                            A few plain-language sentences are enough.
                          </label>
                          <textarea
                            id="reasoning"
                            rows={6}
                            value={answer}
                            onChange={(e) => setAnswer(e.target.value)}
                            placeholder="I would try… because… One thing to check is…"
                          />
                          <details>
                            <summary>Recall self-report</summary>
                            <select
                              aria-label="Recall self-report"
                              value={quality}
                              onChange={(e) => setQuality(e.target.value)}
                            >
                              <option value="complete">
                                I reconstructed the core approach
                              </option>
                              <option value="partial">
                                I recalled part of it
                              </option>
                              <option value="failed">
                                I don't know the approach yet
                              </option>
                              <option value="novel">
                                This is my first approach to a new problem
                              </option>
                            </select>
                          </details>
                          <div className="button-row">
                            <button
                              className="primary"
                              disabled={w.busy || !answer.trim()}
                              onClick={() =>
                                safely(() =>
                                  w.mutate("action/reasoning", {
                                    answer,
                                    quality,
                                  }),
                                )
                              }
                            >
                              Record idea & open editor
                              <ArrowRight size={16} />
                            </button>
                            <button
                              className="text-button"
                              onClick={() => {
                                setAnswer("I don't know the approach yet.");
                                setQuality("failed");
                              }}
                            >
                              I don’t know yet
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          {s.worked_example && (
                            <details className="panel worked-example" open>
                              <summary>
                                Worked example · assisted learning
                              </summary>
                              <pre>{s.worked_example}</pre>
                              <p>{s.worked_explanation}</p>
                            </details>
                          )}
                          {w.conflict && (
                            <section className="panel conflict" role="alert">
                              <h3>Two versions need your review</h3>
                              <p>
                                Your browser draft is preserved. Compare it with
                                the code saved by another window before
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
                                  Keep my browser draft
                                </button>
                                <button
                                  className="text-button"
                                  onClick={() => exportText(w.draft)}
                                >
                                  Export my draft
                                </button>
                              </div>
                            </section>
                          )}
                          <div className="editor-shell panel">
                            <div className="editor-heading">
                              <span>
                                <Code2 size={16} />
                                solution.py
                              </span>
                              <span className="save-status" role="status">
                                {w.saveStatus}
                              </span>
                            </div>
                            <Suspense
                              fallback={
                                <div className="editor-loading">
                                  Opening editor…
                                </div>
                              }
                            >
                              <Editor
                                key={s.session_id}
                                sessionId={s.session_id}
                                value={w.draft}
                                onChange={w.change}
                              />
                            </Suspense>
                            <div className="editor-actions">
                              <span className="muted">
                                Python · your own implementation
                              </span>
                              <button
                                className="secondary small"
                                aria-label="Export code"
                                onClick={() => exportText(w.draft)}
                              >
                                <Download size={16} />
                              </button>
                              {running ? (
                                <button
                                  className="secondary"
                                  onClick={() =>
                                    safely(() => w.operate("action/stop", {}))
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
                                    safely(() => w.mutate("action/check"))
                                  }
                                >
                                  <Play size={15} />
                                  Run tests
                                </button>
                              )}
                            </div>
                          </div>
                          <section
                            className="panel test-panel"
                            aria-live="polite"
                          >
                            <div className="section-heading">
                              <h3>Checks</h3>
                              <span
                                className={
                                  currentCheck && checked?.all_passed
                                    ? "badge success"
                                    : "badge"
                                }
                              >
                                {!checked?.status
                                  ? "Not run"
                                  : running
                                    ? "Running"
                                    : !currentCheck
                                      ? "Stale · run again"
                                      : checked.status === "timeout"
                                        ? "Timed out"
                                        : checked.status === "stopped"
                                          ? "Stopped"
                                          : checked.all_passed
                                            ? "Passed"
                                            : "Needs another look"}
                              </span>
                            </div>
                            <p>
                              {currentCheck
                                ? checked?.message
                                : "Check your saved code to see its current result."}
                            </p>
                            {currentCheck &&
                              checked?.total_cases !== undefined && (
                                <small>
                                  {checked.passed_cases} / {checked.total_cases}{" "}
                                  checks passed. Tests do not establish
                                  explanation quality or efficiency.
                                </small>
                              )}
                            {currentCheck &&
                              checked?.public_failures?.map((f, i) => (
                                <p className="test-failure" key={i}>
                                  Public example {f.example}: {f.error}
                                </p>
                              ))}
                          </section>
                          <section className="panel help-panel">
                            <div className="button-row">
                              <button
                                className="secondary small"
                                onClick={() =>
                                  s.assessment_mode !== "practice"
                                    ? setHintChoice(true)
                                    : safely(() => w.mutate("action/hint"))
                                }
                              >
                                <Lightbulb size={15} />
                                Next hint
                              </button>
                              <button
                                className="text-button"
                                onClick={() =>
                                  s.assessment_mode !== "practice"
                                    ? setHintChoice(true)
                                    : safely(() =>
                                        w.mutate("action/worked-example"),
                                      )
                                }
                              >
                                Study a worked example
                              </button>
                            </div>
                            {hintChoice && s.assessment_mode !== "practice" && (
                              <div className="conversion-card">
                                <p>
                                  Substantive help ends the independent
                                  assessment and preserves your original work.
                                </p>
                                <div className="button-row">
                                  <button
                                    className="secondary small"
                                    onClick={() => setHintChoice(false)}
                                  >
                                    Continue independently
                                  </button>
                                  <button
                                    className="primary small"
                                    onClick={() =>
                                      safely(async () => {
                                        await convert();
                                        setHintChoice(false);
                                      })
                                    }
                                  >
                                    Switch to guided practice
                                  </button>
                                </div>
                              </div>
                            )}
                            {s.revealed_hints?.length ||
                            w.coach?.requests.some(
                              (r) =>
                                r.session_id === s.session_id &&
                                r.assistance &&
                                r.assistance !== "none",
                            ) ? (
                              <details>
                                <summary>
                                  Record a fresh reasoning retry
                                </summary>
                                <textarea
                                  aria-label="New reasoning attempt"
                                  value={retry}
                                  onChange={(e) => setRetry(e.target.value)}
                                  rows={3}
                                />
                                <button
                                  className="secondary small"
                                  onClick={() =>
                                    safely(() =>
                                      w.mutate("practice/retry", {
                                        answer: retry,
                                      }),
                                    )
                                  }
                                >
                                  Save retry
                                </button>
                              </details>
                            ) : null}
                          </section>
                        </>
                      )}
                      {stage?.type === "recall" && (
                        <section className="panel">
                          <h3>Keep this retrieval brief</h3>
                          <p>The full implementation review stays due.</p>
                          <div className="button-row">
                            <button
                              className="secondary"
                              onClick={() =>
                                safely(() =>
                                  w.mutate("practice/advance", {
                                    skip: true,
                                    answer,
                                  }),
                                )
                              }
                            >
                              Skip retrieval
                            </button>
                            <button
                              className="primary"
                              disabled={!s.initial_reasoning}
                              onClick={() =>
                                safely(() =>
                                  w.mutate("practice/advance", {
                                    answer,
                                    quality,
                                  }),
                                )
                              }
                            >
                              Continue session
                              <ArrowRight size={16} />
                            </button>
                          </div>
                        </section>
                      )}
                    </section>
                    {coachVisible && (
                      <>
                        <div
                          className="panel-resizer"
                          role="separator"
                          aria-label="Coach panel width"
                          aria-orientation="vertical"
                          aria-valuenow={coachWidth}
                          aria-valuemin={300}
                          aria-valuemax={500}
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "ArrowLeft")
                              setCoachWidth(Math.min(500, coachWidth + 20));
                            if (e.key === "ArrowRight")
                              setCoachWidth(Math.max(300, coachWidth - 20));
                          }}
                          onPointerDown={(e) => {
                            e.currentTarget.setPointerCapture(e.pointerId);
                          }}
                          onPointerMove={(e) => {
                            if (e.currentTarget.hasPointerCapture(e.pointerId))
                              setCoachWidth(
                                Math.max(
                                  300,
                                  Math.min(
                                    500,
                                    window.innerWidth - e.clientX - 24,
                                  ),
                                ),
                              );
                          }}
                        />
                        <CoachPanel
                          session={s}
                          status={w.coach}
                          send={w.send}
                          operate={w.operate}
                          convert={convert}
                        />
                      </>
                    )}
                  </div>
                </>
              )
            )}
          </div>
        )}
        {view === "progress" && (
          <div className="page">
            <header className="page-heading">
              <span className="eyebrow">EVIDENCE OVER STREAKS</span>
              <h1>What’s taking root.</h1>
              <p>Separate independent learning from progress made with help.</p>
            </header>
            <div className="signal-grid">
              <Signal
                title="Independent implementation"
                metric={w.progress?.independent}
                description="Includes minor help when core reasoning was independent"
              />
              <Signal
                title="Delayed implementation"
                metric={w.progress?.delayed}
                description="At least 24 hours after the prior attempt"
              />
              <Signal
                title="Unseen transfer"
                metric={w.progress?.unseen}
                description="First exposure, including attempts ended for help"
              />
            </div>
            <section className="panel progress-section">
              <h2>Topic readiness</h2>
              {w.progress?.topics.map((t) => (
                <div className="topic-row" key={t.id}>
                  <div>
                    <strong>{t.title || t.name || t.id}</strong>
                    <small>
                      {t.status === "planned"
                        ? "Planned content"
                        : `${Number(t.retained_core || 0)} / ${Number(t.core_count || 0)} core exercises retained`}
                    </small>
                  </div>
                  <span className={t.retained ? "badge success" : "badge"}>
                    {t.status === "planned"
                      ? "Planned"
                      : t.retained
                        ? "Retained"
                        : t.ready
                          ? "Ready to advance"
                          : "Building foundations"}
                  </span>
                </div>
              ))}
              <p className="muted">
                Retained requires independent implementations at least seven
                elapsed days apart and an unseen transfer pass. This is an
                initial policy, not a universal learning threshold.
              </p>
            </section>
            <div className="today-grid">
              <section className="panel">
                <h2>Time invested</h2>
                <strong className="large-number">
                  {Math.round(w.progress?.recorded_total_minutes || 0)}{" "}
                  <small>minutes recorded</small>
                </strong>
                {Object.entries(w.progress?.timing_seconds || {}).map(
                  ([phase, seconds]) => (
                    <div className="list-row" key={phase}>
                      <span>{phases[phase] || phase}</span>
                      <strong>{Math.round(seconds / 60)} min</strong>
                    </div>
                  ),
                )}
                {w.progress?.legacy_timing_incomplete && (
                  <p className="muted">
                    Historical timing is incomplete. Older repairs and
                    administration were not fully recorded.
                  </p>
                )}
              </section>
              <section className="panel">
                <h2>Assistance & baseline</h2>
                {Object.entries(w.progress?.assistance || {}).map(
                  ([level, count]) => (
                    <div className="list-row" key={level}>
                      <span>
                        {level === "none"
                          ? "No help recorded"
                          : level + " help"}
                      </span>
                      <strong>{count} attempts</strong>
                    </div>
                  ),
                )}
                <p>
                  {w.progress?.baseline_sessions || 0} / 12 guided sessions in
                  this workflow’s prospective baseline.
                </p>
                {w.progress?.cohort && (
                  <div className="cohort-metrics">
                    <p>
                      New workflow delayed implementation:{" "}
                      {metricLabel(w.progress.cohort.delayed)}. Unseen transfer:{" "}
                      {metricLabel(w.progress.cohort.unseen)}.
                    </p>
                    <p>
                      {w.progress.cohort.coaching_interruptions} interruptions
                      across {w.progress.cohort.coaching_turns} coaching turns;{" "}
                      {w.progress.cohort.help_escalations} deeper-help replies.
                    </p>
                    <p>
                      Coach response time:{" "}
                      {w.progress.cohort.latency_median_seconds == null
                        ? "not measured"
                        : `${w.progress.cohort.latency_median_seconds.toFixed(1)} seconds median (${w.progress.cohort.latency_samples} replies)`}
                      . This time is part of study time.
                    </p>
                  </div>
                )}
                <p>
                  Completion administration:{" "}
                  {w.progress?.administration_median_minutes == null
                    ? "not measured"
                    : `${w.progress.administration_median_minutes.toFixed(1)} min median · ${w.progress.administration_target_met ? "target met" : "above target"}`}
                  . Target: no more than 3 minutes.
                </p>
                <small>
                  Descriptive evidence, not proof of learning improvement.
                </small>
              </section>
            </div>
          </div>
        )}
        <footer>
          Built for understanding.
          <span>Python · Local practice · Optional Codex coaching</span>
        </footer>
      </main>
      {facts && s && (
        <Dialog cancel={cancelFinish}>
          <span className="eyebrow">KEEP THE USEFUL PART</span>
          <h2 id="finish-title">What will you take forward?</h2>
          <p>What would you recognize or do differently next time?</p>
          <label htmlFor="takeaway">Your takeaway</label>
          <textarea
            id="takeaway"
            rows={3}
            value={takeaway}
            onChange={(e) => setTakeaway(e.target.value)}
            placeholder="Next time, I’ll notice…"
          />
          <div className="completion-preview">
            <strong>
              {s.assessment_before_help
                ? "Independent assessment ended for help. Guided work is recorded separately."
                : facts.tests_passed
                  ? "Your saved code passed its checks."
                  : s.activity === "recall"
                    ? "Short retrieval; implementation scheduling stays separate."
                    : "An unfinished attempt is useful evidence. Your code will be preserved."}
            </strong>
            <p>
              Help: {facts.assistance_level}. Active time:{" "}
              {Math.round(elapsed / 60)} minutes.
            </p>
          </div>
          {review?.findings && (
            <section>
              <h3>Drafted from your evidence</h3>
              {review.findings
                .filter((f) => f.dimension !== "misconception")
                .map((f, i) => (
                  <p key={i}>
                    <strong>{f.dimension}:</strong>{" "}
                    {f.value === "unknown"
                      ? "not established"
                      : f.value === "success"
                        ? "supported by recorded evidence"
                        : "needs review"}
                    <small> · Coach judgment</small>
                  </p>
                ))}
            </section>
          )}
          <label className="checkbox">
            <input
              type="checkbox"
              checked={explained}
              onChange={(e) => setExplained(e.target.checked)}
            />
            Explanation of why the approach works is recorded
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={constraints}
              onChange={(e) => setConstraints(e.target.checked)}
            />
            Time and space requirements were checked
          </label>
          <details>
            <summary>Review ratings, evidence, and time</summary>
            <label>
              Recall rating
              <select
                value={rating}
                disabled={facts.recall_outcome === "unknown"}
                onChange={(e) => setRating(e.target.value)}
              >
                {facts.recall_outcome === "unknown" && (
                  <option value="unknown">
                    Unknown · scheduling unchanged
                  </option>
                )}
                <option value="again">
                  Again · specified recall was missing
                </option>
                {facts.recall_outcome === "success" && (
                  <>
                    <option value="hard">
                      Hard · recalled with substantial effort
                    </option>
                    <option value="good">Good · ordinary effort</option>
                    <option value="easy">Easy · fluent recall</option>
                  </>
                )}
              </select>
            </label>
            <p className="muted">{facts.rating_rationale}</p>
            <label>
              Total active minutes
              <input
                type="number"
                min="0.1"
                max="1440"
                step="0.1"
                value={actualMinutes}
                onChange={(e) => setActualMinutes(e.target.value)}
                placeholder={`${Math.round(elapsed / 60)} · calculated`}
              />
            </label>
            {finishFindings.map((f, i) => (
              <div className="finding" key={i}>
                <label>
                  {f.dimension}
                  <select
                    value={f.value}
                    onChange={(e) =>
                      setFinishFindings(
                        finishFindings.map((v, j) =>
                          j === i
                            ? {
                                ...v,
                                value: e.target.value as Finding["value"],
                                source: "learner_amendment",
                              }
                            : v,
                        ),
                      )
                    }
                  >
                    <option value="success">Supported</option>
                    <option value="failure">Not yet supported</option>
                    <option value="unknown">Unknown / disputed</option>
                  </select>
                </label>
                {f.evidence && <blockquote>{f.evidence}</blockquote>}
              </div>
            ))}
          </details>
          <p className="muted">
            Publication includes your code, reviewed learning evidence, and
            brief takeaway. Full coach conversations stay private.{" "}
            {w.state.unpublished_count > 0
              ? `Also includes ${w.state.unpublished_count} earlier saved item(s).`
              : ""}
          </p>
          <p className="muted">
            Destination: github.com/david1534/leetcode-learning-system
          </p>
          <div className="button-row">
            <button
              className="secondary"
              disabled={w.busy || !takeaway.trim()}
              onClick={() => safely(() => finish(false))}
            >
              Finish locally
            </button>
            <button
              className="primary"
              disabled={w.busy || !takeaway.trim()}
              onClick={() => safely(() => finish(true))}
            >
              Publish & finish
              <ArrowRight size={16} />
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
