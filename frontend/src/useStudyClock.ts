import { useEffect, useState } from "react";
import type { StudyState } from "./types";

export interface ClockAnchor {
  key: string;
  seconds: number;
  running: boolean;
  at: number;
}

export function clockSeconds(anchor: ClockAnchor, now: number) {
  return (
    anchor.seconds + (anchor.running ? Math.max(0, now - anchor.at) / 1000 : 0)
  );
}

export function clockAnchor(
  state: StudyState | null,
  now: number,
  prior?: ClockAnchor,
): ClockAnchor {
  const parent = state?.practice?.status === "active" ? state.practice : null;
  const session = state?.session;
  const repair = state?.repair;
  const key =
    parent?.practice_id ?? session?.session_id ?? repair?.error_id ?? "";
  const seconds =
    parent?.elapsed_seconds ??
    session?.elapsed_seconds ??
    repair?.elapsed_seconds ??
    0;
  const running = Boolean(session?.phase_started_at || repair?.started_at);
  // Preserve a continuous monotonic clock across ordinary polling jitter. State
  // transitions and meaningful corrections (including sleep recovery) resync it.
  if (
    prior &&
    prior.key === key &&
    prior.running === running &&
    Math.abs(clockSeconds(prior, now) - seconds) < 1.5
  )
    return prior;
  return { key, seconds, running, at: now };
}

export function useStudyClock(state: StudyState | null) {
  const [sample, setSample] = useState(() => ({
    state,
    anchor: clockAnchor(state, performance.now()),
  }));
  const [now, setNow] = useState(() => performance.now());
  let anchor = sample.anchor;
  if (sample.state !== state) {
    const receivedAt = performance.now();
    anchor = clockAnchor(state, receivedAt, anchor);
    // Update before committing the render: never render fresh server seconds
    // with the previous response's elapsed time added on top.
    setSample({ state, anchor });
    setNow(receivedAt);
  }
  useEffect(() => {
    if (!anchor.running) return;
    const update = () => setNow(performance.now());
    const timer = window.setInterval(update, 100);
    document.addEventListener("visibilitychange", update);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
    };
  }, [anchor.running]);
  return clockSeconds(anchor, now);
}
