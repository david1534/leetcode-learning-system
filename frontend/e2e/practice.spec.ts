import { test, expect, type Page } from "@playwright/test";

const headers = { "X-Study-Request": "1" };
const solution =
  "def pair_sum_indices(nums, target):\n    seen = {}\n    for index, value in enumerate(nums):\n        if target - value in seen:\n            return [seen[target - value], index]\n        seen[value] = index\n";
const failures = new WeakMap<Page, string[]>();
const expectedFailures = new WeakMap<Page, Set<string>>();

test.beforeEach(async ({ page, request }) => {
  await request.post("/__test__/reset", { headers });
  await page.addInitScript(() =>
    localStorage.setItem("practice-weekend-override", "true"),
  );
  failures.set(page, []);
  expectedFailures.set(page, new Set());
  page.on("pageerror", (error) => failures.get(page)!.push(error.message));
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (
      path.startsWith("/api/") &&
      response.status() >= 400 &&
      !expectedFailures.get(page)!.has(path)
    )
      failures.get(page)!.push(`${response.status()} ${path}`);
  });
});
test.afterEach(async ({ page }) => expect(failures.get(page)).toEqual([]));

async function start(page: Page) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Problem and examples" }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Your initial idea", { exact: true }),
  ).toBeVisible();
}
async function idea(page: Page) {
  await page
    .getByLabel("Your initial idea", { exact: true })
    .fill(
      "Track earlier values and their indices. Look up the complement before inserting the current value so both positions stay distinct.",
    );
  await page
    .getByRole("button", { name: "Continue to code", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Python solution editor", exact: true }),
  ).toBeVisible();
}
async function code(page: Page, value: string, saved = true) {
  const editor = page.getByRole("textbox", {
    name: "Python solution editor",
    exact: true,
  });
  await editor.press("ControlOrMeta+A");
  // Exercise Monaco's real paste handler without overwriting the user's OS clipboard.
  await editor.evaluate((element, text) => {
    const clipboard = new DataTransfer();
    clipboard.setData("text/plain", text);
    element.dispatchEvent(
      new ClipboardEvent("paste", {
        clipboardData: clipboard,
        bubbles: true,
        cancelable: true,
      }),
    );
  }, value);
  if (saved) {
    await expect
      .poll(
        async () =>
          (await (await page.request.get("/api/state")).json()).session.code,
      )
      .toBe(value);
    await expect(page.locator(".save-status")).toHaveText(
      "Saved on this computer",
    );
  }
}
async function connect(page: Page) {
  await page.getByRole("button", { name: "Ask coach", exact: true }).click();
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  if (
    !(await (await page.request.get("/api/coach/connection")).json()).selected
  ) {
    await expect(page.getByRole("dialog")).toBeVisible();
    await page
      .getByRole("combobox", { name: "Connection", exact: true })
      .selectOption("personal");
    await page
      .getByRole("button", { name: "Save connection", exact: true })
      .click();
    await expect(page.locator(".coach-connection-label")).toContainText(
      "Personal ChatGPT",
    );
    await page
      .getByRole("button", { name: "Connect Codex", exact: true })
      .click();
  }
  await expect(page.locator(".coach-status .badge")).toHaveText("Connected");
}
async function finish(page: Page, publish = false) {
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", {
      name: publish ? "Publish & finish" : "Finish locally",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("region", { name: "Saved learning" }),
  ).toBeVisible();
}

test("laptop shows the problem and question together, including after refresh", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const assets: string[] = [];
  page.on("request", (request) => assets.push(request.url()));
  await start(page);
  const prompt = page.locator(".problem-prompt");
  const question = page.getByRole("heading", {
    name: "What would you try, and why?",
    exact: true,
  });
  for (const item of [prompt, question]) {
    const bounds = await item.boundingBox();
    expect(bounds!.y).toBeGreaterThan(0);
    expect(bounds!.y + bounds!.height).toBeLessThan(800);
  }
  expect(assets.some((path) => /\/Editor-[^/]+\.js/.test(path))).toBe(false);
  await page
    .getByLabel("Your initial idea", { exact: true })
    .fill("Preserve my initial draft after refresh.");
  await page.reload();
  await expect(
    page.getByLabel("Your initial idea", { exact: true }),
  ).toHaveValue("Preserve my initial draft after refresh.");
  await expect(prompt).toBeVisible();
  await expect(question).toBeVisible();
  await page.screenshot({ path: "test-results/practice-laptop.png" });
});

test("complete a passing problem locally and start the next without publication", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await code(page, solution);
  await page
    .getByRole("button", { name: "Check solution", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "All checks passed", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Recall rating", exact: true }),
  ).toHaveValue("unknown");
  await page
    .getByRole("combobox", { name: "Recall rating", exact: true })
    .selectOption("good");
  await page
    .getByRole("checkbox", {
      name: "Explanation of why the approach works is recorded",
    })
    .check();
  await page
    .getByRole("checkbox", { name: "Time and space requirements were checked" })
    .check();
  await page
    .getByRole("button", { name: "Finish locally", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Saved learning" }),
  ).toBeVisible();
  const records = await (await request.get("/__test__/records")).json();
  expect(records.reviews).toHaveLength(1);
  expect(records.parents).toHaveLength(1);
  expect(records.reviews[0].rating).toBe("good");
  expect(records.reviews[0].tests_passed).toBe(true);
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await expect(page.locator(".practice-heading h1")).toHaveText(
    "Group Rearranged Words",
  );
  await expect(
    page.getByLabel("Your initial idea", { exact: true }),
  ).toHaveValue("");
  expect(
    (await (await request.get("/api/state")).json()).unpublished_count,
  ).toBe(1);
});

test("return after days keeps the same problem, code, and initial idea", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await code(page, solution);
  const before = (await (await request.get("/api/state")).json()).session;
  await request.post("/__test__/return-after-days", { headers });
  await page.reload();
  await expect(
    page.getByText("Paused · saved on this computer", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".problem-prompt")).toBeVisible();
  await page
    .getByRole("button", { name: "Resume practice", exact: true })
    .click();
  const after = (await (await request.get("/api/state")).json()).session;
  expect(after.session_id).toBe(before.session_id);
  expect(after.code).toBe(solution);
  expect(after.initial_reasoning).toEqual(before.initial_reasoning);
  expect(after.elapsed_seconds).toBeLessThan(60);
});

test("scheduled recall includes the full problem and finishes as one session", async ({
  page,
  request,
}) => {
  await request.post("/__test__/recall", { headers });
  await page.goto("/");
  await expect(page.locator(".problem-prompt")).toContainText(
    "Return the two indices",
  );
  await page
    .getByLabel("Your initial idea", { exact: true })
    .fill(
      "Remember which earlier value would complete the pair, retaining its index.",
    );
  await page
    .getByRole("button", { name: "Continue to code", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Review your reconstruction",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Python solution editor", exact: true }),
  ).toHaveCount(0);
  await finish(page);
  const records = await (await request.get("/__test__/records")).json();
  expect(records.reviews.at(-1).activity).toBe("recall");
  expect((await (await request.get("/api/state")).json()).session).toBeNull();
});

test("ordinary coaching needs no mode conversion and remains on request", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await connect(page);
  expect(
    (await (await request.get("/api/coach/status")).json()).requests,
  ).toHaveLength(0);
  const composer = page.getByRole("textbox", {
    name: "Ask your learning coach",
  });
  await composer.fill("Help me check my initial idea.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".coach-message")).toContainText(
    "Trace one small example",
  );
  await expect(
    page.getByRole("region", { name: "Assessment help choice" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".coach-message")).toContainText(
    "Trace one small example",
  );
  const state = (await (await request.get("/api/state")).json()).session;
  expect(state.assistance_log).toHaveLength(1);
});

test("explicit assessments wait for conversion and preserve pre-help work", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await request.post("/__test__/assessment", { headers });
  await page.reload();
  await connect(page);
  await page
    .getByRole("textbox", { name: "Ask your learning coach" })
    .fill("Show a small code preview.");
  await page.getByRole("checkbox", { name: "Allow a code preview" }).check();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Assessment help choice" }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/coach/status")).json()).requests,
  ).toHaveLength(0);
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/practice/convert", async (route) => {
    await delayed;
    await route.continue();
  });
  await page
    .getByRole("button", { name: "Switch to guided practice", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Send", exact: true }),
  ).toBeDisabled();
  release();
  await expect(
    page.getByRole("region", { name: "Assessment help choice" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByText("Preview proposed code change", { exact: true }).click();
  await page
    .getByRole("button", { name: "Apply this change", exact: true })
    .click();
  await expect
    .poll(
      async () => (await (await request.get("/api/state")).json()).session.code,
    )
    .toContain("Reviewed draft");
  const state = (await (await request.get("/api/state")).json()).session;
  expect(state.assessment_before_help.status).toBe("ended_for_help");
});

test("stopping tests and coaching uses separate controls and preserves code", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await connect(page);
  await code(
    page,
    "def pair_sum_indices(nums, target):\n    while True: pass\n",
  );
  await page
    .getByRole("textbox", { name: "Ask your learning coach" })
    .fill("Give me a slow response please.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page
    .getByRole("button", { name: "Check solution", exact: true })
    .click();
  await page.getByRole("button", { name: "Stop tests", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Test results" }),
  ).toContainText("stopped");
  await expect(page.locator(".coach-message")).toContainText(
    "Trace one small example",
  );
  await page
    .getByRole("textbox", { name: "Ask your learning coach" })
    .fill("Another slow response, please.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Stop coach", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get("/api/coach/status")).json()).requests.at(-1)
          .status,
    )
    .toBe("interrupted");
  expect(
    (await (await request.get("/api/state")).json()).session.code,
  ).toContain("while True");
});

test("a timed-out solution stays available for local completion", async ({
  page,
}) => {
  await start(page);
  await idea(page);
  await code(
    page,
    "def pair_sum_indices(nums, target):\n    while True: pass\n",
  );
  await page
    .getByRole("button", { name: "Check solution", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Test results" }),
  ).toContainText("timed out", { timeout: 16000 });
  await finish(page);
});

test("lost completion response reconciles the receipt without a duplicate review", async ({
  page,
  request,
}) => {
  expectedFailures.get(page)!.add("/api/practice/finish");
  await start(page);
  await idea(page);
  await page.route("**/api/practice/finish", async (route) => {
    await route.fetch();
    await route.fulfill({
      status: 503,
      contentType: "text/plain",
      body: "Simulated lost acknowledgement",
    });
  });
  await finish(page);
  expect(
    (await (await request.get("/__test__/records")).json()).reviews,
  ).toHaveLength(1);
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Saved learning" }),
  ).toBeVisible();
});

test("an unavailable save keeps browser recovery and never claims a local commit", async ({
  page,
  request,
}) => {
  expectedFailures.get(page)!.add("/api/action/save");
  await start(page);
  await idea(page);
  await page.route("**/api/action/save", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        code: "storage_unavailable",
        detail: "The local save could not be confirmed.",
      }),
    }),
  );
  await code(page, solution, false);
  await expect(page.locator(".save-status")).toHaveText("Saved in browser");
  expect(
    (await (await request.get("/api/state")).json()).session.code,
  ).not.toBe(solution);
  await page.reload();
  await expect(page.locator(".save-status")).toHaveText("Saved in browser");
  await page.unroute("**/api/action/save");
  await page.reload();
  await expect
    .poll(
      async () => (await (await request.get("/api/state")).json()).session.code,
    )
    .toBe(solution);
  await expect(page.locator(".save-status")).toHaveText(
    "Saved on this computer",
  );
});

test("storage exhaustion gives a download instead of a false saved claim", async ({
  page,
}) => {
  expectedFailures.get(page)!.add("/api/action/save");
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith("practice-code-"))
        throw new DOMException("Storage full", "QuotaExceededError");
      return original.call(this, key, value);
    };
  });
  await start(page);
  await idea(page);
  await page.route("**/api/action/save", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        code: "storage_unavailable",
        detail: "Storage unavailable.",
      }),
    }),
  );
  await code(page, solution, false);
  await expect(page.locator(".save-status")).toContainText("Not saved");
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download work", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("practice-work.json");
});

test("conflicting tabs preserve both versions until an explicit choice", async ({
  page,
  context,
  request,
}) => {
  expectedFailures.get(page)!.add("/api/action/save");
  await start(page);
  await idea(page);
  const other = await context.newPage();
  await other.goto("/");
  await expect(
    other.getByRole("textbox", { name: "Python solution editor", exact: true }),
  ).toBeVisible();
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/action/save", async (route) => {
    await delayed;
    await route.continue();
  });
  await code(
    page,
    "def pair_sum_indices(nums, target): return [0, 1]\n",
    false,
  );
  await code(other, solution);
  release();
  await expect(
    page.getByRole("heading", {
      name: "Two versions of your code",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Use other saved version", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Two versions of your code",
      exact: true,
    }),
  ).toHaveCount(0);
  expect((await (await request.get("/api/state")).json()).session.code).toBe(
    solution,
  );
  await other.close();
});

test("failed publication leaves the next practice available", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await finish(page, true);
  await expect(
    page.getByText("GitHub sync pending", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Continue locally", exact: true })
    .click();
  await expect(
    page.getByLabel("Your initial idea", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/state")).json()).unpublished_count,
  ).toBe(1);
});

test("malformed coaching, unsafe Markdown, and expired login leave practice usable", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await connect(page);
  const composer = page.getByRole("textbox", {
    name: "Ask your learning coach",
  });
  await composer.fill("Please send unsafe markup for this fixture.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".coach-message")).toContainText("Markup fixture");
  await expect(
    page.locator(
      '.coach-messages script,.coach-messages img,.coach-messages a[href^="javascript:"]',
    ),
  ).toHaveCount(0);
  await composer.fill("A malformed reply for this fixture.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".coach-messages")).toContainText("invalid reply");
  await request.post("/__test__/coach-expired", { headers });
  await expect(page.locator(".coach-connection")).toContainText(
    "sign-in expired",
  );
  await code(page, solution);
  await finish(page);
});

test("keyboard completion cancellation, themes, and narrow layout", async ({
  page,
}) => {
  await start(page);
  await idea(page);
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await page
    .getByRole("textbox", { name: "A short takeaway (optional)", exact: true })
    .fill("Keep this reflection draft.");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(
    page.getByRole("textbox", {
      name: "A short takeaway (optional)",
      exact: true,
    }),
  ).toHaveValue("Keep this reflection draft.");
  await page.keyboard.press("Escape");
  await page.getByLabel("Settings", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "Theme", exact: true })
    .selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  for (const viewport of [
    { width: 1920, height: 1080 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.locator(".problem-prompt")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/practice-${viewport.width}.png`,
      fullPage: false,
    });
  }
});

test("standalone repair preserves its draft and ends without opening a main problem", async ({
  page,
  request,
}) => {
  await request.post("/__test__/repair", { headers });
  await page.goto("/");
  await page
    .getByText("Repairs and learning examples", { exact: true })
    .click();
  await page
    .getByRole("button", { name: "Practice this repair", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Your fresh application", exact: true })
    .fill("items = [4, 5]\nitems.append(6)\nassert items == [4, 5, 6]");
  await page
    .getByRole("button", { name: "Save application", exact: true })
    .click();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page
    .getByRole("button", { name: "Resume practice", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your fresh application", exact: true }),
  ).toContainText("items.append");
  await page
    .getByRole("button", { name: "Run repair assertions", exact: true })
    .click();
  await expect(page.locator(".repair-card")).toContainText("assertions passed");
  await page
    .getByRole("checkbox", {
      name: "I reviewed a correct fresh application, with Codex or an external coach",
      exact: true,
    })
    .check();
  await page
    .getByRole("button", { name: "Finish repair locally", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Saved learning" }),
  ).toBeVisible();
  const state = await (await request.get("/api/state")).json();
  expect(state.session).toBeNull();
  expect(state.repair).toBeNull();
});

test("publication preview can keep a saved session local and cancels by keyboard", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await finish(page);
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await idea(page);
  await finish(page);
  await page
    .getByRole("button", { name: "Review & publish", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Publish saved learning",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  const choices = dialog.getByRole("checkbox");
  await expect(choices).toHaveCount(2);
  await choices.nth(1).uncheck();
  let sent: Record<string, unknown> | undefined;
  await page.route("**/api/action/publish", async (route) => {
    sent = route.request().postDataJSON();
    await route.continue();
  });
  await dialog
    .getByRole("button", { name: "Publish 1 saved session(s)", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  expect((sent!.session_ids as string[]).length).toBe(1);
  expect(
    (await (await request.get("/api/state")).json()).unpublished_count,
  ).toBe(2);
  await page
    .getByRole("button", { name: "Review & publish", exact: true })
    .click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("configure company before practice, remember it, and switch without losing the attempt", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByLabel("Settings", { exact: true }).click();
  await page
    .getByRole("button", { name: "Coaching connection", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("combobox", { name: "Connection", exact: true })
    .selectOption("company");
  await page
    .getByLabel("API base URL", { exact: true })
    .fill("https://company.example/v1");
  await page.getByLabel("Default model", { exact: true }).fill("test-model");
  await page
    .getByRole("combobox", { name: "Reasoning effort", exact: true })
    .selectOption("medium");
  await page
    .getByLabel("Credential environment variable", { exact: true })
    .fill("PRACTICE_BROWSER_KEY");
  await page
    .getByLabel("Organization ID (optional)", { exact: true })
    .fill("fixture-org");
  await page.screenshot({
    path: "test-results/company-connection-settings.png",
  });
  await page
    .getByRole("button", { name: "Save connection", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.reload();
  const saved = await (await request.get("/api/coach/connection")).json();
  expect(saved.selected).toBe("company");
  expect(saved.company.organization).toBe("fixture-org");
  expect(JSON.stringify(saved)).not.toContain("private-browser-test-key");
  await start(page);
  await idea(page);
  await code(page, solution);
  await connect(page);
  await expect(
    page.getByText("Usage managed by your organization", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".usage-indicator")).toHaveCount(0);
  await page
    .getByRole("textbox", { name: "Ask your learning coach", exact: true })
    .fill("Help me trace the example.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".coach-message").last()).toContainText(
    "Trace one small example",
  );
  const before = (await (await request.get("/api/state")).json()).session;
  await page
    .getByRole("button", { name: "Change connection", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Connection", exact: true })
    .selectOption("personal");
  await page
    .getByRole("button", { name: "Save connection", exact: true })
    .click();
  await expect(page.locator(".coach-connection-label")).toContainText(
    "Personal ChatGPT",
  );
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  await expect(page.locator(".coach-status .badge")).toHaveText("Connected");
  await expect(page.locator(".usage-indicator")).toHaveCount(1);
  const after = (await (await request.get("/api/state")).json()).session;
  expect(after.session_id).toBe(before.session_id);
  expect(after.code).toBe(solution);
  await expect(page.locator(".coach-message").last()).toContainText(
    "Company coach",
  );
});

test("missing company credentials preserve configuration and local practice", async ({
  page,
  request,
}) => {
  await request.post("/api/coach/connection", {
    headers,
    data: {
      selected: "company",
      company: {
        base_url: "https://company.example/v1",
        model: "test-model",
        api_key_env: "MISSING_BROWSER_KEY",
      },
    },
  });
  await start(page);
  await idea(page);
  await page.getByRole("button", { name: "Ask coach", exact: true }).click();
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  await expect(page.locator(".coach-connection")).toContainText(
    "MISSING_BROWSER_KEY",
  );
  await expect(
    page.getByRole("link", { name: "Sign in with ChatGPT", exact: true }),
  ).toHaveCount(0);
  expect(
    (await (await request.get("/api/coach/connection")).json()).selected,
  ).toBe("company");
  await code(page, solution);
  await page
    .getByRole("button", { name: "Check solution", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "All checks passed", exact: true }),
  ).toBeVisible();
});

test("check solution keeps its result while progress is busy", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  // Let the refresh request enter the progress calculation before the worker returns.
  const candidate = "import time\ntime.sleep(0.5)\n" + solution;
  await code(page, candidate);
  await request.post("/__test__/slow-progress", { headers });
  await page
    .getByRole("button", { name: "Check solution", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "All checks passed", exact: true }),
  ).toBeVisible({ timeout: 12000 });
  let state = await (await request.get("/api/state")).json();
  expect(state.check.status).toBe("complete");
  expect(state.session.checkpoint_count).toBe(1);
  expect(state.session.code).toBe(candidate);
  await page
    .getByRole("button", { name: "Check solution", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (await (await request.get("/api/state")).json()).session
          .checkpoint_count,
    )
    .toBe(2);
  state = await (await request.get("/api/state")).json();
  expect(state.check.all_passed).toBe(true);
  expect(state.session.code).toBe(candidate);
});

for (const mode of ["delayed", "lost"] as const) {
  test(`a ${mode} save acknowledgement does not create a conflict with this tab`, async ({
    page,
    request,
  }) => {
    await start(page);
    await idea(page);
    let committed!: () => void;
    const savedOnServer = new Promise<void>((resolve) => {
      committed = resolve;
    });
    let release!: () => void;
    const acknowledgement = new Promise<void>((resolve) => {
      release = resolve;
    });
    let first = true;
    await page.route("**/api/action/save", async (route) => {
      if (!first) return route.continue();
      first = false;
      const response = await route.fetch();
      committed();
      await acknowledgement;
      if (mode === "lost") await route.abort("failed");
      else await route.fulfill({ response });
    });
    const initial = solution + "\n# first edit\n";
    const continued = solution + "\n# continued typing\n";
    try {
      await code(page, initial, false);
      await savedOnServer;
      await page.waitForResponse(
        async (response) =>
          response.url().endsWith("/api/state") &&
          response.ok() &&
          (await response.json()).session?.code === initial,
      );
      await code(page, continued, false);
    } finally {
      release();
    }
    await expect
      .poll(
        async () =>
          (await (await request.get("/api/state")).json()).session.code,
      )
      .toBe(continued);
    await expect(
      page.getByRole("heading", {
        name: "Two versions of your code",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(page.locator(".save-status")).toHaveText(
      "Saved on this computer",
    );
  });
}

test("a late save acknowledgement cannot change the next session's draft", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  let committed!: () => void;
  const savedOnServer = new Promise<void>((resolve) => {
    committed = resolve;
  });
  let release!: () => void;
  const acknowledgement = new Promise<void>((resolve) => {
    release = resolve;
  });
  let first = true;
  await page.route("**/api/action/save", async (route) => {
    if (!first) return route.continue();
    first = false;
    const response = await route.fetch();
    committed();
    await acknowledgement;
    await route.fulfill({ response });
  });
  const nextDraft = solution + "\n# next session draft\n";
  let secondId = "";
  try {
    await code(page, solution + "\n# previous session\n", false);
    await savedOnServer;
    const previous = (await (await request.get("/api/state")).json()).session;
    const finished = await request.post("/api/practice/finish", {
      headers,
      data: {
        session_id: previous.session_id,
        revision: previous.revision,
        rating: "unknown",
        stopped: true,
      },
    });
    expect(finished.ok()).toBe(true);
    const started = await request.post("/api/practice/start", {
      headers,
      data: { include_new: true, synchronize: false },
    });
    secondId = (await started.json()).session.session_id;
    await request.post("/api/action/reasoning", {
      headers,
      data: {
        answer:
          "Trace earlier values and compare their complement before insertion.",
      },
    });
    await expect(page.locator(".original-idea p")).toHaveText(
      "Trace earlier values and compare their complement before insertion.",
    );
    await code(page, nextDraft, false);
  } finally {
    release();
  }
  await expect
    .poll(
      async () => (await (await request.get("/api/state")).json()).session.code,
    )
    .toBe(nextDraft);
  const current = (await (await request.get("/api/state")).json()).session;
  expect(current.session_id).toBe(secondId);
  await expect(
    page.getByRole("heading", {
      name: "Two versions of your code",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(page.locator(".save-status")).toHaveText(
    "Saved on this computer",
  );
});

test("a question waiting for autosave cannot move to a new session", async ({
  page,
  request,
}) => {
  const postedQuestions: unknown[] = [];
  page.on("request", (event) => {
    if (
      event.url().endsWith("/api/coach/requests") &&
      event.method() === "POST"
    ) {
      const payload = event.postDataJSON();
      postedQuestions.push({
        session_id: payload.session_id,
        message: payload.message,
      });
    }
  });
  await start(page);
  await idea(page);
  await connect(page);
  let committed!: () => void;
  const savedOnServer = new Promise<void>((resolve) => {
    committed = resolve;
  });
  let release!: () => void;
  const acknowledgement = new Promise<void>((resolve) => {
    release = resolve;
  });
  let first = true;
  await page.route("**/api/action/save", async (route) => {
    if (!first) return route.continue();
    first = false;
    const response = await route.fetch();
    committed();
    await acknowledgement;
    await route.fulfill({ response });
  });
  try {
    await code(page, solution + "\n# old session edit\n", false);
    await savedOnServer;
    await page
      .getByRole("textbox", { name: "Ask your learning coach", exact: true })
      .fill("Question about the previous problem.");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const previous = (await (await request.get("/api/state")).json()).session;
    await request.post("/api/practice/finish", {
      headers,
      data: {
        session_id: previous.session_id,
        revision: previous.revision,
        rating: "unknown",
        stopped: true,
      },
    });
    await request.post("/api/practice/start", {
      headers,
      data: { include_new: true, synchronize: false },
    });
    await request.post("/api/action/reasoning", {
      headers,
      data: { answer: "A fresh idea for the new session." },
    });
    await expect(page.locator(".original-idea p")).toHaveText(
      "A fresh idea for the new session.",
    );
  } finally {
    release();
  }
  await expect(
    page
      .getByText(
        "The active problem changed before sending this question. Review the current problem and ask again.",
        { exact: true },
      )
      .first(),
  ).toBeVisible();
  expect(postedQuestions).toHaveLength(0);
  const status = await (await request.get("/api/coach/status")).json();
  expect(status.requests).toHaveLength(0);
});

test("a delayed completion cannot finish the next session", async ({
  page,
  request,
}) => {
  await start(page);
  await idea(page);
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByLabel("A short takeaway (optional)")
    .fill("Takeaway for the first session only.");
  let evaluated!: () => void;
  const evaluation = new Promise<void>((resolve) => {
    evaluated = resolve;
  });
  let release!: () => void;
  const acknowledgement = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/action/evaluate", async (route) => {
    const response = await route.fetch();
    evaluated();
    await acknowledgement;
    await route.fulfill({ response });
  });
  let nextId = "";
  try {
    await page
      .getByRole("button", { name: "Finish locally", exact: true })
      .click();
    await evaluation;
    const current = (await (await request.get("/api/state")).json()).session;
    const finished = await request.post("/api/practice/finish", {
      headers,
      data: {
        session_id: current.session_id,
        revision: current.revision,
        rating: "unknown",
        stopped: true,
      },
    });
    expect(finished.ok()).toBe(true);
    const next = await request.post("/api/practice/start", {
      headers,
      data: { include_new: true, synchronize: false },
    });
    nextId = (await next.json()).session.session_id;
    await request.post("/api/action/reasoning", {
      headers,
      data: { answer: "New session reasoning must stay independent." },
    });
    await expect(page.locator(".original-idea p")).toHaveText(
      "New session reasoning must stay independent.",
    );
  } finally {
    release();
  }
  await expect(page.locator("section[role=alert]")).toContainText(
    "Open a fresh completion summary",
  );
  expect(
    (await (await request.get("/api/state")).json()).session.session_id,
  ).toBe(nextId);
  const records = await (await request.get("/__test__/records")).json();
  expect(records.reviews).toHaveLength(1);
});

test("editing a repair clears its correctness confirmation and offers first connection setup", async ({
  page,
  request,
}) => {
  await request.post("/__test__/repair", { headers });
  await page.goto("/");
  await page
    .getByText("Repairs and learning examples", { exact: true })
    .click();
  await page
    .getByRole("button", { name: "Practice this repair", exact: true })
    .click();
  const editor = page.getByRole("textbox", {
    name: "Your fresh application",
    exact: true,
  });
  const confirmation = page.getByRole("checkbox", {
    name: "I reviewed a correct fresh application, with Codex or an external coach",
    exact: true,
  });
  await editor.fill("assert True");
  await confirmation.check();
  await editor.fill("assert False");
  await expect(confirmation).not.toBeChecked();
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Coaching connection" }),
  ).toBeVisible();
});

test("saved drafts can stay saved while today's fresh practice starts", async ({
  page,
  request,
}) => {
  await request.post("/__test__/remote-drafts", { headers });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Choose your saved attempt" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "attempt/older-pair-sum", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/saved-draft-choice.png" });
  await page
    .getByRole("button", { name: "Start fresh practice", exact: true })
    .click();
  await expect(
    page.getByLabel("Your initial idea", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry connection", exact: true }),
  ).toHaveCount(0);
  const state = await (await request.get("/api/state")).json();
  expect(state.remote_attempts).toEqual([
    "attempt/older-pair-sum",
    "attempt/older-product",
  ]);
  await idea(page);
  await finish(page);
  await expect(
    page.getByRole("button", { name: "attempt/older-pair-sum", exact: true }),
  ).toBeVisible();
});

test("confirmed practice opens without waiting for a progress refresh", async ({
  page,
}) => {
  await page.goto("/");
  const startButton = page.getByRole("button", {
    name: "Start practice",
    exact: true,
  });
  await expect(startButton).toBeEnabled();
  let release!: () => void;
  const delayedProgress = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const progressRequest = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/api/progress", async (route) => {
    requested();
    await delayedProgress;
    await route.continue();
  });
  try {
    await startButton.click();
    await progressRequest;
    await expect(
      page.getByRole("region", { name: "Problem and examples" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Your initial idea", { exact: true }),
    ).toBeVisible();
  } finally {
    release();
  }
});

for (const retry of [false, true]) {
  test(`confirmed publication clears the saved-session prompt${retry ? " after retry" : " on finish"}`, async ({
    page,
    request,
  }) => {
    test.setTimeout(120000);
    await start(page);
    await idea(page);
    if (!retry) {
      expect(
        (await request.post("/__test__/publication-remote", { headers })).ok(),
      ).toBe(true);
    }
    await finish(page, true);
    const saved = page.getByRole("region", { name: "Saved learning" });
    if (retry) {
      await expect(saved.getByRole("status")).toContainText("sync pending");
      expect(
        (await request.post("/__test__/publication-remote", { headers })).ok(),
      ).toBe(true);
      await saved
        .getByRole("button", { name: "Review & publish", exact: true })
        .click();
      const dialog = page.getByRole("dialog", {
        name: "Publish saved learning",
      });
      await dialog
        .getByRole("button", {
          name: "Publish 1 saved session(s)",
          exact: true,
        })
        .click();
      await expect(dialog).toHaveCount(0);
    }
    await expect(saved).toContainText(
      "Saved locally and published to GitHub.",
      { timeout: 60000 },
    );
    await expect(
      saved.getByRole("button", { name: "Review & publish", exact: true }),
    ).toHaveCount(0);
    await page.reload();
    await expect(saved).toContainText("Saved locally and published to GitHub.");
    expect(
      (await (await request.get("/api/state")).json()).unpublished_count,
    ).toBe(0);
    const records = await (await request.get("/__test__/records")).json();
    expect(records.reviews).toHaveLength(1);
  });
}

test("publication request errors stay visible inside the preview", async ({
  page,
}) => {
  await start(page);
  await idea(page);
  await finish(page);
  await page
    .getByRole("button", { name: "Review & publish", exact: true })
    .click();
  expectedFailures.get(page)!.add("/api/action/publish");
  await page.route("**/api/action/publish", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        detail:
          "The saved-session list changed. Review the publication preview again.",
      }),
    }),
  );
  const dialog = page.getByRole("dialog", { name: "Publish saved learning" });
  await dialog
    .getByRole("button", { name: "Publish 1 saved session(s)", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Review the publication preview again.",
  );
  await expect(dialog).toBeVisible();
});
