import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from study import core, policy
from study.service import StudyService


def test_parent_session_and_conversion_preserve_original_assessment(guided):
    state = guided.practice_start(minutes=60, include_new=True, synchronize=False)
    sid = state["session"]["session_id"]
    guided.reasoning("I don't know the approach yet.", "failed")
    before = (guided.root / "attempt/current.py").read_text()
    with pytest.raises(RuntimeError, match="Switch"):
        guided.hint()
    guided.convert_to_practice()
    guided.hint()
    with pytest.raises(RuntimeError, match="Retry"):
        guided.hint(retried=True)
    guided.record_retry("I traced two values and kept the earlier index separately.")
    guided.hint()
    receipt = guided.practice_finish(sid, "again", "Check the earlier values first.", stopped=True)
    events = core.load_events(guided.root)
    assert len(events) == 1
    assert events[0]["assessment"]["status"] == "ended_for_help"
    assert events[0]["activity"] == "implement"
    assert not policy.independent(events[0])
    assert (guided.root / "progress/attempts" / sid / "assessment.py").read_text() == before
    assert len(policy.practice_sessions(guided.root)) == 1
    assert guided.practice_finish(sid, "again", "retry")["session_id"] == receipt["session_id"]
    assert len(guided._unpublished()) == 1


def test_context_excludes_assessment_cues_and_hidden_cases(guided):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("Try each pair and compare its sum to the target.")
    context = guided.coach_context()
    text = json.dumps(context)
    for prohibited in ("arrays-001", "skill_ids", "hashmap", "reference", "cases", "related_url"):
        assert prohibited not in text
    assert context["code"] and context["mode"] == "assessment"
    session = guided.state()["session"]
    legacy = core.render_template(core.problem_by_id(guided.root, session["problem_id"]))
    guided.save_code(legacy, session["revision"])
    context = guided.coach_context()
    assert "leetcode.com" not in context["code"]
    assert context["code"].startswith("def pair_sum_indices")


def test_outside_repository_fails_without_touching_real_workspace(tmp_path, repo_root):
    with pytest.raises(RuntimeError, match="repository"):
        core.find_root(tmp_path)
    assert core.find_root(repo_root) == repo_root


def test_timer_restart_pauses_and_marks_unknown_gap(guided):
    guided.practice_start(include_new=True, synchronize=False)
    session = core.load_session(guided.root)
    session["phase_started_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    core.save_session(guided.root, session)
    guided.timer_checkpoint()
    state = guided.state()["session"]
    assert state["phase_started_at"] is None
    assert state["timing_uncertain"]
    assert state["elapsed_seconds"] < 10


def test_substantive_help_does_not_automatically_mean_missing_recall(guided):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("I reconstructed my previous approach.", "complete")
    guided.convert_to_practice()
    guided.assistance("guided", "Discussed a different approach after successful recall.")
    assert guided.evaluate()["recommended_rating"] == "good"


def test_supporting_recall_transitions_to_main_without_inflating_sessions(guided, monkeypatch):
    original = guided.plan

    def plan(*args, **kwargs):
        result = original(*args, **kwargs)
        other = next(p for p in core.load_problems(guided.root) if p["id"] != result["main"]["id"])
        result["short_recall"] = [other]
        return result

    monkeypatch.setattr(guided, "plan", plan)
    state = guided.practice_start(include_new=True, synchronize=False)
    assert state["practice"]["stages"][0]["type"] == "recall"
    guided.practice_advance(answer="Use a count for each distinct value.")
    state = guided.state()
    assert state["practice"]["index"] == 1
    assert state["session"]["activity"] == "implement"
    assert policy.metrics(guided.root)["baseline_sessions"] == 0
    guided.reasoning("I don't know yet.", "failed")
    guided.practice_finish(
        state["session"]["session_id"], "again", "Keep prior state.", stopped=True
    )
    assert len(core.load_events(guided.root)) == 2
    assert policy.metrics(guided.root)["baseline_sessions"] == 1


def test_portable_pause_restores_supporting_work_on_another_computer(guided, monkeypatch, tmp_path):
    plan = guided.plan

    def with_recall(*args, **kwargs):
        value = plan(*args, **kwargs)
        value["short_recall"] = [core.problem_by_id(guided.root, "diagnostic-001-frequency")]
        return value

    monkeypatch.setattr(guided, "plan", with_recall)
    guided.practice_start(include_new=True, synchronize=False)
    guided.practice_advance(answer="Count each distinct value before comparing frequencies.")
    guided.reasoning("I don't know yet.", "failed")
    guided.convert_to_practice()
    guided.practice_pause()
    other = tmp_path / "another-computer"
    other.mkdir()
    for name in ("curriculum", "attempt"):
        shutil.copytree(guided.root / name, other / name)
    shutil.copy2(guided.root / "pyproject.toml", other / "pyproject.toml")
    restored = StudyService(other)
    state = restored.practice_start(synchronize=False)
    assert len(core.load_events(other)) == 1
    assert state["practice"]["index"] == 1
    assert state["session"]["assessment_before_help"]["status"] == "ended_for_help"
    restored.practice_finish(
        state["session"]["session_id"], "again", "Restore all supporting evidence.", stopped=True
    )
    assert len(core.load_events(other)) == 2
    assert len(policy.practice_sessions(other)) == 1
    assert len(restored._unpublished()) == 1


def repair_setup(service):
    service.start("arrays-001-pair-sum", synchronize=False, include_new=True)
    service.reasoning("Try an initial approach.")
    path = core.record_learning_error(
        service.root,
        "hashmap-bucket-lifecycle",
        "implementation",
        "execution-slip",
        "blocking",
        "Overwrote the earlier values.",
        "An existing key is present.",
        "Append without replacing earlier values.",
        "Append a fresh third value and check all three remain.",
        datetime.now(UTC) - timedelta(days=2),
    )
    error = json.loads(path.read_text())
    service.begin_repair(error["event_id"])
    return error["event_id"]


def test_small_coding_repair_uses_interruptible_runner_and_preserves_draft(guided):
    error = repair_setup(guided)
    code = "items = [4, 5]\nitems.append(6)\nassert items == [4, 5, 6]"
    guided.repair_draft(code)
    assert guided.check_repair()["all_passed"]
    guided.repair(error, code, True)
    assert guided.state()["session"]["phase_started_at"]
    assert not core.open_repair_gates(guided.root)


def test_disputed_constraint_cannot_become_an_independent_pass(guided):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("Reconstruct the map of earlier values.")
    guided.evidence(
        [{"dimension": "constraints", "value": "unknown", "source": "learner_amendment"}]
    )
    sid = guided.state()["session"]["session_id"]
    guided.practice_finish(sid, "good", "Check the complexity claim.", True, True, stopped=True)
    event = core.load_events(guided.root)[0]
    assert event["assessment"]["constraints_met"] is False
    assert not policy.independent(event)


def test_recorded_time_correction_is_counted_once(guided):
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("I don't know yet.", "failed")
    sid = guided.state()["session"]["session_id"]
    guided.practice_finish(sid, "again", "Try a new trace.", minutes=30, stopped=True)
    assert policy.metrics(guided.root)["recorded_total_minutes"] == 30


def test_stopping_before_recall_is_recorded_does_not_invent_a_failure(guided):
    state = guided.practice_start(include_new=True, synchronize=False)
    assert guided.evaluate()["recall_outcome"] == "unknown"
    guided.practice_finish(state["session"]["session_id"], "unknown", "", stopped=True)
    event = core.load_events(guided.root)[0]
    assert event["rating"] == "unknown" and event["recall_outcome"] == "unknown"
    assert core.rebuild_cards(guided.root) == {}
    assert not policy.independent(event)


def test_repair_can_unblock_a_session_when_no_main_is_available(guided, monkeypatch):
    repair_setup(guided)
    session = guided.state()["session"]
    guided.cancel_repair()
    guided.finish(session["session_id"], "good", "Keep earlier values.", stopped=True)
    original = guided.plan

    def blocked_plan(*args, **kwargs):
        result = original(*args, **kwargs)
        if core.open_repair_gates(guided.root):
            result["main"] = None
        return result

    monkeypatch.setattr(guided, "plan", blocked_plan)
    state = guided.practice_start(include_new=True, synchronize=False)
    assert state["practice"]["stages"][0]["type"] == "repair"
    result = guided.practice_advance(
        answer="items=[4,5]; items.append(6); assert items==[4,5,6]", passed=True
    )
    assert result["session"] is not None
    assert result["practice"]["stages"][result["practice"]["index"]]["type"] == "main"
    assert len(policy.practice_sessions(guided.root)) == 0
