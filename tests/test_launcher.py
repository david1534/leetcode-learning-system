"""Exercise the actual background launcher in disposable workspaces."""

import json
import socket
import subprocess
import sys
import time

from study import launcher


def stop_server(store):
    descriptor = json.loads((store.directory / "server.json").read_text(encoding="utf-8"))
    launcher.local_request(
        descriptor["url"] + "/api/app/shutdown", data={}, owner=descriptor["owner"]
    )
    deadline = time.monotonic() + 15
    while launcher.health(descriptor["url"]) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not launcher.health(descriptor["url"])


def test_launcher_exits_server_survives_relaunch_and_restart(guided):
    command = [
        sys.executable,
        "-m",
        "study",
        "--root",
        str(guided.root),
        "app",
        "--port",
        "0",
        "--no-open",
    ]
    first = subprocess.run(command, capture_output=True, text=True, timeout=35)
    assert first.returncode == 0, first.stderr
    descriptor = json.loads((guided.local / "server.json").read_text(encoding="utf-8"))
    url = descriptor["url"]
    try:
        assert launcher.health(url)["version"] == "0.4.0"
        state = launcher.local_request(
            url + "/api/practice/start", data={"include_new": True, "synchronize": False}
        )
        sid = state["session"]["session_id"]
        launcher.local_request(
            url + "/api/action/reasoning",
            data={"answer": "Preserve my reasoning across a real process restart."},
        )
        second = subprocess.run(command, capture_output=True, text=True, timeout=35)
        assert second.returncode == 0, second.stderr
        assert json.loads((guided.local / "server.json").read_text())["pid"] == descriptor["pid"]
        changed = launcher.launch(guided.root, open_browser=False, restart=True)
        assert changed["pid"] != descriptor["pid"]
        restored = launcher.local_request(changed["url"] + "/api/state")["session"]
        assert restored["session_id"] == sid
        assert restored["initial_reasoning"]["approach"].startswith("Preserve my reasoning")
        assert restored["phase_started_at"] is None
    finally:
        stop_server(guided.store)


def test_occupied_port_is_preserved_and_browser_gets_an_available_port(guided):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        result = launcher.launch(guided.root, port, open_browser=False)
        try:
            assert result["url"] != f"http://127.0.0.1:{port}"
            assert launcher.health(result["url"])["workspace"]
            assert occupied.getsockname()[1] == port
        finally:
            stop_server(guided.store)
