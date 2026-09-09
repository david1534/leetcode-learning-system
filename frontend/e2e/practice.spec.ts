import { test, expect, type Page } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const result = await request.post("/__test__/reset", {
    headers: { "X-Study-Request": "1" },
  });
  expect(result.ok()).toBeTruthy();
});
async function start(page: Page) {
  await page.goto("/");
  await page.getByLabel("Allow new material on weekends").check();
  await page
    .getByRole("button", {
      name: /Start.*session|Start practicing|Start practice/i,
    })
    .click();
  if (await page.getByRole("button", { name: "Code", exact: true }).isVisible())
    await page.getByRole("button", { name: "Code", exact: true }).click();
  await page
    .getByLabel("A few plain-language sentences are enough.")
    .fill(
      "Check earlier values before adding this value. Compare a pair with the target.",
    );
  await page.getByRole("button", { name: "Record idea & open editor" }).click();
}
async function code(page: Page, value: string) {
  const editor = page.getByRole("textbox", { name: "Python solution editor" });
  await editor.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText(value);
  await expect(page.locator(".save-status")).toHaveText("Saved locally");
}
test("dark first paint, local practice, timeout/stop, refresh and unsuccessful finish", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await start(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await code(
    page,
    "def pair_sum_indices(nums, target):\n    while True:\n        pass\n",
  );
  await page.getByRole("button", { name: /Run tests/i }).click();
  await page.getByRole("button", { name: /Stop tests/i }).click();
  await expect(
    page.getByText("Stopped", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask your learning coach" })
    .fill("My question survives a refresh");
  await page.reload();
  await page.getByRole("button", { name: "Practice", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Ask your learning coach" }),
  ).toHaveValue("My question survives a refresh");
  await page.getByRole("button", { name: /Finish \/ stop for today/i }).click();
  await page
    .getByLabel("Your takeaway")
    .fill("I will test one small example before a full loop.");
  await page
    .getByRole("button", { name: "Finish locally", exact: true })
    .click();
  await expect(
    page.getByText("Your complete practice session is saved locally.", {
      exact: true,
    }),
  ).toBeVisible();
  const records = await (await request.get("/__test__/records")).json();
  expect(records.reviews).toHaveLength(1);
  expect(records.parents).toHaveLength(1);
  expect(records.reviews[0].tests_passed).toBe(false);
  expect(errors).toEqual([]);
});
test("explicit assessment conversion, fake coach reply and safe code preview", async ({
  page,
  request,
}) => {
  await start(page);
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await page.getByText("Coach preferences", { exact: true }).click();
  await page.getByLabel("Automatic practice checkpoints").uncheck();
  await page
    .getByRole("textbox", { name: "Ask your learning coach" })
    .fill("Please suggest a small code change.");
  await page.getByLabel("Include a code-change preview if useful").check();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Assessment help choice" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Switch to guided practice", exact: true })
    .click();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Preview proposed code change")).toBeVisible();
  await page.getByText("Preview proposed code change").click();
  await page.getByRole("button", { name: "Apply this change" }).click();
  const state = await (await request.get("/api/state")).json();
  expect(state.session.code).toContain("Reviewed draft");
  expect(state.session.assessment_before_help.status).toBe("ended_for_help");
});
test("narrow layout, theme persistence and keyboard completion cancellation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Toggle dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await start(page);
  await page.getByRole("button", { name: /Finish \/ stop for today/i }).click();
  await page
    .getByLabel("Your takeaway")
    .fill("Preserve this unfinished reflection.");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("conflicting tabs preserve the browser draft and require a choice", async ({
  page,
  context,
}) => {
  await start(page);
  await page.route("**/api/action/save", (route) => route.abort());
  const editor = page.getByRole("textbox", { name: "Python solution editor" });
  await editor.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText(
    "def pair_sum_indices(nums, target):\n    return [0, 1]\n# first window\n",
  );
  await expect(page.locator(".save-status")).toHaveText("Saved in browser");
  const other = await context.newPage();
  await other.goto("/");
  await other.getByRole("button", { name: "Practice", exact: true }).click();
  // The other tab has its own loaded draft, while the first retains an unsent edit.
  await code(
    other,
    "def pair_sum_indices(nums, target):\n    return [1, 2]\n# second window\n",
  );
  await page.unroute("**/api/action/save");
  await expect(
    page.getByRole("heading", { name: "Two versions need your review" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep my browser draft" }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get("/api/state")).json()).session.code,
    )
    .toContain("first window");
});

test("default timeout is recoverable and does not remove code", async ({
  page,
}) => {
  await start(page);
  await code(
    page,
    "def pair_sum_indices(nums, target):\n    while True:\n        pass\n",
  );
  await page.getByRole("button", { name: "Run tests" }).click();
  await expect(page.getByText("Timed out", { exact: true })).toBeVisible({
    timeout: 16000,
  });
  const state = await (await page.request.get("/api/state")).json();
  expect(state.session.code).toContain("while True");
});

test("visual layouts, large text and lazy editor loading", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const loaded: string[] = [];
  page.on("request", (r) => loaded.push(r.url()));
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Start practice" }),
  ).toBeInViewport();
  expect(loaded.some((url) => /\/Editor-.*\.js/.test(url))).toBe(false);
  await page.screenshot({ path: "test-results/today-desktop.png" });
  await start(page);
  await expect(
    page.getByRole("textbox", { name: "Python solution editor" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/practice-desktop.png" });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.screenshot({ path: "test-results/practice-laptop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/practice-narrow.png" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addStyleTag({
    content:
      "body {font-size:32px !important} p, label, input, textarea, select, button {font-size:inherit !important}",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/practice-large-text.png" });
  expect(errors).toEqual([]);
});

test("repair draft survives pause and resumes the main activity", async ({
  page,
  request,
}) => {
  await request.post("/__test__/repair", {
    headers: { "X-Study-Request": "1" },
  });
  await page.goto("/");
  await page.getByLabel("Allow new material on weekends").check();
  await page.getByRole("button", { name: "Start practice" }).click();
  await expect(
    page.getByRole("heading", { name: "Apply the corrected rule" }),
  ).toBeVisible();
  const answer = "items = [4, 5]\nitems.append(6)\nassert items == [4, 5, 6]";
  await page.getByLabel("A fresh application").fill(answer);
  await page.getByRole("button", { name: "Pause & save repair" }).click();
  await expect(
    page.getByRole("button", { name: "Resume repair" }),
  ).toBeVisible();
  let state = await (await request.get("/api/state")).json();
  expect(state.repair.application).toBe(answer);
  expect(state.repair.started_at).toBe(null);
  await page.reload();
  await page.getByRole("button", { name: "Practice", exact: true }).click();
  await expect(page.getByLabel("A fresh application")).toHaveValue(answer);
  await page.getByRole("button", { name: "Resume repair" }).click();
  await page.getByRole("button", { name: "Run repair assertions" }).click();
  await expect(page.getByText(/Your assertions passed/)).toBeVisible();
  await page
    .getByLabel("I reviewed the fresh application and confirmed it succeeds")
    .check();
  await page.getByRole("button", { name: "Save repair & continue" }).click();
  await expect(
    page.getByLabel("A few plain-language sentences are enough."),
  ).toBeVisible();
  state = await (await request.get("/api/state")).json();
  expect(state.repair).toBe(null);
  expect(state.practice.stages[state.practice.index].type).toBe("main");
  expect(state.session.phase_started_at).not.toBe(null);
});

test("malformed coaching and unsafe Markdown leave local practice available", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await start(page);
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await page.getByText("Coach preferences", { exact: true }).click();
  await page.getByLabel("Automatic practice checkpoints").uncheck();
  await page
    .getByRole("button", { name: "Get guided help", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Switch to guided practice", exact: true })
    .click();
  const question = page.getByRole("textbox", {
    name: "Ask your learning coach",
  });
  await question.fill("unsafe markup");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText(/Markup fixture/)).toBeVisible();
  expect(await page.evaluate(() => "__unsafe" in window)).toBe(false);
  await expect(
    page.locator(
      '.coach-messages script, .coach-messages img, .coach-messages a[href^="javascript:"]',
    ),
  ).toHaveCount(0);
  await question.fill("malformed reply");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText(/coach returned an invalid reply/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run tests", exact: true }),
  ).toBeEnabled();
  expect(errors).toEqual([]);
});
