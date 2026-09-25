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
  await expect(
    page.getByRole("progressbar", { name: "Session progress" }),
  ).toBeVisible();
  await expect(page.getByLabel(/allowance remaining/)).toBeVisible();
  await expect(page.getByText(/included allowance remaining/)).toHaveCount(0);
  await page.getByText("Coach preferences", { exact: true }).click();
  const model = page.getByRole("combobox", { name: "Model" });
  await expect(model).toBeVisible();
  await model.selectOption("test-model");
  await expect(
    page.getByRole("combobox", { name: "Reasoning effort" }),
  ).toBeVisible();
  await page.getByLabel("Automatic practice checkpoints").uncheck();
  await page.getByText("Coach preferences", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "Ask your learning coach" })
    .fill("Please suggest a small code change.");
  await page.getByLabel("Allow a code preview").check();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Assessment help choice" }),
  ).toBeVisible();
  let releaseConversion!: () => void;
  const conversion = new Promise<void>((resolve) => {
    releaseConversion = resolve;
  });
  await page.route("**/api/practice/convert", async (route) => {
    await conversion;
    await route.continue();
  });
  await page
    .getByRole("button", { name: "Switch to guided practice", exact: true })
    .click();
  try {
    await expect(
      page.getByRole("button", { name: "Send", exact: true }),
    ).toBeDisabled();
  } finally {
    releaseConversion();
  }
  await expect(
    page.getByText("Guided practice", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Preview proposed code change")).toBeVisible();
  await page.getByText("Preview proposed code change").click();
  await page.getByRole("button", { name: "Apply this change" }).click();
  await expect(
    page.getByRole("button", { name: "Applied", exact: true }),
  ).toBeVisible();
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
  await expect(
    page.getByRole("button", { name: "Run tests", exact: true }),
  ).toBeInViewport();
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
  let releasePreferences!: () => void;
  const preferences = new Promise<void>((resolve) => {
    releasePreferences = resolve;
  });
  await page.route("**/api/coach/preferences", async (route) => {
    await preferences;
    await route.continue();
  });
  await page.getByLabel("Automatic practice checkpoints").uncheck();
  await page.getByText("Coach preferences", { exact: true }).click();
  await page
    .getByRole("button", { name: "Get guided help", exact: true })
    .click();
  const switchMode = page.getByRole("button", {
    name: "Switch to guided practice",
    exact: true,
  });
  try {
    await expect(switchMode).toBeDisabled();
  } finally {
    releasePreferences();
  }
  await switchMode.click();
  await expect(
    page.getByText("Guided practice", { exact: true }),
  ).toBeVisible();
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

test("recall selection survives a refresh but does not carry into another session", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByLabel("Allow new material on weekends").check();
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await page
    .getByRole("button", { name: "I don\u2019t know yet", exact: true })
    .click();
  await page.reload();
  await page.getByRole("button", { name: "Practice", exact: true }).click();
  await expect(page.getByLabel("Recall self-report")).toHaveValue("failed");
  await page.getByRole("button", { name: "Record idea & open editor" }).click();
  const first = (await (await request.get("/api/state")).json()).session
    .session_id;
  await page.getByRole("button", { name: "Finish / stop for today" }).click();
  await page
    .getByLabel("Your takeaway")
    .fill("Try the idea again after a break.");
  await page
    .getByRole("button", { name: "Finish locally", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await expect(page.getByLabel("Recall self-report")).toHaveValue("complete");
  await page
    .getByLabel("A few plain-language sentences are enough.")
    .fill("I independently reconstructed the approach for this attempt.");
  await page.getByRole("button", { name: "Record idea & open editor" }).click();
  await expect(
    page.getByRole("textbox", { name: "Python solution editor" }),
  ).toBeVisible();
  const next = (await (await request.get("/api/state")).json()).session;
  expect(next.session_id).not.toBe(first);
  expect(next.initial_reasoning.quality).toBe("complete");
});

test("pending publication can stay local while the next practice starts", async ({
  page,
  request,
}) => {
  await start(page);
  const first = (await (await request.get("/api/state")).json()).session
    .session_id;
  await page.getByRole("button", { name: "Finish / stop for today" }).click();
  await page
    .getByLabel("Your takeaway")
    .fill("Preserve the attempt and return to it later.");
  // The disposable repository has no remote, so publication remains pending.
  await page
    .getByRole("button", { name: "Publish & finish", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Saved learning" }),
  ).toBeInViewport();
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Keep local and continue" }),
  ).toBeVisible();
  const before = await (await request.get("/api/state")).json();
  expect(before.practice.status).toBe("completed");
  expect(before.session).toBe(null);
  const starting = page.waitForRequest(
    (r) => r.url().endsWith("/api/practice/start") && r.method() === "POST",
  );
  await page
    .getByRole("button", { name: "Keep local and continue", exact: true })
    .click();
  expect((await starting).postDataJSON().synchronize).toBe(false);
  await expect(
    page.getByLabel("A few plain-language sentences are enough."),
  ).toBeVisible();
  const resumed = await (await request.get("/api/state")).json();
  expect(resumed.session.session_id).not.toBe(first);
  expect(resumed.unpublished_count).toBe(1);
  expect(
    (await (await request.get("/__test__/records")).json()).reviews,
  ).toHaveLength(1);
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await expect(
    page.getByText("Saved learning awaits publication", { exact: true }),
  ).toBeVisible();
});

test("saved branch choices display and submit the API's branch names", async ({
  page,
  request,
}) => {
  const state = await (await request.get("/api/state")).json();
  let branches = ["attempt/first-draft", "attempt/second-draft"];
  let selected: unknown;
  await page.route("**/api/state", (route) =>
    route.fulfill({ json: { ...state, remote_attempts: branches } }),
  );
  await page.route("**/api/action/choose-attempt", async (route) => {
    selected = route.request().postDataJSON();
    branches = [];
    await route.fulfill({ json: { ...state, remote_attempts: [] } });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "attempt/first-draft", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "attempt/second-draft", exact: true })
    .click();
  await expect.poll(() => selected).toEqual({ branch: "attempt/second-draft" });
});
