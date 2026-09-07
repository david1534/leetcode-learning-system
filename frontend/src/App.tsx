import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Code2,
  ExternalLink,
  Lightbulb,
  Pause,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Square,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import Editor from "./Editor";
import { api, ApiError, formatTime, metricLabel, reconcileDraft } from "./api";

type View = "today" | "practice" | "progress";
const phaseLabels: Record<string, string> = {
  recall: "Thinking & recall",
  implementation: "Coding",
  explanation: "Testing & explanation",
  administration: "Finishing up",
  learning: "Learning",
  repair: "Repair",
};

export default function App() {
  const [view, setView] = useState<View>("today"),
    [state, setState] = useState<any>(null),
    [queue, setQueue] = useState<any>(null),
    [progress, setProgress] = useState<any>(null);
  const [minutes, setMinutes] = useState(60),
    [includeNew, setIncludeNew] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [draft, setDraft] = useState(""),
    [saveStatus, setSaveStatus] = useState("Saved"),
    [conflict, setConflict] = useState(false);
  const [answer, setAnswer] = useState(""),
    [quality, setQuality] = useState("complete"),
    [facts, setFacts] = useState<any>(null),
    [takeaway, setTakeaway] = useState(""),
    [rating, setRating] = useState("good"),
    [explained, setExplained] = useState(false),
    [constraints, setConstraints] = useState(false),
    [actualMinutes, setActualMinutes] = useState("");
  const [repair, setRepair] = useState<any>(null),
    [application, setApplication] = useState(""),
    [repairPassed, setRepairPassed] = useState(false),
    [repairHelp, setRepairHelp] = useState("none");
  const latest = useRef<any>(null),
    dirty = useRef(false),
    draftRef = useRef(""),
    sessionId = useRef(""),
    saving = useRef<Promise<void> | null>(null),
    conflictRef = useRef(false),
    base = useRef({ revision: 0, digest: "" });
  const [tick, setTick] = useState(0);
  const receivedAt = useRef(Date.now());
  const applyState = (next: any) => {
    latest.current = next;
    receivedAt.current = Date.now();
    setState(next);
    const s = next.session;
    if (s?.code !== null && s?.code !== undefined) {
      if (sessionId.current !== s.session_id) {
        sessionId.current = s.session_id;
        base.current = { revision: s.revision, digest: s.code_digest };
        dirty.current = false;
        conflictRef.current = false;
        setConflict(false);
        setAnswer("");
        let pending: any;
        try {
          pending = JSON.parse(
            localStorage.getItem("draft-" + s.session_id) || "null",
          );
        } catch {
          pending = null;
        }
        if (pending && pending.code !== s.code) {
          dirty.current = true;
          draftRef.current = pending.code;
          setDraft(pending.code);
          base.current = { revision: s.revision, digest: pending.base };
          if (pending.base !== s.code_digest) {
            conflictRef.current = true;
            setConflict(true);
          }
          setSaveStatus("Recovered draft");
        } else {
          draftRef.current = s.code;
          setDraft(s.code);
        }
      } else {
        if (dirty.current && base.current.digest !== s.code_digest) {
          conflictRef.current = true;
          setConflict(true);
        }
        if (!dirty.current)
          base.current = { revision: s.revision, digest: s.code_digest };
        const text = reconcileDraft(draftRef.current, s.code, dirty.current);
        draftRef.current = text;
        setDraft(text);
      }
    }
  };
  const refresh = async () => {
    const [s, q, p] = await Promise.all([
      api("state"),
      api(`queue?minutes=${minutes}&include_new=${includeNew}`),
      api("progress"),
    ]);
    applyState(s);
    setQueue(q);
    setProgress(p);
  };
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [minutes, includeNew]);
  useEffect(() => {
    const timer = setInterval(
      () =>
        api("state")
          .then(applyState)
          .catch(() => {}),
      2000,
    );
    const clock = setInterval(() => setTick((x) => x + 1), 1000);
    return () => {
      clearInterval(timer);
      clearInterval(clock);
    };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty.current) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
  const save = async (): Promise<void> => {
    if (saving.current) {
      await saving.current;
      if (dirty.current) return save();
      return;
    }
    if (!dirty.current) return;
    if (conflictRef.current)
      throw new Error(
        "Compare your recovered draft with the saved version before continuing.",
      );
    const text = draftRef.current,
      s = latest.current?.session;
    if (!s) return;
    const promise = (async () => {
      try {
        setSaveStatus("Saving…");
        const response = await api("action/save", {
          code: text,
          revision: base.current.revision,
          code_digest: base.current.digest,
        });
        base.current = {
          revision: response.session.revision,
          digest: response.session.code_digest,
        };
        dirty.current = draftRef.current !== text;
        applyState(response);
        setSaveStatus(dirty.current ? "Unsaved changes" : "Saved");
        if (!dirty.current) localStorage.removeItem("draft-" + s.session_id);
        else
          localStorage.setItem(
            "draft-" + s.session_id,
            JSON.stringify({
              code: draftRef.current,
              base: response.session.code_digest,
            }),
          );
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
    saving.current = promise;
    await promise;
  };
  useEffect(() => {
    if (!dirty.current || conflict) return;
    const timer = setTimeout(
      () => save().catch((e) => setError(e.message)),
      700,
    );
    return () => clearTimeout(timer);
  }, [draft, conflict]);
  const changeCode = (text: string) => {
    if (!dirty.current && latest.current?.session)
      base.current = {
        revision: latest.current.session.revision,
        digest: latest.current.session.code_digest,
      };
    draftRef.current = text;
    setDraft(text);
    dirty.current = true;
    setSaveStatus("Unsaved changes");
    const s = latest.current?.session;
    if (s)
      localStorage.setItem(
        "draft-" + s.session_id,
        JSON.stringify({ code: text, base: base.current.digest }),
      );
  };
  const action = async (op: string, data: any = {}) => {
    setBusy(true);
    setError("");
    try {
      await save();
      const result = await api("action/" + op, data);
      if (result.session !== undefined) applyState(result);
      await refresh();
      return result;
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy(false);
    }
  };
  const safely = (fn: () => Promise<unknown>) => {
    fn().catch(() => {});
  };
  const start = async (id?: string, activity?: string) => {
    const result = await action("start", {
      ...(id ? { problem_id: id } : {}),
      ...(activity ? { activity } : {}),
      minutes,
      include_new: includeNew,
    });
    if (result.session) setView("practice");
    else setToast(result.message || "No activity is available.");
  };
  useEffect(() => {
    if (!facts && !repair) return;
    const previous = document.activeElement as HTMLElement | null;
    const modal = document.querySelector<HTMLElement>('[role="dialog"]');
    const controls = () =>
      Array.from(
        modal?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input,select,textarea,[tabindex="0"]',
        ) || [],
      );
    controls()[0]?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === "Tab") {
        const nodes = controls(),
          first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [!!facts, !!repair]);
  const beforeFinishPhase = useRef("implementation");
  const cancelFinish = async () => {
    setFacts(null);
    await action("phase", { phase: beforeFinishPhase.current });
  };
  const finishPreview = async () => {
    beforeFinishPhase.current = latest.current.session.phase;
    await action("phase", { phase: "administration" });
    const result = await action("evaluate");
    setFacts(result);
    setRating(result.recommended_rating);
    setActualMinutes("");
    setTakeaway("");
    setExplained(false);
    setConstraints(false);
  };
  const finish = async (publish: boolean) => {
    const s = latest.current.session;
    await action("finish", {
      session_id: s.session_id,
      rating,
      takeaway,
      explained,
      constraints_met: constraints,
      minutes: Number(actualMinutes) || undefined,
      publish,
      revision: facts.revision,
      stopped:
        ["implement", "transfer"].includes(s.activity) && !facts.tests_passed,
    });
    localStorage.removeItem("draft-" + s.session_id);
    setFacts(null);
    setView("today");
    setToast(
      publish
        ? "Session saved. Publication status is shown on Today."
        : "Session saved on this computer.",
    );
  };
  const beginRepair = async (gate: any) => {
    await action("begin-repair", { error_id: gate.event_id });
    setRepair(gate);
    setApplication(latest.current?.repair?.application || "");
    setRepairPassed(false);
    setRepairHelp("none");
  };
  const s = state?.session;
  const elapsed =
    (s?.elapsed_seconds || 0) +
    (s?.phase_started_at ? (Date.now() - receivedAt.current) / 1000 : 0) +
    tick * 0;
  const running = state?.check?.status === "running";
  const savedCheck =
    s && state?.check?.session_id === s.session_id ? state.check : null;
  const currentCheck =
    savedCheck && s && savedCheck.code_digest !== s.code_digest
      ? {
          ...savedCheck,
          status: "stale",
          all_passed: false,
          message: "Code changed since the check; run again.",
        }
      : savedCheck;
  const formatCount = (n: number) => String(n || 0).padStart(2, "0");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("today");
          }}
        >
          <span className="brand-mark">
            <Code2 size={23} />
          </span>
          <span>
            practice<span className="brand-room">room</span>
          </span>
        </a>
        <div className="sidebar-caption">A LITTLE PRACTICE. LASTING SKILL.</div>
        <nav aria-label="Main navigation">
          {(
            [
              { id: "today", label: "Today", icon: CalendarDays },
              { id: "practice", label: "Practice", icon: Code2 },
              { id: "progress", label: "Progress", icon: TrendingUp },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={"nav-item " + (view === id ? "selected" : "")}
              aria-current={view === id ? "page" : undefined}
              onClick={() => setView(id)}
            >
              <Icon size={19} />
              {label}
              {id === "practice" && s && <span className="live-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <BookOpen size={20} />
          <p>
            Understand the pattern.
            <br />
            Make it your own.
          </p>
          <span>Independent thinking comes first.</span>
        </div>
        <div className="sidebar-bottom">
          <span
            className={
              "status-dot " + (state?.sync?.status === "pending" ? "amber" : "")
            }
          />
          <span>
            {state?.sync?.status === "pending"
              ? "Sync pending"
              : "Local workspace"}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh workspace"
            onClick={() => refresh().catch((e) => setError(e.message))}
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>YOUR LEARNING WORKSPACE</span>
          <div>
            <span className="subtle-pill">
              <ShieldCheck size={14} /> Thinking stays yours
            </span>
            <span className="avatar">YOU</span>
          </div>
        </header>
        {error && (
          <div className="notice error" role="alert">
            <span>{error}</span>
            <button
              className="icon-button"
              onClick={() => setError("")}
              aria-label="Dismiss error"
            >
              <X size={17} />
            </button>
          </div>
        )}
        {!state || !queue ? (
          <div className="loading">Opening your practice room…</div>
        ) : (
          <>
            {view === "today" && (
              <div className="page today-page">
                <div className="page-heading">
                  <div className="eyebrow">
                    {new Date().toLocaleDateString(undefined, {
                      weekday: "long",
                      month: "long",
                      day: "numeric",
                    })}
                  </div>
                  <h1>
                    Small steps.
                    <br />
                    <span>Deeper understanding.</span>
                  </h1>
                  <p>A clear next step, with room to think.</p>
                </div>
                {state.remote_attempts?.length > 0 && (
                  <section className="plain-card">
                    <h3>Choose the saved attempt to resume</h3>
                    <p>Each version is preserved.</p>
                    {state.remote_attempts.map((branch: string) => (
                      <button
                        className="secondary small"
                        key={branch}
                        onClick={() =>
                          safely(() => action("choose-attempt", { branch }))
                        }
                      >
                        {branch}
                      </button>
                    ))}
                  </section>
                )}
                <div className="today-grid">
                  <section className="focus-card">
                    <div className="card-top">
                      <span className="eyebrow">
                        <span className="live-dot" />{" "}
                        {s ? "READY WHEN YOU ARE" : "TODAY’S FOCUS"}
                      </span>
                      <span className="pill">
                        <Clock3 size={14} />
                        {s?.budget_minutes || minutes} min
                      </span>
                    </div>
                    <div className="focus-illustration" aria-hidden="true">
                      <span className="orbit one" />
                      <span className="orbit two" />
                      <span className="orbit three" />
                      <div className="orbit-center">
                        <Code2 size={38} />
                      </div>
                      <div className="satellite">
                        <Check size={16} />
                      </div>
                    </div>
                    <h2>
                      {s
                        ? "Pick up where you left off."
                        : queue.main
                          ? queue.activity === "transfer"
                            ? "Try something unfamiliar."
                            : queue.activity === "recall"
                              ? "Bring an idea back."
                              : "Build a little more fluency."
                          : "A little room to consolidate."}
                    </h2>
                    <p>
                      {s
                        ? "Your draft, reasoning, and coaching evidence are saved together."
                        : queue.reason}
                    </p>
                    <div className="focus-bottom">
                      <button
                        className="primary"
                        disabled={busy || (!s && !queue.main)}
                        onClick={() => safely(() => start())}
                      >
                        {s ? <Play size={17} /> : <ArrowRight size={18} />}{" "}
                        {s ? "Resume practice" : "Start practice"}
                      </button>
                      <span>{s ? s.activity : "One problem at a time"}</span>
                    </div>
                  </section>
                  <section className="session-card">
                    <div className="card-top">
                      <h3>Your session</h3>
                      <Clock3 size={19} />
                    </div>
                    <label className="field-label" htmlFor="session-budget">
                      Time available
                    </label>
                    <select
                      id="session-budget"
                      value={minutes}
                      onChange={(e) => setMinutes(Number(e.target.value))}
                    >
                      <option value={15}>15 minutes · a short revisit</option>
                      <option value={30}>30 minutes · a focused step</option>
                      <option value={45}>45 minutes · steady practice</option>
                      <option value={60}>60 minutes · room to explore</option>
                      <option value={90}>
                        90 minutes · an extended session
                      </option>
                    </select>
                    <div className="session-timeline">
                      {[
                        ["01", "Recall & repair", "Bring back what matters"],
                        ["02", "Think & implement", "Work through one problem"],
                        ["03", "Explain & reflect", "Keep the useful lesson"],
                      ].map(([n, title, copy]) => (
                        <div className="timeline-row" key={n}>
                          <span>{n}</span>
                          <div>
                            <strong>{title}</strong>
                            <small>{copy}</small>
                          </div>
                        </div>
                      ))}
                    </div>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={includeNew}
                        onChange={(e) => setIncludeNew(e.target.checked)}
                      />{" "}
                      Allow new material on weekends
                    </label>
                    <p className="small-note">
                      A break is suggested at 45 active minutes. Your work stays
                      saved.
                    </p>
                  </section>
                </div>
                <div className="section-heading">
                  <h2>A few useful signals</h2>
                  <button
                    className="text-button"
                    onClick={() => setView("progress")}
                  >
                    View progress <ArrowRight size={16} />
                  </button>
                </div>
                <div className="signal-grid">
                  <div className="signal-card">
                    <div className="signal-icon">
                      <RefreshCw size={20} />
                    </div>
                    <strong>{formatCount(queue.due.length)}</strong>
                    <div>
                      <h3>Reviews waiting</h3>
                      <p>Scheduled by your recall history</p>
                    </div>
                  </div>
                  <div className="signal-card">
                    <div className="signal-icon green">
                      <Target size={20} />
                    </div>
                    <strong>{formatCount(queue.repairs.length)}</strong>
                    <div>
                      <h3>Skills to revisit</h3>
                      <p>Small repairs, specific to a skill</p>
                    </div>
                  </div>
                  <div className="signal-card">
                    <div className="signal-icon peach">
                      <TrendingUp size={20} />
                    </div>
                    <strong>
                      {progress?.baseline_sessions || 0}
                      <small>/12</small>
                    </strong>
                    <div>
                      <h3>Baseline sessions</h3>
                      <p>Learning what works for you</p>
                    </div>
                  </div>
                </div>
                {(queue.short_recall.length > 0 ||
                  queue.repairs.length > 0) && (
                  <section className="plain-card review-list">
                    <div className="section-heading">
                      <h3>Before the main problem</h3>
                      <span className="muted">Up to 10 minutes</span>
                    </div>
                    {queue.repairs.map((g: any) => (
                      <div className="list-row" key={g.event_id}>
                        <div className="row-icon">
                          <Lightbulb size={17} />
                        </div>
                        <div>
                          <strong>{g.skill}</strong>
                          <small>
                            {g.eligible
                              ? "Apply the corrected rule to a fresh example"
                              : "Available after a full 24-hour delay"}
                          </small>
                        </div>
                        <button
                          className="secondary small"
                          disabled={!g.eligible || busy}
                          onClick={() => safely(() => beginRepair(g))}
                        >
                          Repair <ChevronRight size={14} />
                        </button>
                      </div>
                    ))}
                    {queue.short_recall.map((p: any, i: number) => (
                      <div className="list-row" key={p.id}>
                        <div className="row-icon">
                          <RefreshCw size={17} />
                        </div>
                        <div>
                          <strong>Recall an earlier approach · {i + 1}</strong>
                          <small>
                            Full implementation remains separately scheduled
                          </small>
                        </div>
                        <button
                          className="secondary small"
                          disabled={!!s || busy}
                          onClick={() => safely(() => start(p.id, "recall"))}
                        >
                          Recall <ChevronRight size={14} />
                        </button>
                      </div>
                    ))}
                  </section>
                )}
                {state.completion && !s && (
                  <section className="notice completion">
                    <CheckCircle2 size={22} />
                    <div>
                      <strong>Session safely recorded</strong>
                      <p>{state.completion.message}</p>
                    </div>
                    {!state.completion.published && (
                      <div className="button-row">
                        <button
                          className="secondary small"
                          onClick={() =>
                            safely(() =>
                              action("publish", {
                                session_id: state.completion.session_id,
                                include_saved: true,
                              }),
                            )
                          }
                        >
                          Publish saved learning ({state.unpublished_count || 1}
                          )
                        </button>
                        <button
                          className="text-button"
                          onClick={() => safely(() => action("keep-local"))}
                        >
                          Keep local
                        </button>
                      </div>
                    )}
                  </section>
                )}
                <details className="plain-card">
                  <summary>Explore available learning support</summary>
                  <p className="muted">
                    Worked examples and incomplete examples build understanding.
                    They do not count as independent implementation.
                  </p>
                  <div className="support-grid">
                    {queue.support.map((p: any) => (
                      <button
                        key={p.id}
                        disabled={!!s || busy}
                        className="support-item"
                        onClick={() => safely(() => start(p.id, "learn"))}
                      >
                        <BookOpen size={17} />
                        <span>
                          {p.title}
                          <small>
                            {p.kind} · {p.estimated_minutes} min
                          </small>
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>
                </details>
                {state.sync.status === "pending" && (
                  <div className="notice">
                    <span>
                      <strong>Saved locally.</strong> {state.sync.message}
                    </span>
                    <button
                      className="secondary small"
                      disabled={busy}
                      onClick={() => safely(() => action("sync"))}
                    >
                      Retry sync
                    </button>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => safely(() => action("recover"))}
                    >
                      Preserve divergent draft
                    </button>
                  </div>
                )}
                <footer>
                  Built for understanding, not streaks.
                  <span>Python · Local practice · Codex coaching</span>
                </footer>
              </div>
            )}
            {view === "practice" && (
              <div className="page practice-page">
                <div className="compact-heading">
                  <div>
                    <div className="eyebrow">SPACE TO THINK</div>
                    <h1>Your next good attempt.</h1>
                  </div>
                  {s && (
                    <div className="timer" aria-label="Active study time">
                      <Clock3 size={18} />
                      {formatTime(elapsed)}
                      <small>/ {s.budget_minutes} min</small>
                    </div>
                  )}
                </div>
                {!s ? (
                  <section className="empty-card">
                    <Code2 size={35} />
                    <h2>Your next step is ready.</h2>
                    <p>
                      Start from Today to get a problem suited to your current
                      progress.
                    </p>
                    <button
                      className="primary"
                      onClick={() => setView("today")}
                    >
                      Go to Today <ArrowRight size={17} />
                    </button>
                  </section>
                ) : (
                  <>
                    {(s.break_suggested || s.budget_reached) && (
                      <div className="notice">
                        <Clock3 size={19} />
                        <span>
                          {s.budget_reached
                            ? "You’ve reached your session budget. Your work is saved."
                            : "You’ve had a focused stretch. A short break may help."}
                        </span>
                        <button
                          className="secondary small"
                          disabled={busy}
                          onClick={() => safely(() => action("pause"))}
                        >
                          Pause
                        </button>
                      </div>
                    )}
                    {!s.phase_started_at && (
                      <div className="notice">
                        <Pause size={18} />
                        <span>
                          Paused. Resume when you’re ready; no active time is
                          being counted.
                        </span>
                        <button
                          className="primary small"
                          disabled={busy}
                          onClick={() => safely(() => start())}
                        >
                          Resume
                        </button>
                      </div>
                    )}
                    <div className="practice-toolbar">
                      <span className="pill">{s.activity.toUpperCase()}</span>
                      <label>
                        Working on{" "}
                        <select
                          aria-label="Current study phase"
                          value={s.phase}
                          onChange={(e) =>
                            safely(() =>
                              action("phase", { phase: e.target.value }),
                            )
                          }
                        >
                          {Object.entries(phaseLabels).map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="spacer" />
                      <button
                        className="secondary small"
                        disabled={busy || running}
                        onClick={() => safely(() => action("pause"))}
                      >
                        <Pause size={15} /> Pause & sync
                      </button>
                      <button
                        className="primary small"
                        disabled={busy || running}
                        onClick={() => safely(finishPreview)}
                      >
                        <Check size={16} /> Finish / stop for today
                      </button>
                    </div>
                    <div className="practice-grid">
                      <section className="problem-panel plain-card">
                        <span className="eyebrow">THE PROBLEM</span>
                        <h2>{s.problem.title}</h2>
                        <p className="prompt">{s.problem.prompt}</p>
                        <code className="signature">{s.problem.signature}</code>
                        <details open>
                          <summary>Constraints</summary>
                          <ul>
                            {s.problem.constraints.map((c: string) => (
                              <li key={c}>{c}</li>
                            ))}
                          </ul>
                        </details>
                        {s.problem.examples.map((e: any, i: number) => (
                          <div className="example" key={i}>
                            <h4>Example {i + 1}</h4>
                            <pre>
                              {Object.entries(e.inputs)
                                .map(
                                  ([key, value]) =>
                                    key + " = " + JSON.stringify(value),
                                )
                                .join("\n")}
                              {"\n"}Output: {JSON.stringify(e.output)}
                            </pre>
                            <p>{e.explanation}</p>
                          </div>
                        ))}
                        {s.initial_reasoning && (
                          <details>
                            <summary>Your initial reasoning</summary>
                            <p>{s.initial_reasoning.approach}</p>
                          </details>
                        )}
                        {s.revealed_hints?.length > 0 && (
                          <div className="hint-box">
                            <h4>
                              <Lightbulb size={16} /> Revealed hints
                            </h4>
                            {s.revealed_hints.map((h: string, i: number) => (
                              <p key={i}>
                                {i + 1}. {h}
                              </p>
                            ))}
                          </div>
                        )}
                        {s.problem.related_url && (
                          <a
                            className="text-button"
                            href={s.problem.related_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Related practice <ExternalLink size={14} />
                          </a>
                        )}
                      </section>
                      <section className="work-panel">
                        {!s.initial_reasoning && s.activity !== "learn" ? (
                          <div className="reasoning-card plain-card">
                            <div className="round-icon">
                              <Lightbulb size={25} />
                            </div>
                            <h2>Start with your idea.</h2>
                            <p>
                              What approach would you try, why does it fit, and
                              what should remain true—or which edge case
                              matters?
                            </p>
                            <label className="field-label" htmlFor="reasoning">
                              A few plain-language sentences are enough.
                            </label>
                            <textarea
                              id="reasoning"
                              value={answer}
                              onChange={(e) => setAnswer(e.target.value)}
                              placeholder="I would try… because… One thing to check is…"
                              rows={7}
                            />
                            <label
                              className="field-label"
                              htmlFor="recall-quality"
                            >
                              How did that recall feel?
                            </label>
                            <select
                              id="recall-quality"
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
                                I don’t know the approach yet
                              </option>
                              <option value="novel">
                                This is my own first approach to a new problem
                              </option>
                            </select>
                            <button
                              className="primary"
                              disabled={busy || !answer.trim()}
                              onClick={() =>
                                safely(() =>
                                  action("reasoning", {
                                    answer,
                                    quality,
                                    revision: s.revision,
                                  }),
                                )
                              }
                            >
                              Record idea & open editor <ArrowRight size={17} />
                            </button>
                            <div className="coach-note">
                              <BookOpen size={17} />
                              <span>
                                Unsure is a useful starting point. Codex can
                                help you take the next step.
                              </span>
                            </div>
                          </div>
                        ) : (
                          <>
                            {s.worked_example && (
                              <details className="plain-card" open>
                                <summary>
                                  Worked example · trace and explain
                                </summary>
                                <pre>{s.worked_example}</pre>
                              </details>
                            )}
                            {s.activity === "learn" && (
                              <div className="notice">
                                <BookOpen size={19} />
                                <span>{s.worked_explanation}</span>
                              </div>
                            )}
                            {conflict && (
                              <div className="conflict-card" role="alert">
                                <h3>Two versions need your attention.</h3>
                                <p>
                                  Your draft is preserved. Review the saved
                                  version before choosing.
                                </p>
                                <details>
                                  <summary>See saved version</summary>
                                  <pre>{s.code}</pre>
                                </details>
                                <div className="button-row">
                                  <button
                                    className="secondary small"
                                    onClick={() => {
                                      dirty.current = false;
                                      conflictRef.current = false;
                                      setConflict(false);
                                      draftRef.current = s.code;
                                      setDraft(s.code);
                                      localStorage.removeItem(
                                        "draft-" + s.session_id,
                                      );
                                      setSaveStatus("Saved");
                                    }}
                                  >
                                    Use saved version
                                  </button>
                                  <button
                                    className="primary small"
                                    onClick={() => {
                                      base.current = {
                                        revision: s.revision,
                                        digest: s.code_digest,
                                      };
                                      conflictRef.current = false;
                                      setConflict(false);
                                      safely(save);
                                    }}
                                  >
                                    Save my draft instead
                                  </button>
                                </div>
                              </div>
                            )}
                            <div className="editor-frame">
                              <div className="editor-header">
                                <span>
                                  <Code2 size={15} /> current.py
                                </span>
                                <span>
                                  <span className="status-dot" />
                                  {saveStatus}
                                </span>
                              </div>
                              <Editor value={draft} onChange={changeCode} />
                              <div className="editor-footer">
                                <span>Python · 4 spaces</span>
                                <span>Autosaved locally</span>
                              </div>
                            </div>
                            <div className="button-row check-actions">
                              <button
                                className="primary"
                                disabled={busy || running || conflict}
                                onClick={() => safely(() => action("check"))}
                              >
                                <Play size={16} />
                                {running ? "Checking…" : "Check solution"}
                              </button>
                              {running && (
                                <button
                                  className="secondary"
                                  onClick={() => safely(() => action("stop"))}
                                >
                                  <Square size={15} /> Stop check
                                </button>
                              )}
                              <button
                                className="secondary"
                                disabled={busy || running}
                                onClick={() =>
                                  safely(() =>
                                    action("hint", { retried: false }),
                                  )
                                }
                              >
                                <Lightbulb size={16} /> Next hint
                              </button>
                              {s.hints_used > 0 && (
                                <button
                                  className="text-button"
                                  disabled={busy}
                                  onClick={() =>
                                    safely(() =>
                                      action("hint", { retried: true }),
                                    )
                                  }
                                >
                                  I retried the reasoning
                                </button>
                              )}
                            </div>
                            {currentCheck && (
                              <div
                                className={
                                  "check-result " +
                                  (currentCheck.all_passed ? "passed" : "")
                                }
                                role="status"
                              >
                                <strong>
                                  {currentCheck.status === "running"
                                    ? "Checking saved code…"
                                    : currentCheck.all_passed
                                      ? "All cases passed"
                                      : currentCheck.status === "complete"
                                        ? `${currentCheck.passed_cases} of ${currentCheck.total_cases} cases passed`
                                        : currentCheck.message}
                                </strong>
                                {currentCheck.status === "complete" && (
                                  <p>
                                    {currentCheck.all_passed
                                      ? "Correctness is one part of the evidence. Explain why your approach works."
                                      : "Ask Codex to discuss one issue, then try again."}
                                  </p>
                                )}
                                {currentCheck.public_failures?.map(
                                  (f: any, i: number) => (
                                    <small key={i}>
                                      Example {f.example}: {f.error}
                                    </small>
                                  ),
                                )}
                              </div>
                            )}
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() =>
                                safely(() => action("worked-example"))
                              }
                            >
                              I’m stuck · study a worked example
                            </button>
                            <div className="coach-note">
                              <BookOpen size={18} />
                              <div>
                                <strong>Your coach is in Codex.</strong>
                                <p>
                                  Ask “review my approach” or “help me with one
                                  issue.” Codex reads this same session; no
                                  copying of code or problem IDs is needed.
                                </p>
                              </div>
                            </div>
                          </>
                        )}
                      </section>
                    </div>
                  </>
                )}
              </div>
            )}
            {view === "progress" && progress && (
              <div className="page">
                <div className="page-heading">
                  <div className="eyebrow">EVIDENCE, NOT A STREAK</div>
                  <h1>See what’s becoming yours.</h1>
                  <p>
                    Independent thinking, retained skills, and unfamiliar
                    problems.
                  </p>
                </div>
                <div className="metric-grid">
                  {[
                    ["Independent implementation", progress.independent, Code2],
                    ["Delayed implementation", progress.delayed, RefreshCw],
                    ["Unseen transfer", progress.unseen, Target],
                  ].map(([title, metric, Icon]: any) => (
                    <section className="plain-card metric" key={title}>
                      <Icon size={21} />
                      <h3>{title}</h3>
                      <strong>{metricLabel(metric)}</strong>
                      <p>
                        {metric.total
                          ? `${Math.round(metric.rate * 100)}% independent passes · ${metric.total} measured attempts`
                          : "New evidence will appear here after practice."}
                      </p>
                    </section>
                  ))}
                </div>
                <section className="plain-card baseline">
                  <div>
                    <span className="eyebrow">YOUR FIRST 12 SESSIONS</span>
                    <h3>Establishing a useful baseline</h3>
                    <p>
                      {progress.baseline_sessions} of 12 sessions recorded with
                      the new evidence model. This does not yet prove that the
                      app improves learning.
                    </p>
                  </div>
                  <div className="baseline-dots">
                    {Array.from({ length: 12 }, (_, i) => (
                      <span
                        key={i}
                        className={
                          i < progress.baseline_sessions ? "filled" : ""
                        }
                      />
                    ))}
                  </div>
                </section>
                <div className="section-heading">
                  <h2>Your foundation</h2>
                  <span className="muted">Ready to advance ≠ retained</span>
                </div>
                <div className="topic-grid">
                  {progress.topics.map((t: any) => (
                    <section
                      className={
                        "topic-card " +
                        (t.status === "planned" ? "planned" : "")
                      }
                      key={t.id}
                    >
                      <div>
                        <BookOpen size={20} />
                        <span className="pill">
                          {t.status === "planned"
                            ? "Planned"
                            : t.retained
                              ? "Retained"
                              : t.ready
                                ? "Ready to advance"
                                : "Building"}
                        </span>
                      </div>
                      <h3>{t.title}</h3>
                      {t.status !== "planned" && (
                        <>
                          <div className="progress-track">
                            <span
                              style={{
                                width: `${t.core_count ? (t.retained_core / t.core_count) * 100 : 0}%`,
                              }}
                            />
                          </div>
                          <p>
                            {t.retained_core} / {t.core_count} core exercises
                            retained
                          </p>
                          <small>
                            {t.unseen_transfer_passed
                              ? "✓ Unseen transfer passed"
                              : "Unseen transfer still to establish"}
                          </small>
                        </>
                      )}
                    </section>
                  ))}
                </div>
                <div className="metric-grid two">
                  <section className="plain-card">
                    <h3>Where your time goes</h3>
                    {Object.entries(progress.timing_seconds).length ? (
                      Object.entries(progress.timing_seconds).map(
                        ([phase, seconds]: any) => (
                          <div className="data-row" key={phase}>
                            <span>{phaseLabels[phase] || phase}</span>
                            <strong>{Math.round(seconds / 60)} min</strong>
                          </div>
                        ),
                      )
                    ) : (
                      <p className="muted">
                        Phase timing begins with your next session.
                      </p>
                    )}
                    <div className="data-row">
                      <span>Total recorded study time</span>
                      <strong>
                        {Math.round(progress.recorded_total_minutes)} min
                      </strong>
                    </div>
                    {progress.legacy_timing_incomplete && (
                      <p className="small-note">
                        Historical timing is incomplete: older repairs and other
                        work may be missing.
                      </p>
                    )}
                    <p className="small-note">
                      Routine completion target: median ≤ 3 minutes.{" "}
                      {progress.administration_median_minutes === null
                        ? "Not measured yet."
                        : `Current median: ${progress.administration_median_minutes.toFixed(1)} minutes. Target ${progress.administration_target_met ? "met" : "not met"}.`}
                    </p>
                  </section>
                  <section className="plain-card">
                    <h3>Assistance, in context</h3>
                    {Object.entries(progress.assistance).map(
                      ([level, count]: any) => (
                        <div className="data-row" key={level}>
                          <span>
                            {level === "none"
                              ? "Independent"
                              : level[0].toUpperCase() +
                                level.slice(1) +
                                " help"}
                          </span>
                          <strong>{count} attempts</strong>
                        </div>
                      ),
                    )}
                    <p className="small-note">
                      A small implementation correction differs from help that
                      supplies the missing algorithm. Hint count alone does not
                      decide your recall rating.
                    </p>
                    <details>
                      <summary>Historical evidence</summary>
                      <p>
                        {progress.historical.review_count} completed attempts
                        across the preserved history. Older evidence remains
                        separate from the new baseline.
                      </p>
                      <div>
                        {Object.entries(
                          progress.historical.errors_by_skill || {},
                        ).map(([skill, count]: any) => (
                          <div className="data-row" key={skill}>
                            <span>{skill}</span>
                            <strong>{count}</strong>
                          </div>
                        ))}
                      </div>
                    </details>
                  </section>
                </div>
                <footer>Progress is evidence that you can do it again.</footer>
              </div>
            )}
          </>
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={19} />
          {toast}
        </div>
      )}
      {facts && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="finish-title"
          >
            <button
              className="close icon-button"
              aria-label="Cancel completion"
              onClick={() => safely(cancelFinish)}
            >
              <X />
            </button>
            <div className="eyebrow">KEEP THE USEFUL PART</div>
            <h2 id="finish-title">What will you take forward?</h2>
            <p>What would you recognize or do differently next time?</p>
            <label className="field-label" htmlFor="takeaway">
              Your takeaway
            </label>
            <textarea
              id="takeaway"
              rows={3}
              value={takeaway}
              onChange={(e) => setTakeaway(e.target.value)}
              placeholder="Next time, I’ll notice…"
            />
            <div className="form-grid">
              <label>
                Recall rating
                <select
                  value={rating}
                  onChange={(e) => setRating(e.target.value)}
                >
                  <option value="again">Again · approach needed help</option>
                  {facts.recall_outcome === "success" && (
                    <>
                      <option value="hard">Hard · recalled with effort</option>
                      <option value="good">Good · ordinary effort</option>
                      <option value="easy">Easy · fluent recall</option>
                    </>
                  )}
                </select>
              </label>
              <label>
                Total active minutes
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  placeholder={facts.active_minutes + " · automatic"}
                  value={actualMinutes}
                  onChange={(e) => setActualMinutes(e.target.value)}
                />
              </label>
            </div>
            <p className="small-note">{facts.rating_rationale}</p>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={explained}
                onChange={(e) => setExplained(e.target.checked)}
              />{" "}
              I explained why the approach works.
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={constraints}
                onChange={(e) => setConstraints(e.target.checked)}
              />{" "}
              I checked the time and space requirements.
            </label>
            <div className="completion-preview">
              <strong>
                {s?.activity === "recall"
                  ? "Outline recall: implementation scheduling stays separate."
                  : s?.activity === "learn"
                    ? "Assisted learning: independent skill remains to establish."
                    : facts.tests_passed
                      ? "Current code passed its checks."
                      : "This will be saved as an unfinished / unsuccessful attempt."}
              </strong>
              <p>
                Your code, brief reflection, and learning evidence will be
                preserved.
              </p>
              <small>
                Publish destination:
                github.com/david1534/leetcode-learning-system
              </small>
            </div>
            <div className="button-row">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => safely(() => finish(false))}
              >
                <Save size={16} /> Finish locally
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => safely(() => finish(true))}
              >
                Publish & finish <ArrowRight size={16} />
              </button>
            </div>
            <p className="small-note">
              Publishing makes these learning artifacts public.{" "}
              {facts.unpublished_count > 0 &&
                `This includes ${facts.unpublished_count} earlier locally saved sessions.`}{" "}
              Cancel keeps the active attempt.
            </p>
          </section>
        </div>
      )}
      {repair && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="repair-title"
          >
            <button
              className="close icon-button"
              aria-label="Close repair"
              onClick={() =>
                safely(async () => {
                  await action("cancel-repair", { application });
                  setRepair(null);
                })
              }
            >
              <X />
            </button>
            <div className="eyebrow">ONE SMALL REPAIR</div>
            <h2 id="repair-title">{repair.skill}</h2>
            <p>{repair.repair_prompt}</p>
            <label className="field-label" htmlFor="repair-answer">
              Apply the rule to a fresh example
            </label>
            <textarea
              id="repair-answer"
              rows={6}
              value={application}
              onChange={(e) => setApplication(e.target.value)}
            />
            <p className="small-note">
              Ask Codex to check the application. Explain the rule briefly if
              the reasoning is unclear.
            </p>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={repairPassed}
                onChange={(e) => setRepairPassed(e.target.checked)}
              />{" "}
              The fresh application was checked and is correct.
            </label>
            <label className="field-label">
              Help received
              <select
                value={repairHelp}
                onChange={(e) => setRepairHelp(e.target.value)}
              >
                {["none", "minor", "guided", "substantial"].map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={busy || !application.trim()}
              onClick={() =>
                safely(async () => {
                  const result = await action("repair", {
                    error_id: repair.event_id,
                    application,
                    passed: repairPassed,
                    assistance: repairHelp,
                  });
                  setRepair(null);
                  setToast(result.message);
                })
              }
            >
              Record repair <Check size={17} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
