import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
const local =
  process.platform === "win32"
    ? "../.venv/Scripts/python.exe"
    : "../.venv/bin/python";
const python = existsSync(local) ? resolve(local) : "python";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:8767",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" "${resolve("../tests/browser_server.py")}"`,
    url: "http://127.0.0.1:8767/api/state",
    reuseExistingServer: false,
    timeout: 30000,
  },
  reporter: [["list"]],
});
