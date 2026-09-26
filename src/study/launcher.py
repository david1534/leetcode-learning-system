"""Own one background app process per workspace and wait for confirmed readiness."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path

from filelock import FileLock

from study.build import build_id
from study.database import StudyStore, workspace_id
from study.storage import atomic_json


def local_request(url, *, data=None, owner=None):
    headers = {"X-Study-Request": "1", "Content-Type": "application/json"}
    if owner:
        headers["X-Study-Owner"] = owner
    request = urllib.request.Request(
        url, data=None if data is None else json.dumps(data).encode(), headers=headers
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=1) as response:
        return json.load(response)


def health(url):
    try:
        return local_request(url + "/api/health")
    except (OSError, ValueError, urllib.error.URLError):
        return None


def background(command, root, output, env=None):
    options = {
        "cwd": root,
        "stdin": subprocess.DEVNULL,
        "stdout": output,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return subprocess.Popen(command, **options)


def launch(root: Path, port=8765, open_browser=True, restart=False):
    root = root.resolve()
    store = StudyStore(root)
    store.directory.mkdir(parents=True, exist_ok=True)
    descriptor_path = store.directory / "server.json"
    with FileLock(str(store.directory / "launcher.lock"), timeout=20):
        descriptor = (
            json.loads(descriptor_path.read_text(encoding="utf-8"))
            if descriptor_path.exists()
            else {}
        )
        url = descriptor.get("url", f"http://127.0.0.1:{port}")
        active = health(url)
        owned = (
            active
            and active.get("workspace") == workspace_id(root)
            and active.get("instance_id") == descriptor.get("instance_id")
        )
        if owned and (restart or active.get("build_id") != build_id()):
            local_request(url + "/api/app/shutdown", data={}, owner=descriptor["owner"])
            deadline = time.monotonic() + 15
            while health(url) and time.monotonic() < deadline:
                time.sleep(0.1)
            if health(url):
                raise RuntimeError(
                    "The previous app is still saving. Wait a moment and reopen Start Study."
                )
            port = descriptor["port"]
            active = None
        elif owned:
            if open_browser:
                webbrowser.open(url)
            return {"url": url, "pid": descriptor["pid"], "reused": True}
        # An occupied port never authorizes stopping another process or workspace.
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        descriptor = {
            "url": url,
            "port": port,
            "owner": uuid.uuid4().hex,
            "instance_id": uuid.uuid4().hex,
            "workspace": workspace_id(root),
        }
        env = {
            **os.environ,
            "PRACTICE_ROOM_SERVER_OWNER": descriptor["owner"],
            "PRACTICE_ROOM_SERVER_INSTANCE": descriptor["instance_id"],
        }
        with (store.directory / "server.log").open("a", encoding="utf-8") as output:
            process = background(
                [
                    sys.executable,
                    "-m",
                    "study",
                    "--root",
                    str(root),
                    "app",
                    "--serve",
                    "--no-open",
                    "--port",
                    str(port),
                ],
                root,
                output,
                env,
            )
        descriptor["pid"] = process.pid
        atomic_json(descriptor_path, descriptor)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            ready = health(url)
            if ready and ready.get("instance_id") == descriptor["instance_id"]:
                if open_browser:
                    webbrowser.open(url)
                return {"url": url, "pid": process.pid, "reused": False}
            if process.poll() is not None:
                raise RuntimeError(
                    "Practice Room could not start. "
                    f"Read the private log: {store.directory / 'server.log'}"
                )
            time.sleep(0.1)
        raise RuntimeError(
            "Practice Room is taking longer to start. Reopen Start Study to "
            "reconnect; the private server log has details."
        )


def request_restart(root: Path):
    store = StudyStore(root)
    command = [sys.executable, "-m", "study", "--root", str(root), "app", "--restart", "--no-open"]
    script = root / "scripts/study.ps1"
    if os.name == "nt" and script.is_file():
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "app",
            "--restart",
            "--no-open",
        ]
    with (store.directory / "server.log").open("a", encoding="utf-8") as output:
        background(command, root, output)


def serve(root: Path, port: int):
    import uvicorn

    from study.app import create_app

    app = create_app(root)
    app.state.instance_id = os.environ.get("PRACTICE_ROOM_SERVER_INSTANCE") or uuid.uuid4().hex
    app.state.owner = os.environ.get("PRACTICE_ROOM_SERVER_OWNER") or uuid.uuid4().hex
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    app.state.shutdown = lambda: setattr(server, "should_exit", True)
    server.run()
