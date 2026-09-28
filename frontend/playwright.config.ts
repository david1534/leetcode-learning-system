import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
const local =
  process.platform === "win32"
    ? "../.venv/Scripts/python.exe"
    : "../.venv/bin/python";
const python = existsSync(local) ? resolve(local) : "python";
const port = Number(process.env.PRACTICE_ROOM_TEST_PORT || 8767);
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error(
    "PRACTICE_ROOM_TEST_PORT must be a port between 1024 and 65535.",
  );
}
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" "${resolve("../tests/browser_server.py")}" --port ${port}`,
    url: `http://127.0.0.1:${port}/api/state`,
    reuseExistingServer: false,
    timeout: 30000,
  },
  reporter: [["list"]],
});
