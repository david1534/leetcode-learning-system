import json
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from study import core, gitflow, policy
from study.app import create_app
from study.cli import main
from study.service import Conflict, StudyService
from study.storage import atomic_json


@pytest.mark.parametrize(
    "failure_at", ["parent_event", "parent_receipt", "grouping", "last_receipt"]
)
def test_grouped_completion_recovers_one_review_and_one_budget(guided, monkeypatch, failure_at):
    state = guided.practice_start(minutes=30, include_new=True, synchronize=False)
    sid = state["session"]["session_id"]
    pid = state["practice"]["practice_id"]
    original = atomic_json

    def interrupted(path, value):
        relative = path.relative_to(guided.root).as_posix()
        if (
            failure_at == "parent_event"
            and relative == f"progress/practice-sessions/{pid}.json"
            or failure_at == "parent_receipt"
            and relative == f".study-local/completions/{pid}.json"
            or failure_at == "grouping"
            and value.get("grouped_into") == pid
            or failure_at == "last_receipt"
            and relative == ".study-local/last-completion.json"
            and value.get("session_id") == pid
        ):
            raise PermissionError("Interrupted completion write")
        original(path, value)

    with monkeypatch.context() as patch:
        patch.setattr("study.guided.atomic_json", interrupted)
        with pytest.raises(PermissionError, match="Interrupted"):
            guided.practice_finish(
                sid, "unknown", "Stopped before an approach.", minutes=25, stopped=True
            )
    review = guided.root / "progress/reviews" / f"{sid}.json"
    recorded = review.read_bytes()
    restarted = StudyService(guided.root)
    recovered = restarted.state()
    assert recovered["session"] is None
    assert recovered["practice"]["status"] == "completed"
    assert recovered["completion"]["session_id"] == pid
    assert recovered["unpublished_count"] == 1
    assert review.read_bytes() == recorded
    parents = policy.practice_sessions(guided.root)
    assert len(parents) == 1
    assert parents[0]["minutes"] == 25
    assert sum(parents[0]["timing"].values()) / 60 == pytest.approx(25)
    assert len(core.load_events(guided.root)) == 1
    assert restarted.practice_finish(sid, "unknown", "Retry", stopped=True)["session_id"] == pid
    assert restarted.state()["completion"] == recovered["completion"]
    assert not (guided.local / "practice-completion.json").exists()


def test_rejected_completion_keeps_the_active_parent(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    sid = state["session"]["session_id"]
    guided.reasoning("Try a direct comparison.")
    with pytest.raises(RuntimeError, match="current passing check"):
        guided.practice_finish(sid, "good", "Keep a useful lesson.")
    assert guided.state()["session"]["session_id"] == sid
    assert not core.load_events(guided.root)
    assert not (guided.local / "practice-completion.json").exists()


def test_old_completion_cannot_close_another_active_session(guided):
    first = guided.practice_start(include_new=True, synchronize=False)["session"]["session_id"]
    guided.practice_finish(first, "unknown", "Stopped early.", stopped=True)
    second = guided.practice_start(include_new=True, synchronize=False)["session"]["session_id"]
    with pytest.raises(Conflict, match="active session changed"):
        guided.practice_finish(first, "unknown", "Stale finish.", stopped=True)
    assert guided.state()["session"]["session_id"] == second


def test_pending_publication_can_be_deferred_before_local_continuation(guided, monkeypatch):
    state = guided.practice_start(include_new=True, synchronize=False)
    sid = state["session"]["session_id"]
    guided.practice_finish(sid, "unknown", "Stopped early.", stopped=True, publish=True)
    # A folder without a remote retains the same pending publication as an offline push.
    assert (guided.local / "pending.json").exists()
    parent = guided.state()["practice"]
    with pytest.raises(RuntimeError, match="Keep local and continue"):
        guided.practice_start(include_new=True, synchronize=False)
    assert guided.state()["practice"] == parent
    guided.keep_local()
    pull = Mock(side_effect=AssertionError("Local continuation must not contact GitHub"))
    monkeypatch.setattr(guided, "_pull", pull)
    resumed = guided.practice_start(include_new=True, synchronize=False)
    assert resumed["session"]["session_id"] != sid
    assert resumed["unpublished_count"] == 1
    assert len(core.load_events(guided.root)) == 1
    pull.assert_not_called()


def test_multiple_remote_attempts_do_not_create_a_parent(guided):
    branches = ["attempt/first", "attempt/second"]
    atomic_json(guided.local / "remote-attempts.json", branches)
    state = guided.practice_start(include_new=True, synchronize=False)
    assert state["remote_attempts"] == branches
    assert state["session"] is None and state["practice"] is None
    assert not (guided.local / "practice.json").exists()


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
        assert response.status_code == 200
        assert response.json()["session"]
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
    candidate = guided.root / "attempt/current.py"
    original = candidate.read_bytes()
    monkeypatch.chdir(guided.root)
    assert main(["practice", "--no-sync"]) == 0
    resumed = guided.state()["session"]
    assert resumed["schema_version"] == 6
    assert resumed["initial_reasoning"] == session["initial_reasoning"]
    assert resumed["assistance_log"] == session["assistance_log"]
    assert resumed["hints_used"] == 1
    assert resumed["timing"]["unclassified"] == 240
    assert candidate.read_bytes() == original


def test_unknown_recall_remains_available_for_implementation_on_weekends(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    sid, pid = state["session"]["session_id"], state["session"]["problem_id"]
    guided.practice_finish(sid, "unknown", "Stopped early.", stopped=True)
    sunday = datetime(2026, 10, 4, 14, tzinfo=UTC)
    choice = policy.queue(guided.root, now=sunday, minutes=60)
    assert choice["main"]["id"] == pid and choice["activity"] == "implement"
    assert core.rebuild_cards(guided.root) == {}
    assert core.load_events(guided.root)[0]["rating"] == "unknown"
    assert policy.queue(guided.root, now=sunday, minutes=5)["main"] is None
    resumed = guided.practice_start(include_new=True, synchronize=False)
    assert not resumed["session"]["unseen"]


def test_unassessed_retry_respects_prerequisites_and_repairs(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    pid = state["session"]["problem_id"]
    problem = core.problem_by_id(guided.root, pid)
    core.record_learning_error(
        guided.root,
        problem["skill_ids"][0],
        "invariant",
        "misconception",
        "blocking",
        "A missing condition.",
        "Recognize a boundary.",
        "Check the boundary.",
        "Apply the rule to a fresh example.",
    )
    guided.practice_finish(state["session"]["session_id"], "unknown", "Stopped.", stopped=True)
    choice = policy.queue(guided.root, include_new=True)
    assert choice["main"] is None or choice["main"]["id"] != pid
    catalog_path = guided.root / "curriculum/problems.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    next(p for p in catalog["problems"] if p["id"] == pid)["prerequisites"] = [
        "unmet-fixture-anchor"
    ]
    # Remove only this fixture's error to isolate the prerequisite rule.
    for path in (guided.root / "progress/learning-events").glob("*.json"):
        if json.loads(path.read_text(encoding="utf-8"))["event_type"] == "error":
            path.unlink()
    atomic_json(catalog_path, catalog)
    choice = policy.queue(guided.root, include_new=True)
    assert choice["main"] is None or choice["main"]["id"] != pid


@pytest.mark.parametrize("operation", ["pause", "sync"])
@pytest.mark.parametrize("content", ["Fixture token=not-a-secret", r"C:\Users\fixture\notes"])
def test_draft_sync_checks_content_before_git(guided, monkeypatch, operation, content):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning(content)
    (guided.root / ".git").mkdir()
    commit, push = Mock(), Mock()
    monkeypatch.setattr(gitflow, "commit_paths", commit)
    monkeypatch.setattr(gitflow, "push_current", push)
    result = getattr(guided, operation)()
    sync = result["sync"] if operation == "pause" else result
    assert sync["status"] == "pending"
    assert "Public-content check" in sync["message"]
    assert core.load_session(guided.root)["initial_reasoning"]["approach"] == content
    commit.assert_not_called()
    push.assert_not_called()


def test_portable_draft_checks_embedded_supporting_artifacts(guided, monkeypatch):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("A safe recorded answer.")
    portable = {
        "parent": guided._practice(),
        "repair": None,
        "receipts": {},
        "artifacts": {
            "progress/attempts/fixture/session.json": json.dumps(
                {"approach": r"C:\Users\fixture\private-notes"}
            )
        },
    }
    atomic_json(guided.root / "attempt/practice.json", portable)
    (guided.root / ".git").mkdir()
    commit, push = Mock(), Mock()
    monkeypatch.setattr(gitflow, "commit_paths", commit)
    monkeypatch.setattr(gitflow, "push_current", push)
    result = guided.pause()
    assert result["sync"]["status"] == "pending"
    assert "practice.json" in result["sync"]["message"]
    assert (guided.root / "attempt/practice.json").exists()
    commit.assert_not_called()
    push.assert_not_called()
