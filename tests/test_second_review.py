"""Regression coverage for the second whole-application review."""

import json

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from test_guided import repair_setup

from study.app import create_app
from study.runner import execute
from study.service import Conflict


def test_relative_candidate_files_stay_inside_the_disposable_runner(tmp_path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "from pathlib import Path\n"
        'Path("worker-relative.txt").write_text("scratch")\n'
        "def example(): return True\n"
    )
    assert (
        execute(candidate, {"function": "example", "cases": [{"args": [], "expected": True}]}) == []
    )
    assert not (tmp_path / "worker-relative.txt").exists()


@pytest.mark.parametrize("repair", [False, True])
def test_duplicate_check_cannot_replace_the_running_job(guided, monkeypatch, repair):
    if repair:
        repair_setup(guided)
        guided.repair_draft("assert True")
    else:
        guided.practice_start(include_new=True, synchronize=False)
        guided.reasoning("Try each pair and check the sum.")
    app = create_app(guided.root)
    scheduled = []
    monkeypatch.setattr(
        BackgroundTasks, "add_task", lambda _, fn, *a, **k: scheduled.append((fn, a, k))
    )
    client = TestClient(app, base_url="http://127.0.0.1")
    path = "/api/practice/repair-check" if repair else "/api/action/check"
    data = {"answer": "assert True"} if repair else {}
    first = client.post(path, json=data, headers={"x-study-request": "1"})
    assert first.status_code == 200
    state = guided.state()
    check = state["repair"]["check"] if repair else state["check"]
    assert check["status"] == "running"
    second = client.post(path, json=data, headers={"x-study-request": "1"})
    assert second.status_code == 409
    state = guided.state()
    assert (state["repair"]["check"] if repair else state["check"]) == check
    assert len(scheduled) == 1
    fn, args, kwargs = scheduled[0]
    fn(*args, **kwargs)
    state = guided.state()
    assert (state["repair"]["check"] if repair else state["check"])["status"] == "complete"


def test_repair_infrastructure_failure_is_retryable_and_keeps_the_answer(guided, monkeypatch):
    repair_setup(guided)
    guided.repair_draft("assert True")
    original = execute

    def broken(*args, **kwargs):
        raise OSError("private fixture infrastructure detail")

    monkeypatch.setattr("study.runner.execute", broken)
    result = guided.check_repair()
    assert result["status"] == "error"
    assert "try again" in result["message"]
    assert "private fixture" not in json.dumps(guided.state())
    assert guided.state()["repair"]["application"] == "assert True"
    monkeypatch.setattr("study.runner.execute", original)
    assert guided.check_repair()["all_passed"]


def test_fresh_practice_keeps_remote_drafts_and_rejects_replacing_local_work(guided):
    branches = ["attempt/first", "attempt/second"]
    guided._write_local("remote-attempts", branches)
    assert guided.practice_start(include_new=True, synchronize=False)["session"] is None
    state = guided.practice_start(include_new=True, synchronize=False, fresh=True)
    assert state["session"] and state["remote_attempts"] == branches
    candidate = state["session"]["code"]
    with pytest.raises(Conflict, match="Finish|finish"):
        guided.practice_start(include_new=True, synchronize=False, fresh=True)
    assert guided.state()["session"]["code"] == candidate


def test_evaluation_rejects_a_different_session(guided):
    first = guided.practice_start(include_new=True, synchronize=False)["session"]
    guided.finish(first["session_id"], "unknown", "", stopped=True)
    second = guided.practice_start(include_new=True, synchronize=False)["session"]
    with pytest.raises(Conflict):
        guided.evaluate(session_id=first["session_id"])
    assert guided.state()["session"]["session_id"] == second["session_id"]


@pytest.mark.parametrize("repair", [False, True])
def test_retired_check_result_cannot_overwrite_the_current_check(guided, monkeypatch, repair):
    scheduled = []

    def schedule(fn, *args):
        scheduled.append((fn, args))

    if repair:
        repair_setup(guided)
        guided.repair_draft("assert True")
        old = guided.check_repair(schedule=schedule)
        timer = guided._read_local("repair-timer")
        timer["check"]["status"] = "interrupted"
        guided._write_local("repair-timer", timer)
        current = guided.check_repair(schedule=schedule)
    else:
        guided.practice_start(include_new=True, synchronize=False)
        guided.reasoning("Try each pair and check its sum.")
        monkeypatch.setattr("study.core.run_solution", lambda *args: [])
        old = guided.check(schedule=schedule)
        guided._write_local("check", {**old, "status": "interrupted"})
        current = guided.check(schedule=schedule)
    assert old["id"] != current["id"]
    fn, args = scheduled[0]
    assert fn(*args)["status"] == "stale"
    state = guided.state()
    assert (state["repair"]["check"] if repair else state["check"]) == current
    fn, args = scheduled[1]
    assert fn(*args)["status"] == "complete"


def test_cli_fresh_start_uses_the_shared_startup_flow(guided, monkeypatch, capsys):
    from study.cli import main

    guided._write_local("remote-attempts", ["attempt/older-one", "attempt/older-two"])
    monkeypatch.chdir(guided.root)
    assert main(["practice", "--no-sync", "--include-new"]) == 0
    assert "study choose-attempt attempt/older-one" in capsys.readouterr().out
    assert main(["practice", "--fresh", "--no-sync", "--include-new"]) == 0
    assert guided.state()["session"]
    assert len(guided.state()["remote_attempts"]) == 2


def test_delayed_completion_stop_cannot_interrupt_the_next_sessions_coach(guided, monkeypatch):
    from test_coach import factory

    first = guided.practice_start(include_new=True, synchronize=False)["session"]
    app = create_app(guided.root, coach_factory=factory)
    first = app.state.service.state()["session"]
    scheduled = []
    monkeypatch.setattr(
        BackgroundTasks, "add_task", lambda _, fn, *a, **k: scheduled.append((fn, a, k))
    )
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/practice/finish",
        json={
            "session_id": first["session_id"],
            "revision": first["revision"],
            "rating": "unknown",
            "stopped": True,
        },
        headers={"x-study-request": "1"},
    )
    assert response.status_code == 200
    second = app.state.service.practice_start(include_new=True, synchronize=False)["session"]
    coach = app.state.coach
    coach.active = "next-question"
    coach._save(
        "requests/next-question",
        {"session_id": second["session_id"], "thread_id": "next-thread", "turn_id": "next-turn"},
    )
    calls = []
    monkeypatch.setattr(coach.runtime, "call", lambda method, params: calls.append(method))
    fn, args, kwargs = scheduled[0]
    fn(*args, **kwargs)
    assert "next-question" not in coach.cancelled
    assert not calls
