"""Behavioral recovery checks for the SQLite service and its HTTP boundary."""

import subprocess
import sys
import time
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from study import core, policy
from study.app import create_app
from study.cli import main
from study.service import Conflict, StudyService


def test_storage_failure_is_json_and_completion_rolls_back(guided, monkeypatch):
    state = guided.practice_start(include_new=True, synchronize=False)
    sid = state["session"]["session_id"]
    app = create_app(guided.root)
    original = app.state.service.store.write_json

    def full_disk(path, value):
        if path == ".study-local/last-completion.json":
            raise OSError("Simulated full disk")
        original(path, value)

    monkeypatch.setattr(app.state.service.store, "write_json", full_disk)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/practice/finish",
            headers={"X-Study-Request": "1"},
            json={
                "session_id": sid,
                "revision": guided._session()["revision"],
                "rating": "unknown",
                "stopped": True,
            },
        )
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["code"] == "storage_unavailable"
        assert response.json()["diagnostic_id"]
    assert core.load_session(guided.root)["session_id"] == sid
    assert core.load_events(guided.root) == []


def test_late_save_cannot_write_to_a_different_attempt(guided):
    first = guided.practice_start(include_new=True, synchronize=False)["session"]["session_id"]
    guided.finish(first, "unknown", "", stopped=True)
    second = guided.practice_start(include_new=True, synchronize=False)["session"]
    guided.reasoning("A compact first idea.")
    current = guided.state()["session"]
    with pytest.raises(Conflict, match="active problem changed"):
        guided.save_code("lost old draft", current["revision"], current["code_digest"], first)
    assert guided._code() == current["code"]
    assert guided._session()["session_id"] == second["session_id"]


def test_check_remains_available_after_metadata_changes(guided):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("Try all distinct pairs and compare with the target.")
    observed = guided.state()["session"]
    guided.assistance("minor", "Clarified the meaning of a Python return statement.")
    result = guided.check(
        observed["revision"], session_id=observed["session_id"], code_digest=observed["code_digest"]
    )
    assert result["status"] == "complete"
    assert result["code_digest"] == observed["code_digest"]


def test_changed_browser_build_is_rejected_before_mutation(guided):
    app = create_app(guided.root)
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/practice/start",
        headers={"X-Study-Request": "1", "X-Study-Build": "stale-page"},
        json={"include_new": True, "synchronize": False},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "client_outdated"
    assert guided.state()["session"] is None


def test_real_process_interruption_leaves_the_prior_transaction_intact(guided, tmp_path):
    state = guided.practice_start(include_new=True, synchronize=False)
    old_code = guided._code()
    ready = tmp_path / "transaction-ready"
    program = """
import sys,time
from pathlib import Path
from study.database import StudyStore
store=StudyStore(Path(sys.argv[1])).initialize()
with store.transaction():
    store.write_text('attempt/current.py', '# uncommitted candidate')
    store.write_json('progress/reviews/interrupted.json', {'event_id':'interrupted'})
    Path(sys.argv[2]).write_text('ready')
    time.sleep(30)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", program, str(guided.root), str(ready)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), child.communicate(timeout=2)
        child.terminate()  # Only the process created for this disposable transaction.
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
    restarted = StudyService(guided.root)
    assert restarted._code() == old_code
    assert restarted._session()["session_id"] == state["session"]["session_id"]
    assert core.load_events(guided.root) == []


def test_pending_publication_does_not_require_defer_before_local_continuation(guided, monkeypatch):
    state = guided.practice_start(include_new=True, synchronize=False)
    sid = state["session"]["session_id"]
    guided.practice_finish(sid, "unknown", "", stopped=True, publish=True)
    pull = Mock(side_effect=AssertionError("Local continuation must not contact GitHub"))
    monkeypatch.setattr(guided, "_pull", pull)
    next_state = guided.practice_start(include_new=True, synchronize=False)
    assert next_state["session"]["session_id"] != sid
    assert next_state["unpublished_count"] == 1
    pull.assert_not_called()


def test_multiple_remote_attempts_require_a_choice(guided):
    branches = ["attempt/first", "attempt/second"]
    guided._write_local("remote-attempts", branches)
    state = guided.practice_start(include_new=True, synchronize=False)
    assert state["remote_attempts"] == branches
    assert state["session"] is None and state["practice"] is None


def test_api_supports_explicit_local_start(guided, monkeypatch):
    app = create_app(guided.root)
    pull = Mock(side_effect=AssertionError("Unexpected synchronization"))
    monkeypatch.setattr(app.state.service, "_pull", pull)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/practice/start",
            headers={"X-Study-Request": "1"},
            json={"synchronize": False, "include_new": True},
        )
        assert response.status_code == 200 and response.json()["session"]
    pull.assert_not_called()


def test_cli_migrates_schema_five_before_resuming(guided, monkeypatch):
    core.start_problem(guided.root, "arrays-004-product-others")
    session = core.load_session(guided.root)
    session.update(
        active_started_at=None,
        accumulated_seconds=240,
        hints_used=1,
        initial_reasoning={"approach": "My original idea.", "quality": "novel"},
        assistance_log=[{"level": "guided", "summary": "Original help."}],
    )
    core.save_session(guided.root, session)
    code = guided._code()
    monkeypatch.chdir(guided.root)
    assert main(["practice", "--no-sync"]) == 0
    resumed = guided.state()["session"]
    assert resumed["schema_version"] == 7
    assert resumed["initial_reasoning"] == session["initial_reasoning"]
    assert resumed["assistance_log"] == session["assistance_log"]
    assert resumed["timing"]["unclassified"] == 240
    assert guided._code() == code


def test_unknown_recall_stays_available_for_a_weekend_implementation(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    pid = state["session"]["problem_id"]
    guided.finish(state["session"]["session_id"], "unknown", "", stopped=True)
    sunday = datetime(2026, 10, 4, 14, tzinfo=UTC)
    choice = policy.queue(guided.root, now=sunday, minutes=60)
    assert choice["main"]["id"] == pid and choice["activity"] == "implement"
    assert core.rebuild_cards(guided.root) == {}
    assert policy.queue(guided.root, now=sunday, minutes=5)["main"] is None


@pytest.mark.parametrize("content", ["Fixture token=not-a-secret", r"C:\Users\fixture\notes"])
def test_draft_content_rejection_happens_before_git(guided, monkeypatch, content):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning(content)
    prepare = Mock(side_effect=AssertionError("Sensitive drafts must stay local"))
    monkeypatch.setattr(guided.synchronizer, "prepare", prepare)
    result = guided.practice_pause()
    assert result["sync"]["status"] == "pending"
    assert "Public-content check" in result["sync"]["message"]
    assert guided._session()["initial_reasoning"]["approach"] == content
    assert guided.store.json_documents(".study-local/outbox/") == []
    prepare.assert_not_called()


def test_recall_confirmation_cannot_erase_an_initial_failure(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("I don't know the approach yet.", quality="failed")
    with pytest.raises(RuntimeError, match="Again"):
        guided.finish(
            state["session"]["session_id"], "good", "", stopped=True, recall_confirmed=True
        )
    assert core.load_events(guided.root) == []
    assert guided.evaluate()["recall_outcome"] == "failure"
