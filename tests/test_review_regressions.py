"""Regression cases found by the application review; all state is disposable."""

import io
import json
import queue
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_guided import repair_setup

from study.coach import attempted_again
from study.codex_runtime import CodexRuntime
from study.gitflow import GitFlowError
from study.service import Conflict, StudyService


@pytest.mark.parametrize("code", ["def example(): return 1", "def example(): return 2"])
def test_original_and_proposed_code_are_not_a_learner_retry(code):
    prior = {
        "context": {"code": "def example(): return 1", "retries": []},
        "proposed_code": "def example(): return 2",
    }
    assert not attempted_again({"code": code, "retries": []}, prior)
    assert attempted_again({"code": "def example(): return 3", "retries": []}, prior)
    assert attempted_again({"code": code, "retries": [{"answer": "A fresh trace."}]}, prior)


@pytest.mark.parametrize("was_paused", [False, True])
def test_restarted_repair_check_can_run_again_without_losing_the_answer(guided, was_paused):
    repair_setup(guided)
    answer = "values = [1, 2]\nvalues.append(3)\nassert values == [1, 2, 3]"
    guided.repair_draft(answer)
    timer = guided._read_local("repair-timer")
    original_id = timer["session_id"]
    timer["check"] = {"status": "running", "code_digest": timer["code_digest"]}
    if was_paused:
        timer["started_at"] = None
    guided._write_local("repair-timer", timer)
    restarted = StudyService(guided.root)
    restarted.recover_timing()
    restored = restarted._read_local("repair-timer")
    assert restored["session_id"] == original_id
    assert restored["application"] == answer
    assert restored["check"]["status"] == "interrupted"
    assert restored["check"]["all_passed"] is False
    result = restarted.check_repair()
    assert result["status"] == "complete" and result["all_passed"]


def test_repair_result_survives_generated_file_cleanup_error(guided, monkeypatch):
    repair_setup(guided)
    guided.repair_draft("assert 2 + 2 == 4")
    original = Path.unlink

    def fail_cleanup(path, *args, **kwargs):
        if path.name.startswith("repair-check-"):
            raise PermissionError("Simulated temporary file lock")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_cleanup)
        result = guided.check_repair()
    assert result["status"] == "complete" and result["all_passed"]
    assert guided._read_local("repair-timer")["check"] == result


def publication(guided, status="pending"):
    job = {
        "id": "reviewjob",
        "kind": "publish",
        "status": status,
        "session_ids": ["fixture"],
        "problem_id": "fixture",
        "artifacts": {},
    }
    guided._write_local("outbox/reviewjob", job)
    return job


def test_failed_preparation_does_not_resurrect_deferred_publication(guided, monkeypatch):
    publication(guided)
    sync = guided.synchronizer

    def fail_after_deferral():
        guided.keep_local()
        raise GitFlowError("Simulated disconnected remote")

    monkeypatch.setattr(sync, "prepare", fail_after_deferral)
    sync.run_jobs()
    assert guided._read_local("outbox/reviewjob")["status"] == "deferred"
    assert guided._read_local("sync")["status"] == "local"
    calls = []
    monkeypatch.setattr(sync, "prepare", lambda: calls.append("prepare"))
    monkeypatch.setattr(sync, "_push", lambda job: calls.append("push"))
    sync.run_jobs()
    assert not calls


def test_keep_local_does_not_claim_an_inflight_publication_was_canceled(guided):
    publication(guided, "running")
    with pytest.raises(Conflict, match="already sending"):
        guided.keep_local()
    assert guided._read_local("outbox/reviewjob")["status"] == "running"


@pytest.mark.parametrize(
    "lines", [[], [json.dumps({"method": "account/rateLimits/updated", "params": {}})]]
)
def test_retired_reader_cannot_disconnect_or_notify_the_new_runtime(tmp_path, lines):
    runtime = CodexRuntime(tmp_path)
    old = SimpleNamespace(stdout=iter(lines))
    current = SimpleNamespace(poll=lambda: None)
    runtime.process = current
    pending = queue.Queue(maxsize=1)
    runtime.pending[42] = pending
    events = []
    runtime.on_event = lambda method, params: events.append(method)
    runtime.closed.clear()
    runtime._read(old)
    assert runtime.process is current
    assert not runtime.closed.is_set()
    assert pending.empty()
    assert not events


def test_close_releases_pending_calls_even_when_reader_teardown_is_delayed(tmp_path):
    runtime = CodexRuntime(tmp_path)
    process = SimpleNamespace(poll=lambda: 0, stdin=io.StringIO(), stdout=io.StringIO())
    runtime.process = process
    pending = queue.Queue(maxsize=1)
    runtime.pending[42] = pending
    runtime.close()
    assert "disconnected" in pending.get_nowait()["error"]["message"]
    assert runtime.process is None and runtime.closed.is_set()
    assert process.stdin.closed and process.stdout.closed
