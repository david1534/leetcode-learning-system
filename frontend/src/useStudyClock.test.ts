import { describe, expect, it } from "vitest";
import { clockAnchor, clockSeconds } from "./useStudyClock";
import type { StudyState } from "./types";

function state(
  seconds: number,
  running = true,
  repair = false,
  key = "practice-1",
) {
  return {
    practice: { practice_id: key, status: "active", elapsed_seconds: seconds },
    session: repair
      ? null
      : {
          session_id: "session-1",
          phase_started_at: running ? "active" : null,
        },
    repair: repair
      ? { error_id: "repair-1", started_at: running ? "active" : null }
      : null,
  } as StudyState;
}

describe("active study clock", () => {
  it("shows every second once across staggered server polls and render ticks", () => {
    let anchor = clockAnchor(state(0), 0);
    const displayed = [];
    for (let second = 0; second <= 60; second++) {
      if (second % 2 === 0)
        anchor = clockAnchor(state(second + 0.22), second * 1000 + 240, anchor);
      displayed.push(Math.floor(clockSeconds(anchor, second * 1000 + 300)));
    }
    expect(displayed).toEqual(Array.from({ length: 61 }, (_, i) => i));
  });
  it("freezes when paused and resumes without counting the break", () => {
    let anchor = clockAnchor(state(12), 1000);
    anchor = clockAnchor(state(13, false), 2000, anchor);
    expect(clockSeconds(anchor, 30000)).toBe(13);
    anchor = clockAnchor(state(13), 30000, anchor);
    expect(clockSeconds(anchor, 32000)).toBe(15);
  });
  it("ticks during a repair and preserves the total on the next stage", () => {
    let anchor = clockAnchor(state(10, true, true), 1000);
    expect(clockSeconds(anchor, 3000)).toBe(12);
    anchor = clockAnchor(state(12), 3000, anchor);
    expect(clockSeconds(anchor, 4000)).toBe(13);
  });
  it("accepts a sleep correction and resets for a new practice session", () => {
    let anchor = clockAnchor(state(20), 1000);
    anchor = clockAnchor(state(22, false), 100000, anchor);
    expect(clockSeconds(anchor, 100000)).toBe(22);
    anchor = clockAnchor(state(0, true, false, "new-session"), 101000, anchor);
    expect(clockSeconds(anchor, 102000)).toBe(1);
  });
});
