"""Persistence acceptance tests use real SQLite and disposable learner workspaces."""

import ctypes
import hashlib
import json
import os
import shutil
from datetime import UTC, datetime

import pytest

from study import core
from study.database import StudyStore
from study.service import StudyService

PAIR = "arrays-001-pair-sum"


def open_attempt(service):
    session = service.start(PAIR, include_new=True, synchronize=False)["session"]
    service.reasoning("I would track earlier values and look up the complement first.")
    return session["session_id"]


def test_completion_is_a_single_transaction_and_retry_keeps_one_event(guided, monkeypatch):
    sid = open_attempt(guided)
    candidate = guided._code()
    original = guided.store.write_json

    def fail_receipt(path, value):
        if path == ".study-local/last-completion.json":
            raise OSError("Simulated disk write failure")
        original(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(guided.store, "write_json", fail_receipt)
        with pytest.raises(OSError, match="disk write"):
            guided.finish(sid, "unknown", "", stopped=True)
    assert guided.state()["session"]["session_id"] == sid
    assert guided._code() == candidate
    assert core.load_events(guided.root) == []
    assert guided.store.paths("progress/attempts/") == []
    receipt = guided.finish(sid, "unknown", "", stopped=True)
    restarted = StudyService(guided.root)
    assert restarted.finish(sid, "unknown", "Retry", stopped=True) == receipt
    assert restarted.state()["session"] is None
    assert len(core.load_events(guided.root)) == 1
    assert not (guided.root / "attempt").exists()


def test_old_receipt_cannot_close_a_new_attempt(guided):
    first = open_attempt(guided)
    receipt = guided.finish(first, "unknown", "", stopped=True)
    second = open_attempt(guided)
    assert guided.finish(first, "unknown", "Retry", stopped=True) == receipt
    assert guided.state()["session"]["session_id"] == second


def test_one_problem_and_unknown_recall_until_confirmed(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    assert len(state["practice"]["stages"]) == 1
    assert state["session"]["assessment_mode"] == "practice"
    sid = state["session"]["session_id"]
    guided.reasoning("I would try an approach and explain the condition.")
    assert guided.evaluate()["recall_outcome"] == "unknown"
    guided.finish(sid, "good", "", stopped=True, recall_confirmed=True)
    assert core.load_events(guided.root)[0]["recall_outcome"] == "success"
    assert not core.is_independent_successful_review(core.load_events(guided.root)[0])
    assert guided.state()["session"] is None


def test_timer_checkpoint_does_not_invalidate_editor_revision(guided):
    open_attempt(guided)
    before = guided.state()["session"]
    guided.timer_checkpoint()
    guided.evaluate()
    assert guided.state()["session"]["revision"] == before["revision"]
    guided.save_code("def pair_sum_indices(nums, target): return []\n", before["revision"])


def test_existing_history_import_preserves_ids_schedules_and_originals(tmp_path, repo_root):
    root = tmp_path / "legacy"
    root.mkdir()
    shutil.copytree(repo_root / "curriculum", root / "curriculum")
    core.record_review(
        root,
        core.problem_by_id(root, PAIR),
        "good",
        20,
        True,
        0,
        True,
        reviewed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    core.start_problem(root, PAIR)
    before_cards = {key: value.to_dict() for key, value in core.rebuild_cards(root).items()}
    before_files = {
        p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    before_events = core.load_events(root)
    service = StudyService(root)
    assert core.load_events(root) == before_events
    assert {key: value.to_dict() for key, value in core.rebuild_cards(root).items()} == before_cards
    assert service.state()["session"]["schema_version"] == 7
    assert all((root / path).read_bytes() == content for path, content in before_files.items())
    assert not service.store.directory.is_relative_to(root)
    backup = service.store.backup()
    assert backup.is_file()


@pytest.mark.skipif(os.name != "nt", reason="Uses a real Windows delete-denying file handle")
def test_locked_legacy_candidate_cannot_break_local_completion(tmp_path, repo_root):
    root = tmp_path / "locked-legacy"
    root.mkdir()
    shutil.copytree(repo_root / "curriculum", root / "curriculum")
    core.start_problem(root, PAIR)
    candidate = root / "attempt/current.py"
    original = candidate.read_bytes()
    service = StudyService(root)
    session = service.start(synchronize=False)["session"]
    create = ctypes.windll.kernel32.CreateFileW
    create.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create.restype = ctypes.c_void_p
    handle = create(str(candidate), 0x80000000, 3, None, 3, 0x80, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    try:
        receipt = service.finish(session["session_id"], "unknown", "", stopped=True)
        assert receipt["status"] == "saved"
        assert service.state()["session"] is None
        assert len(core.load_events(root)) == 1
        assert candidate.read_bytes() == original
    finally:
        ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.CloseHandle(handle)


def test_duplicate_history_id_imports_once_and_conflicts_are_preserved(guided):
    sid = open_attempt(guided)
    guided.finish(sid, "unknown", "", stopped=True)
    event = core.load_events(guided.root)[0]
    text = json.dumps(event)
    guided.store.import_documents({"progress/reviews/copied.json": text}, "other-device")
    assert len(core.load_events(guided.root)) == 1
    event["rating"] = "again"
    report = guided.store.import_documents(
        {"progress/reviews/copied.json": json.dumps(event)}, "other-device"
    )
    assert len(report["conflicts"]) == 1
    assert core.load_events(guided.root)[0]["rating"] == "unknown"
    assert guided.state()["recovery"]
    key = guided.store.paths(".study-local/conflicts/", ".json")[0]
    incoming = guided.store.read_json(key)["incoming"]
    assert hashlib.sha256(incoming.encode()).hexdigest()
    assert StudyStore(guided.root).read_json(key)["status"] == "unresolved"
