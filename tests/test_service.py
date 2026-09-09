import json
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from study import core, policy
from study.app import create_app
from study.service import Conflict, StudyService
from study.storage import atomic_json

ROOT = Path(__file__).parents[1]
PAIR = "arrays-001-pair-sum"
REFERENCE = json.loads((ROOT / "curriculum/validation.json").read_text(encoding="utf-8"))


@pytest.fixture
def service(tmp_path):
    shutil.copytree(ROOT / "curriculum", tmp_path / "curriculum")
    return StudyService(tmp_path)


def prepared(service, problem=PAIR, activity="implement"):
    service.start(problem, activity, synchronize=False, include_new=True)
    service.reasoning("Map prior values to indices; check the complement before insertion.")
    state = service.state()["session"]
    return service.save_code(REFERENCE[problem]["reference"], state["revision"])["session"]


def finish(service, **changes):
    data = dict(
        session_id=service.state()["session"]["session_id"],
        rating="good",
        takeaway="Check before insertion to avoid using an element twice.",
        explained=True,
        constraints_met=True,
    )
    return service.finish(**{**data, **changes})


def test_same_service_browser_and_coach_revisions(service):
    s = prepared(service)
    coach = StudyService(service.root)
    coach.save_code(s["code"] + "\n# coach edit\n", s["revision"])
    with pytest.raises(Conflict):
        service.save_code(s["code"] + "\n# browser edit\n", s["revision"])
    assert "coach edit" in service.state()["session"]["code"]
    # Direct file edits also invalidate the previously observed session revision.
    s = service.state()["session"]
    (service.root / "attempt/current.py").write_text("# external editor", encoding="utf-8")
    with pytest.raises(Conflict):
        coach.save_code("overwritten", s["revision"])


def test_checked_revision_cannot_authorize_later_code(service):
    prepared(service)
    assert service.check()["all_passed"]
    s = service.state()["session"]
    service.save_code("def pair_sum_indices(nums, target): return []", s["revision"])
    with pytest.raises(RuntimeError, match="current passing check"):
        finish(service)
    receipt = finish(service, stopped=True)
    assert (service.root / "progress/attempts" / receipt["session_id"] / "candidate.py").exists()
    assert not (service.root / "solutions" / f"{PAIR}.py").exists()


@pytest.mark.parametrize("minutes", [None, 12.5])
def test_completion_and_idempotent_restart_recovery(service, minutes):
    prepared(service)
    service.check()
    session = core.load_session(service.root)
    receipt = finish(service, minutes=minutes)
    # Simulate power loss after receipt, before removing the active directory.
    core.save_session(service.root, session)
    restarted = StudyService(service.root)
    assert restarted.state()["session"] is None
    retry = restarted.finish(session["session_id"], "good", "same", minutes=minutes)
    assert retry["event_id"] == receipt["event_id"]
    assert len(core.load_events(service.root)) == 1
    event = core.load_events(service.root)[0]
    assert event["scheduler"]["version"] == "6.3.2"
    if minutes:
        assert sum(event["timing"].values()) / 60 == pytest.approx(minutes, abs=0.001)


def test_interruptible_check_keeps_code_and_cannot_publish_stale_pass(service):
    prepared(service)
    s = service.state()["session"]
    loop = "def pair_sum_indices(nums, target):\n    while True: pass\n"
    service.save_code(loop, s["revision"])
    result = {}
    thread = threading.Thread(target=lambda: result.update(service.check()))
    thread.start()
    # Wait for the job to begin, then use the same stop operation as the browser.
    import time

    deadline = time.monotonic() + 4
    while service.state()["check"].get("status") != "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    service.stop_check()
    thread.join(3)
    assert not thread.is_alive()
    assert result["status"] == "stopped"
    assert service.state()["session"]["code"] == loop


def test_minor_hint_does_not_supply_algorithm_or_count_as_failure(service):
    prepared(service)
    service.assistance("minor", "A generic prompt to double-check the public examples.")
    service.check()
    assert service.evaluate()["recall_outcome"] == "success"
    receipt = finish(service, rating="hard")
    assert policy.independent(core.load_events(service.root)[0])
    assert receipt["published"] is False


def test_guided_recall_requires_again_but_preserves_correct_implementation(service):
    prepared(service)
    service.convert_to_practice()
    service.assistance(
        "guided", "Supplied the missing complement lookup reasoning.", supplied_missing_recall=True
    )
    service.check()
    with pytest.raises(RuntimeError, match="Again"):
        finish(service, rating="hard")
    finish(service, rating="again")
    event = core.load_events(service.root)[0]
    assert event["guided_outcome"]["tests_passed"] and not policy.independent(event)


def test_recall_does_not_reschedule_implementation(service):
    prepared(service)
    service.check()
    finish(service)
    before = core.rebuild_cards(service.root)[PAIR].to_dict()
    service.start(PAIR, "recall", synchronize=False)
    service.reasoning("I recall the map invariant.", quality="complete")
    finish(service)
    assert core.rebuild_cards(service.root)[PAIR].to_dict() == before


def test_offline_pause_resume_preserves_active_timer(service, monkeypatch):
    prepared(service)
    service.pause(synchronize=False)
    assert service.state()["session"]["phase_started_at"] is None
    restarted = StudyService(service.root)
    resumed = restarted.start(synchronize=False)["session"]
    assert resumed["phase_started_at"] and resumed["initial_reasoning"]
    assert resumed["code"] == REFERENCE[PAIR]["reference"]


def test_api_shares_state_and_rejects_stale_or_cross_origin_edits(service):
    s = prepared(service)
    client = TestClient(create_app(service.root), base_url="http://127.0.0.1")
    headers = {"X-Study-Request": "1"}
    assert client.get("/api/state").json()["session"]["session_id"] == s["session_id"]
    service.assistance("minor", "Clarified Python syntax.")
    assert (
        client.post(
            "/api/action/save", headers=headers, json={"revision": s["revision"], "code": "lost"}
        ).status_code
        == 409
    )
    assert client.post("/api/action/pause", json={}).status_code == 403
    assert (
        client.post(
            "/api/action/pause", headers={**headers, "Origin": "https://example.org"}, json={}
        ).status_code
        == 403
    )


def evidence(service, problem, when, **changes):
    p = core.problem_by_id(service.root, problem)
    event = dict(
        schema_version=4,
        event_id=f"e{when.timestamp()}",
        problem_id=problem,
        reviewed_at=when.isoformat(),
        topic=p["topic"],
        kind=p["kind"],
        rating="good",
        minutes=20,
        activity="implement",
        recall_outcome="success",
        assistance_level="none",
        tests_passed=True,
        explained=True,
        assessment={"constraints_met": True},
        unseen=False,
    )
    event.update(changes)
    atomic_json(service.root / "progress/reviews" / f"{event['event_id']}.json", event)


def test_spacing_and_prerequisites_are_elapsed_time_rules(service):
    first = datetime(2026, 8, 20, 3, 59, tzinfo=UTC)
    evidence(service, PAIR, first)
    evidence(service, PAIR, first + timedelta(minutes=2))
    assert policy.topic_progress(service.root)[0]["retained_core"] == 0
    evidence(service, PAIR, first + timedelta(days=7))
    assert policy.topic_progress(service.root)[0]["retained_core"] == 1
    dependent = core.problem_by_id(service.root, "two-pointers-001-core")
    assert policy.eligible(service.root, dependent)
    evidence(service, PAIR, first + timedelta(days=8), rating="again", recall_outcome="failure")
    assert not policy.eligible(service.root, dependent)
    assert policy.topic_progress(service.root)[0]["retained_core"] == 0


def test_repeat_transfer_is_practice_even_after_unfinished_exposure(service):
    p = next(p for p in core.load_problems(service.root) if p["kind"] == "transfer")
    for i, prerequisite in enumerate(p["prerequisites"]):
        evidence(service, prerequisite, datetime(2026, 8, 1 + i, tzinfo=UTC))
    service.start(p["id"], "transfer", synchronize=False, include_new=True)
    assert service.state()["session"]["unseen"]
    finish(service, rating="again", stopped=True)
    service.start(p["id"], "transfer", synchronize=False, include_new=True)
    assert service.state()["session"]["activity"] == "implement"
    assert not service.state()["session"]["unseen"]


def test_queue_budget_weekend_and_new_rotation(service):
    monday = datetime(2026, 9, 7, 15, tzinfo=UTC)
    saturday = monday - timedelta(days=2)
    assert policy.queue(service.root, saturday)["main"] is None
    assert policy.queue(service.root, saturday, include_new=True)["main"]
    evidence(service, PAIR, monday - timedelta(days=30))
    evidence(service, PAIR, monday - timedelta(days=25))
    q = policy.queue(service.root, monday)
    assert q["main"]["id"] != PAIR and q["postponed"]
    assert policy.queue(service.root, monday, minutes=5)["activity"] == "recall"


def test_repair_aliases_merge_and_midnight_does_not_clear_delay(service):
    prepared(service)
    when = datetime.now(UTC) - timedelta(minutes=2)
    for skill in ["hashmap-bucket-initialization", "hashmap-bucket-preservation"]:
        core.record_learning_error(
            service.root,
            skill,
            "implementation",
            "execution-slip",
            "minor",
            "Replaced a bucket.",
            "An existing group is present.",
            "Append without overwriting.",
            "Add a third item to an existing group.",
            when,
        )
    gates = core.open_repair_gates(service.root, when + timedelta(minutes=3))
    assert len(gates) == 1 and not gates[0]["eligible"]
    assert core.open_repair_gates(service.root, when + timedelta(hours=24))[0]["eligible"]
    unrelated = core.problem_by_id(service.root, PAIR)
    assert not policy.relevant_gates(service.root, unrelated)


@pytest.mark.parametrize("entered", ["", "12.5"])
def test_guided_terminal_completion_handles_calculated_or_entered_minutes(
    service, monkeypatch, entered
):
    from study.cli import main

    prepared(service)
    (service.root / "pyproject.toml").write_text('[project]\nname="terminal-test"\n')
    monkeypatch.chdir(service.root)
    answers = iter(["", entered, "Keep the prior-value invariant.", "y", "y", "LOCAL"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert main(["complete"]) == 0
    assert len(core.load_events(service.root)) == 1
    assert service.state()["session"] is None


def test_guided_terminal_cancellation_preserves_candidate(service, monkeypatch):
    from study.cli import main

    s = prepared(service)
    (service.root / "pyproject.toml").write_text('[project]\nname="terminal-test"\n')
    monkeypatch.chdir(service.root)
    answers = iter(["", "", "Keep the invariant.", "y", "y", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert main(["complete"]) == 1
    assert service.state()["session"]["code"] == s["code"]
    assert not core.load_events(service.root)


def test_fifth_main_session_prefers_unseen_transfer(service):
    when = datetime(2026, 8, 1, tzinfo=UTC)
    for i, pid in enumerate([PAIR, "arrays-002-anagram-groups", PAIR, "arrays-002-anagram-groups"]):
        evidence(service, pid, when + timedelta(days=i))
    choice = policy.queue(service.root, datetime(2026, 9, 7, 15, tzinfo=UTC))
    assert choice["activity"] == "transfer"
    assert choice["main"]["id"] not in policy.exposures(service.root)


def test_generic_formal_hint_keeps_independent_recall(service):
    service.start("diagnostic-001-frequency", synchronize=False, include_new=True)
    service.reasoning("Count frequencies, then scan first appearances to resolve ties.")
    service.convert_to_practice()
    assert service.hint()["level"] == "minor"
    assert service.state()["session"]["hints_used"] == 1
    assert service.evaluate()["recall_outcome"] == "success"
