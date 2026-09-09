"""Versioned, subscription-only JSONL adapter. No agent tools are exposed."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from study import __version__
from study.storage import atomic_text

SUPPORTED_VERSIONS = {"0.153.4"}
CONFIG = """forced_login_method = "chatgpt"
model_provider = "openai"
sandbox_mode = "read-only"
approval_policy = "never"
web_search = "disabled"
project_doc_max_bytes = 0
include_apps_instructions = false
include_environment_context = false
include_collaboration_mode_instructions = false
[features]
shell_tool = false
unified_exec = false
multi_agent = false
memories = false
apps = false
plugins = false
remote_plugin = false
tool_suggest = false
skill_search = false
skill_mcp_dependency_install = false
skip_host_skill_discovery = true
browser_use = false
browser_use_external = false
computer_use = false
view_image = false
image_generation = false
goals = false
hooks = false
sleep_tool = false
workspace_dependencies = false
auth_elicitation = false
[features.code_mode]
enabled = false
[memories]
generate_memories = false
use_memories = false
[apps._default]
enabled = false
[analytics]
enabled = false
"""


def codex_candidates() -> list[Path]:
    """Discover launchers without changing PATH or copying desktop credentials."""
    override = os.environ.get("PRACTICE_ROOM_CODEX")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise RuntimeError(
                "PRACTICE_ROOM_CODEX must name an existing absolute Codex executable path."
            )
        return [path]
    paths = []
    executable = shutil.which("codex")
    if executable:
        paths.append(Path(executable))
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            bundled = Path(local) / "OpenAI/Codex/bin"
            paths.extend(
                sorted(bundled.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
            )
            paths.append(bundled / "codex.exe")
        roaming = os.environ.get("APPDATA")
        if roaming:
            paths.append(Path(roaming) / "npm/codex.cmd")
    else:
        paths.extend([Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex")])
    return list(dict.fromkeys(p for p in paths if p.is_file()))


def codex_command(path: Path) -> list[str]:
    if path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        # npm's Windows shim needs a shell. Launch its JS entry point directly,
        # so paths containing spaces or shell metacharacters remain literal.
        entry = path.parent / "node_modules/@openai/codex/bin/codex.js"
        node = path.parent / "node.exe"
        executable = str(node) if node.is_file() else shutil.which("node")
        if not entry.is_file() or not executable:
            raise RuntimeError(
                "The Codex npm installation is incomplete. Reinstall the supported CLI and Node.js."
            )
        return [executable, str(entry)]
    return [str(path)]


def find_codex() -> tuple[list[str], str]:
    errors = []
    for path in codex_candidates():
        try:
            command = codex_command(path)
            result = subprocess.run(
                [*command, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            version = result.stdout.strip().removeprefix("codex-cli ")
            if result.returncode == 0 and version in SUPPORTED_VERSIONS:
                return command, version
            errors.append(
                f"Codex {version or 'unknown version'} has not been validated for this coach."
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            errors.append(str(exc))
    setup = (
        "Install Codex CLI 0.153.4 with npm install -g @openai/codex@0.153.4, "
        "then reconnect. Practice and saving remain available."
    )
    if errors:
        raise RuntimeError(errors[0] + " " + setup)
    raise RuntimeError(
        "Codex CLI was not found in PATH or the usual installation folders. " + setup
    )


class CodexRuntime:
    def __init__(self, directory: Path, command: list[str] | None = None):
        self.directory = directory.resolve()
        self.command = command
        self.process = None
        self.pending = {}
        self.ids = 0
        self.write_lock = threading.Lock()
        self.changed = threading.Condition()
        self.turns = {}
        self.on_event = lambda method, params: None
        self.version = None
        self.closed = threading.Event()
        self.reader = None

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if self.process or self.reader:
            self.close()
        self.directory.mkdir(parents=True, exist_ok=True)
        home = self.directory / "home"
        work = self.directory / "workspace"
        home.mkdir(exist_ok=True)
        work.mkdir(exist_ok=True)
        atomic_text(home / "config.toml", CONFIG)
        cmd = self.command
        if cmd is None:
            command, self.version = find_codex()
            cmd = [*command, "app-server", "--strict-config", "--listen", "stdio://"]
        else:
            self.version = "test-adapter"
        # A child-specific Codex home owns its login. Never copy the desktop's credentials.
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("OPENAI_", "AZURE_", "AWS_", "ANTHROPIC_", "CODEX_"))
        }
        env["CODEX_HOME"] = str(home)
        self.process = subprocess.Popen(
            cmd,
            cwd=work,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.closed.clear()
        self.turns.clear()
        self.reader = threading.Thread(target=self._read, args=(self.process,), daemon=True)
        self.reader.start()
        try:
            self._initialize()
        except Exception:
            self.close()
            raise

    def _initialize(self):
        self.call(
            "initialize",
            {
                "clientInfo": {"name": "practice_room", "version": __version__},
                "capabilities": {"experimentalApi": False},
            },
        )
        self.send({"method": "initialized", "params": {}})
        if self.command is None:
            import tomllib

            actual = self.call("config/read", {"includeLayers": False}).get("config", {})
            expected = tomllib.loads(CONFIG)

            def matches(wanted, found):
                return isinstance(found, dict) and all(
                    matches(value, found.get(key))
                    if isinstance(value, dict)
                    else found.get(key) == value
                    for key, value in wanted.items()
                )

            if not matches(expected, actual) or any(
                actual.get(k)
                for k in ("mcp_servers", "plugins", "hooks", "notify", "model_providers")
            ):
                self.close()
                raise RuntimeError(
                    "Codex could not confirm the restricted coaching configuration. "
                    "Practice remains available."
                )

    def send(self, message):
        with self.write_lock:
            if not self.process or self.process.poll() is not None:
                raise RuntimeError("Codex disconnected. Reconnect to resume coaching.")
            try:
                self.process.stdin.write(json.dumps(message) + "\n")
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise RuntimeError("Codex connection closed. Your work is saved.") from exc

    def call(self, method, params=None, timeout=20):
        with self.changed:
            self.ids += 1
            request_id = self.ids
            response = queue.Queue(maxsize=1)
            self.pending[request_id] = response
        try:
            self.send({"id": request_id, "method": method, "params": params or {}})
            message = response.get(timeout=timeout)
            if "error" in message:
                raise RuntimeError(
                    message["error"].get("message", "Codex could not complete the request.")
                )
            return message.get("result", {})
        except queue.Empty as exc:
            raise RuntimeError(
                "Codex did not confirm the request. Reconnect to check its status."
            ) from exc
        finally:
            self.pending.pop(request_id, None)

    def _read(self, process):
        try:
            for line in process.stdout:
                if len(line) > 8_000_000:
                    raise RuntimeError("Codex response exceeded the local safety limit.")
                message = json.loads(line)
                if "id" in message and "method" not in message:
                    target = self.pending.get(message["id"])
                    if target:
                        target.put_nowait(message)
                    continue
                if "id" in message:
                    # An unexpected tool or approval is never forwarded to the learner or executed.
                    self.send(
                        {
                            "id": message["id"],
                            "error": {
                                "code": -32601,
                                "message": "Tools are disabled in the learning coach.",
                            },
                        }
                    )
                    self.on_event("coach/unsupportedTool", {})
                    process.terminate()
                    break
                method, params = message.get("method"), message.get("params", {})
                turn_id = params.get("turnId") or params.get("turn", {}).get("id")
                with self.changed:
                    if turn_id:
                        turn = self.turns.setdefault(turn_id, {"texts": []})
                        if (
                            method == "item/completed"
                            and params.get("item", {}).get("type") == "agentMessage"
                        ):
                            item = params["item"]
                            if item.get("phase") != "commentary":
                                turn["texts"].append(item.get("text", ""))
                        if method == "turn/completed":
                            turn["result"] = params["turn"]
                        self.changed.notify_all()
                self.on_event(method, params)
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            self.closed.set()
            for target in list(self.pending.values()):
                try:
                    target.put_nowait(
                        {"error": {"message": "Codex disconnected. Reconnect to recover."}}
                    )
                except queue.Full:
                    pass
            self.on_event("coach/disconnected", {})
            with self.changed:
                self.changed.notify_all()

    def wait_turn(self, turn_id, timeout=180):
        deadline = time.monotonic() + timeout
        with self.changed:
            while time.monotonic() < deadline:
                turn = self.turns.get(turn_id, {})
                if "result" in turn:
                    if turn["result"]["status"] != "completed":
                        raise RuntimeError(
                            "Coaching stopped before a complete reply. Your draft is saved."
                        )
                    return "\n".join(turn["texts"])
                if self.closed.is_set() or not self.process or self.process.poll() is not None:
                    raise RuntimeError("Codex disconnected during its reply. Reconnect to recover.")
                self.changed.wait(timeout=min(1, max(0, deadline - time.monotonic())))
        raise RuntimeError("Coaching took too long. Stop or reconnect; your work is saved.")

    def close(self):
        proc = self.process
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=5)
        if proc:
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    stream.close()
        self.reader = None
        self.process = None
        self.closed.set()
