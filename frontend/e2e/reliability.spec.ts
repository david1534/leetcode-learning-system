import { test, expect, type Page } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  expect(
    (
      await request.post("/__test__/reset", {
        headers: { "X-Study-Request": "1" },
      })
    ).ok(),
  ).toBeTruthy();
});

async function start(page: Page) {
  await page.goto("/");
  await page.getByLabel("Allow new material on weekends").check();
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  await page
    .getByLabel("A few plain-language sentences are enough.")
    .fill("Compare earlier values with the target before storing this value.");
  await page.getByRole("button", { name: "Record idea & open editor" }).click();
  await expect(
    page.getByRole("button", { name: "Run tests", exact: true }),
  ).toBeEnabled();
}

async function connect(page: Page) {
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
  await expect(
    page.getByText("Guided practice", { exact: true }),
  ).toBeVisible();
}

async function observeClock(page: Page, duration: number) {
  await expect(page.locator(".timer-digits")).toBeVisible();
  return page.evaluate(async (milliseconds) => {
    const digits = document.querySelector(".timer-digits")!;
    const seconds = () => {
      const [m, s] = digits.textContent!.split(":").map(Number);
      return m * 60 + s;
    };
    const values = [seconds()];
    const observer = new MutationObserver(() => {
      const value = seconds();
      if (value !== values.at(-1)) values.push(value);
    });
    observer.observe(digits, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    await new Promise((resolve) => setTimeout(resolve, milliseconds));
    observer.disconnect();
    return values;
  }, duration);
}

test("timer counts consecutive seconds through polling, phase changes, pause and resume", async ({
  page,
}) => {
  await start(page);
  await page.route("**/api/state", async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 240));
    await route.fulfill({ response });
  });
  const values = await observeClock(page, 6500);
  expect(values.length).toBeGreaterThanOrEqual(6);
  values.slice(1).forEach((v, i) => expect(v - values[i]).toBe(1));
  await page.getByLabel("Current study phase").selectOption("explanation");
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(
    page.getByText("Paused. No active time is being counted."),
  ).toBeVisible();
  expect(await observeClock(page, 2200)).toHaveLength(1);
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  expect((await observeClock(page, 2200)).length).toBeGreaterThanOrEqual(3);
});

test("delayed preference acknowledgement cannot make the next action stale", async ({
  page,
}) => {
  await start(page);
  await page.route("**/api/coach/preferences", async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill({ response });
  });
  await connect(page);
  await expect(
    page.getByRole("alert").filter({ hasText: "session changed" }),
  ).toHaveCount(0);
  await page.getByLabel("Ask your learning coach").fill("unsafe markup");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText(/Markup fixture/)).toBeVisible();
});

test("an old state response cannot resurrect a completed session", async ({
  page,
  request,
}) => {
  await start(page);
  const old = await (await request.get("/api/state")).json();
  await page.getByRole("button", { name: "Finish / stop for today" }).click();
  await page
    .getByLabel("Your takeaway")
    .fill("I will check the smallest example first.");
  await page
    .getByRole("button", { name: "Finish locally", exact: true })
    .click();
  await expect(
    page.getByText("Your complete practice session is saved locally.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.route("**/api/state", (route) => route.fulfill({ json: old }));
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await expect(
    page.getByRole("button", { name: "Start practice", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Resume practice", exact: true }),
  ).toHaveCount(0);
});

test("keyboard send obeys disabled state and preserves a new composer draft", async ({
  page,
}) => {
  await start(page);
  let requests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/coach/requests")) requests++;
  });
  const question = page.getByLabel("Ask your learning coach");
  await question.fill("Do not send while disconnected");
  await question.press("Control+Enter");
  await expect(
    page.getByRole("region", { name: "Assessment help choice" }),
  ).toHaveCount(0);
  expect(requests).toBe(0);
  await connect(page);
  await page.route("**/api/coach/requests", async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({ response });
  });
  await question.fill("slow question");
  await question.press("Control+Enter");
  await expect.poll(() => requests).toBe(1);
  await question.fill("My next question stays here");
  await question.press("Control+Enter");
  await expect(page.locator(".coach-messages")).toContainText("slow question");
  await expect(
    page.getByRole("button", { name: "Send", exact: true }),
  ).toBeEnabled();
  await expect(question).toHaveValue("My next question stays here");
  expect(requests).toBe(1);
});

test("connection failures are visible and actionable from Settings", async ({
  page,
}) => {
  await page.goto("/");
  await page.route("**/api/coach/connect", async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    await route.fulfill({
      json: {
        ...status,
        connection: "unavailable",
        message: "Codex CLI was not found.",
        auth_url: null,
      },
    });
  });
  await page.getByLabel("Settings", { exact: true }).click();
  await page
    .getByRole("button", { name: "Connect Codex", exact: true })
    .click();
  await expect(
    page.getByText("Codex CLI was not found.", { exact: true }),
  ).toBeVisible();
  await page.getByText("Help connecting Codex", { exact: true }).click();
  await expect(
    page.getByText("npm install -g @openai/codex@0.153.4", { exact: true }),
  ).toBeVisible();
});

test("repair timer ticks every second and freezes on pause", async ({
  page,
  request,
}) => {
  await request.post("/__test__/repair", {
    headers: { "X-Study-Request": "1" },
  });
  await page.goto("/");
  await page.getByLabel("Allow new material on weekends").check();
  await page
    .getByRole("button", { name: "Start practice", exact: true })
    .click();
  const values = await observeClock(page, 4200);
  expect(values.length).toBeGreaterThanOrEqual(5);
  values.slice(1).forEach((v, i) => expect(v - values[i]).toBe(1));
  await page.getByRole("button", { name: "Pause & save repair" }).click();
  await expect(
    page.getByRole("button", { name: "Resume repair" }),
  ).toBeVisible();
  expect(await observeClock(page, 2100)).toHaveLength(1);
});

test("practice panels support arrow keys and keep the selected tab focused", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await start(page);
  const codeTab = page.getByRole("tab", { name: "Code", exact: true });
  const problemTab = page.getByRole("tab", { name: "Problem", exact: true });
  await codeTab.focus();
  await codeTab.press("ArrowLeft");
  await expect(problemTab).toBeFocused();
  await expect(problemTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("tabpanel", { name: "Problem", exact: true }),
  ).toBeVisible();
  await problemTab.press("ArrowRight");
  await expect(codeTab).toBeFocused();
  await expect(
    page.getByRole("tabpanel", { name: "Code", exact: true }),
  ).toBeVisible();
  await codeTab.press("End");
  await expect(
    page.getByRole("tab", { name: "Coach", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("complementary", { name: "Codex coach" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Hide coach" }).click();
  await expect(codeTab).toHaveAttribute("aria-selected", "true");
});

test("polling an acknowledged save before its response does not create a false conflict", async ({
  page,
}) => {
  await start(page);
  await page.route("**/api/action/save", async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 2400));
    await route.fulfill({ response });
  });
  const editor = page.getByRole("textbox", { name: "Python solution editor" });
  await editor.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText(
    "def pair_sum_indices(nums, target):\n    return [0, 1]\n",
  );
  await expect(page.locator(".save-status")).toHaveText("Saving…");
  await expect(page.locator(".save-status")).toHaveText("Saved locally");
  await expect(
    page.getByRole("heading", { name: "Two versions need your review" }),
  ).toHaveCount(0);
});
