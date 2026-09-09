import json

import pytest
from test_cross_device import clone, seed_remote

from study import core, gitflow
from study.service import StudyService


def prepare_service(root, repo_root):
    service = StudyService(root)
    service.start("arrays-001-pair-sum", synchronize=False)
    service.reasoning("Map prior values to their indices; look up the complement first.")
    reference = json.loads((repo_root / "curriculum/validation.json").read_text(encoding="utf-8"))
    session = service.state()["session"]
    service.save_code(reference[session["problem_id"]]["reference"], session["revision"])
    return service


def test_offline_completion_retry_has_one_review(monkeypatch, tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    laptop = clone(remote, tmp_path / "offline-laptop")
    service = prepare_service(laptop, repo_root)
    service.check()
    sid = service.state()["session"]["session_id"]
    with monkeypatch.context() as context:

        def offline(*args, **kwargs):
            raise gitflow.GitFlowError("Simulated connection loss")

        context.setattr(gitflow, "push_current", offline)
        result = service.finish(sid, "good", "Check before insertion.", True, True, publish=True)
        assert not result["published"]
        assert service.state()["session"] is None
        assert len(core.load_events(laptop)) == 1
    assert service.publish(sid)["status"] == "synced"
    assert service.publish(sid)["published"]
    other = clone(remote, tmp_path / "after-publication")
    assert len(core.load_events(other)) == 1
    assert (other / "progress/attempts" / sid / "candidate.py").exists()


def test_divergent_drafts_are_preserved_on_separate_branches(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    a = clone(remote, tmp_path / "device-a")
    first = prepare_service(a, repo_root)
    assert first.pause()["sync"]["status"] == "synced"
    b = clone(remote, tmp_path / "device-b")
    second = StudyService(b)
    second.start()
    state = second.state()["session"]
    second.save_code(state["code"] + "\n# Device B\n", state["revision"])
    assert second.pause()["sync"]["status"] == "synced"
    state = first.start(synchronize=False)["session"]
    first.save_code(state["code"] + "\n# Device A\n", state["revision"])
    assert first.pause()["sync"]["status"] == "pending"
    assert "Device A" in (a / "attempt/current.py").read_text()
    first.recover()
    assert first.sync()["status"] == "synced"
    observer = clone(remote, tmp_path / "observer")
    observer_service = StudyService(observer)
    choice = observer_service.start()
    assert choice["session"] is None
    assert len(choice["remote_attempts"]) == 2
    selected = observer_service.choose_attempt("attempt/arrays-001-pair-sum")
    assert "Device B" in selected["session"]["code"]
    assert list((a / ".study-local/recovery").glob("*/current.py"))


def test_multiple_local_sessions_keep_individual_reflections(tmp_path, repo_root):
    remote, _ = seed_remote(tmp_path, repo_root)
    laptop = clone(remote, tmp_path / "offline-series")
    service = prepare_service(laptop, repo_root)
    service.check()
    first = service.state()["session"]["session_id"]
    service.finish(first, "good", "First takeaway.", True, True)
    service = prepare_service(laptop, repo_root)
    service.check()
    second = service.state()["session"]["session_id"]
    service.finish(second, "good", "Second takeaway.", True, True)
    with pytest.raises(RuntimeError, match="Several sessions"):
        service.publish(second)
    assert service.publish(second, include_saved=True)["status"] == "synced"
    after = clone(remote, tmp_path / "series-published")
    assert len(core.load_events(after)) == 2
    assert "First takeaway." in (after / "progress/attempts" / first / "reflection.md").read_text()
    assert (
        "Second takeaway." in (after / "progress/attempts" / second / "reflection.md").read_text()
    )
