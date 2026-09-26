"""Use real local Git remotes to exercise synchronization separately from saving."""

import json

import pytest
from test_cross_device import clone, git, seed_remote

from study import core
from study.service import StudyService
from study.synchronization import Synchronizer


@pytest.fixture(autouse=True)
def controlled_worker(monkeypatch):
    monkeypatch.setattr(Synchronizer, "wake", lambda self, pull=False: None)


def prepared(root, repo_root):
    service = StudyService(root)
    state = service.start("arrays-001-pair-sum", include_new=True, synchronize=False)["session"]
    service.reasoning(
        "Map earlier values to indices; look up the complement first.", quality="complete"
    )
    reference = json.loads((repo_root / "curriculum/validation.json").read_text(encoding="utf-8"))
    service.save_code(reference[state["problem_id"]]["reference"], service._session()["revision"])
    return service


def test_pause_sync_and_resume_do_not_switch_or_modify_source_checkout(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    a = clone(remote, tmp_path / "a")
    (a / "README.md").write_text("Unrelated source draft", encoding="utf-8")
    first = prepared(a, repo_root)
    sid = first._session()["session_id"]
    first.pause(synchronize=False)
    result = first.sync(wait=True)
    assert result["status"] == "synced", result
    assert git(a, "branch", "--show-current") == "main"
    assert (a / "README.md").read_text() == "Unrelated source draft"
    assert not (a / "attempt").exists()
    b = clone(remote, tmp_path / "b")
    second = StudyService(b)
    state = second.start()["session"]
    assert state["session_id"] == sid
    assert state["code"] == first._code()
    assert git(b, "branch", "--show-current") == "main"


def test_local_completion_publishes_and_retry_is_idempotent(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    root = clone(remote, tmp_path / "local")
    service = prepared(root, repo_root)
    service.check()
    sid = service._session()["session_id"]
    service.finish(sid, "good", "Look up the complement first.", True, True)
    result = service.publish(sid, wait=True)
    assert result["status"] == "synced", result
    assert service.publish(sid, wait=True)["published"]
    other = clone(remote, tmp_path / "other")
    assert len(core.load_events(other)) == 1
    assert core.load_events(other)[0]["event_id"] == sid
    assert git(root, "branch", "--show-current") == "main"
    assert (other / "progress/attempts" / sid / "candidate.py").exists()


def test_divergence_preserves_both_drafts(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    a = clone(remote, tmp_path / "a")
    first = prepared(a, repo_root)
    first.pause(synchronize=False)
    assert first.sync(wait=True)["status"] == "synced"
    b = clone(remote, tmp_path / "b")
    second = StudyService(b)
    s = second.start()["session"]
    second.save_code(s["code"] + "\n# from B\n", s["revision"])
    second.pause(synchronize=False)
    assert second.sync(wait=True)["status"] == "synced"
    s = first.start(synchronize=False)["session"]
    first.save_code(s["code"] + "\n# from A\n", s["revision"])
    first.pause(synchronize=False)
    result = first.sync(wait=True)
    assert result["status"] == "pending"
    assert "another computer" in result["message"]
    assert "from A" in first._code()
    assert "from B" in second._code()


def test_publication_does_not_block_next_local_problem(guided):
    sid = guided.practice_start(include_new=True, synchronize=False)["session"]["session_id"]
    guided.finish(sid, "unknown", "", publish=True, stopped=True)
    assert guided.state()["session"] is None
    assert guided.state()["unpublished_count"] == 1
    next_state = guided.practice_start(include_new=True, synchronize=False)
    assert next_state["session"]["session_id"] != sid
    assert len(core.load_events(guided.root)) == 1


def test_publishing_one_session_does_not_include_a_later_private_reflection(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    root = clone(remote, tmp_path / "selected-publication")
    service = prepared(root, repo_root)
    service.check()
    first = service._session()["session_id"]
    service.finish(first, "good", "Approved first takeaway.", True, True)
    service = prepared(root, repo_root)
    service.check()
    second = service._session()["session_id"]
    service.finish(second, "good", "Private fixture token=not-a-secret", True, True)
    result = service.publish(first, wait=True)
    assert result["status"] == "synced", result
    observer = clone(remote, tmp_path / "selected-observer")
    assert [event["event_id"] for event in core.load_events(observer)] == [first]
    text = (observer / "reflections/arrays-001-pair-sum.md").read_text()
    assert "Approved first takeaway" in text and "Private fixture" not in text
    assert service.state()["unpublished_count"] == 1
    assert service._read_local("completions/" + second)["published"] is False


def test_a_new_attempt_uses_its_own_draft_branch(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    root = clone(remote, tmp_path / "repeat-review")
    service = prepared(root, repo_root)
    service.pause(synchronize=False)
    assert service.sync(wait=True)["status"] == "synced"
    first_branch = service._session()["sync_branch"]
    service.check()
    service.finish(service._session()["session_id"], "good", "First review.", True, True)
    assert (
        service.publish(service.state()["completion"]["session_id"], wait=True)["status"]
        == "synced"
    )
    service = prepared(root, repo_root)
    service.pause(synchronize=False)
    result = service.sync(wait=True)
    assert result["status"] == "synced", result
    assert service._session()["sync_branch"] != first_branch


def test_rejected_publication_is_not_reported_as_a_successful_pull(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    root = clone(remote, tmp_path / "private-only")
    service = prepared(root, repo_root)
    service.check()
    sid = service._session()["session_id"]
    service.finish(sid, "good", "Fixture token=keep-local", True, True)
    result = service.publish(sid, wait=True)
    assert result["status"] == "pending"
    assert "Public-content check" in result["message"]
    assert service._read_local("completions/" + sid)["published"] is False
    observer = clone(remote, tmp_path / "private-observer")
    assert core.load_events(observer) == []


def test_git_archive_line_endings_do_not_change_the_saved_candidate(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    a = clone(remote, tmp_path / "crlf-a")
    first = prepared(a, repo_root)
    first.pause(synchronize=False)
    assert first.sync(wait=True)["status"] == "synced"
    b = clone(remote, tmp_path / "crlf-b")
    second = StudyService(b)
    second.synchronizer.prepare()
    second.synchronizer.git("config", "core.autocrlf", "true")
    restored = second.start()["session"]
    assert restored["code"] == first._code()
    assert restored["code_digest"] == first._session()["code_digest"]
