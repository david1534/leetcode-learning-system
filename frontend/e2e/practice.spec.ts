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
