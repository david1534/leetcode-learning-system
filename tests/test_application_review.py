import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from study import gitflow
from study.app import create_app
from study.core import load_session
from study.service import Conflict


def test_state_samples_order_refreshes_without_changing_evidence(guided):
    guided.practice_start(include_new=True, synchronize=False)
    first = guided.state()
    second = guided.state()
    assert first["observed_at"] < second["observed_at"]
    assert first["session"]["revision"] == second["session"]["revision"]
    assert second["practice"]["elapsed_seconds"] >= first["practice"]["elapsed_seconds"]
    assert "observed_at" not in load_session(guided.root)


def test_private_api_responses_are_not_cached(guided):
    client = TestClient(create_app(guided.root), base_url="http://127.0.0.1")
    for path in ("/api/health", "/api/state", "/api/coach/status"):
        assert client.get(path).headers["cache-control"] == "no-store"


def test_missing_git_is_a_recoverable_setup_error(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gitflow.subprocess, "run", missing)
    result = gitflow.run_git(tmp_path, "status")
    assert result.code == 127
    assert "Install Git" in result.output


def test_a_draft_from_a_previous_session_cannot_overwrite_a_new_exercise(guided):
    first = guided.practice_start(include_new=True, synchronize=False)["session"]
    guided.practice_finish(
        first["session_id"], "unknown", "Stopped before recording an idea.", stopped=True
    )
    current = guided.practice_start(include_new=True, synchronize=False)["session"]
    guided.reasoning("Compare each pair with the target.")
    with pytest.raises(Conflict, match="exercise changed"):
        guided.save_code(
            "old draft", current["revision"], current["code_digest"], session_id=first["session_id"]
        )
    assert guided.state()["session"]["code"] != "old draft"


def test_windows_checkout_preserves_historical_artifacts_byte_for_byte(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    def git(*args, cwd=source):
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)
        return result.stdout

    git("init")
    git("config", "core.autocrlf", "true")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (source / ".gitattributes").write_bytes(
        (Path(__file__).parents[1] / ".gitattributes").read_bytes()
    )
    record = b'{"rating": "good", "minutes": 12}\r\n'
    for path in ("progress/reviews/history.json", "solutions/earlier.py", "reflections/earlier.md"):
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(record)
    git("add", ".")
    git("commit", "-m", "Fixture")
    checkout = tmp_path / "checkout"
    git("-c", "core.autocrlf=true", "clone", str(source), str(checkout))
    assert git("status", "--porcelain", cwd=checkout) == b""
    assert (checkout / "progress/reviews/history.json").read_bytes() == record
