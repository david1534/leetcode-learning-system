import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
vi.mock("./Editor", () => ({ default: () => null }));
import App from "./App";
describe("startup", () => {
  it("renders a loading state before the session arrives", () => {
    expect(renderToString(<App />)).toContain("Opening your practice room");
  });
});
