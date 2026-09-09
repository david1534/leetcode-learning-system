import { describe, it, expect } from "vitest";
import { formatTime, metricLabel, reconcileDraft } from "./api";
describe("learner evidence and draft protection", () => {
  it("does not represent absent measurements as zero success", () => {
    expect(metricLabel({ passed: 0, total: 0 })).toBe("Not measured");
    expect(metricLabel({ passed: 0, total: 3 })).toBe("0 / 3");
  });
  it("preserves an unsaved candidate after an external update", () => {
    expect(reconcileDraft("my draft", "external edit", true)).toBe("my draft");
    expect(reconcileDraft("saved", "external edit", false)).toBe(
      "external edit",
    );
  });
  it("formats elapsed time without wrapping at an hour", () =>
    expect(formatTime(3661)).toBe("61:01"));
});
