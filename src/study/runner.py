"""Interruptible local Python checks. A process boundary is not a security sandbox."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


def execute(
    path: Path, problem: dict, timeout: float = 10, cancel: threading.Event | None = None
) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="study-check-") as directory:
        target = Path(directory)
        (target / "candidate.py").write_bytes(path.read_bytes())
        request = target / "request.json"
        response = target / "response.json"
        request.write_text(json.dumps(problem), encoding="utf-8")
        with (target / "output.log").open("wb") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).with_name("worker.py")),
                    str(request),
                    str(response),
                ],
                stdout=output,
                stderr=output,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            import time

            deadline = time.monotonic() + timeout
            reason = None
            while process.poll() is None:
                if cancel is not None and cancel.is_set():
                    reason = "Check stopped. Your code is saved."
                    break
                if time.monotonic() >= deadline:
                    reason = f"Check timed out after {timeout:g} seconds. Your code is saved."
                    break
                try:
                    process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
            if reason:
                process.kill()
                process.wait()
                return [{"index": 0, "expected": None, "error": reason}]
        if not response.exists():
            return [
                {
                    "index": 0,
                    "expected": None,
                    "error": "Candidate process exited without a result.",
                }
            ]
        return json.loads(response.read_text(encoding="utf-8"))
