from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from study.core import (
    MAX_ACTIVE_SEGMENT_SECONDS,
    active_seconds,
    due_problems,
    effective_events,
    focus_boundary_reached,
    learning_insights,
    load_problems,
    next_new_problem,
    open_repair_gates,
    pause_timer,
    problem_by_id,
    rebuild_cards,
    record_assistance,
    record_initial_reasoning,
    record_learning_error,
    record_repair,
    record_review,
    render_template,
    resume_timer,
    run_solution,
    save_session,
)


def seed_repo(tmp_path):
    (tmp_path / "curriculum").mkdir()
    (tmp_path / "progress" / "reviews").mkdir(parents=True)
    catalog = {
        "problems": [
            {
                "id": "one",
                "title": "One",
                "topic": "arrays-hashing",
                "kind": "core",
                "function": "solve",
                "estimated_minutes": 10,
                "cases": [{"args": [[1, 2]], "expected": 3}],
            },
            {
                "id": "two",
                "title": "Two",
                "topic": "arrays-hashing",
                "kind": "core",
                "function": "solve",
                "estimated_minutes": 10,
                "cases": [{"args": [[2, 3]], "expected": 5}],
            },
        ]
    }
    (tmp_path / "curriculum" / "problems.json").write_text(json.dumps(catalog))
    return tmp_path


def test_catalog_contains_diagnostic_and_complete_first_module(repo_root):
    problems = load_problems(repo_root)
    assert sum(problem["kind"] == "diagnostic" for problem in problems) == 5
    arrays = [problem for problem in problems if problem["topic"] == "arrays-hashing"]
    assert sum(problem["kind"] == "core" for problem in arrays) == 7
    assert sum(problem["kind"] == "transfer" for problem in arrays) == 1
    assert all(len(problem["hints"]) == 3 for problem in problems)
    assert all(problem["cases"] for problem in problems)
    assert all(problem["signature"].startswith(problem["function"]) for problem in problems)
    assert all(problem["parameters"] for problem in problems)
    assert all(problem["returns"]["description"] for problem in problems)
    assert all(example["explanation"] for problem in problems for example in problem["examples"])


def test_published_rating_corrections_preserve_history_and_new_reviews(repo_root):
    effective = effective_events(repo_root)
    by_event_id = {event["event_id"]: event for event in effective}
    pair_sum_history = [
        event for event in effective if event["problem_id"] == "arrays-001-pair-sum"
    ]
    anagram = next(
        event for event in effective if event["problem_id"] == "arrays-002-anagram-groups"
    )

    corrected_pair_sum = by_event_id["91305de82f294291b7bd2d2c46cf30af"]
    assert corrected_pair_sum["original_rating"] == "hard"
    assert corrected_pair_sum["rating"] == "again"
    assert pair_sum_history[-1]["rating"] == "good"
    assert "rating_correction" not in pair_sum_history[-1]
    assert anagram["original_rating"] == "hard"
    assert anagram["rating"] == "again"


def test_pair_sum_template_has_named_readable_example(repo_root):
    problem = problem_by_id(repo_root, "arrays-001-pair-sum")
    rendered = render_template(problem)
    assert "def pair_sum_indices(nums: list[int], target: int) -> list[int]:" in rendered
    assert "nums = [7, 2, 11, 5]" in rendered
    assert "target = 7" in rendered
    assert "nums[1] + nums[3] equals 2 + 5 = 7" in rendered
    compile(rendered, "attempt/current.py", "exec")


def test_every_problem_template_is_valid_python(repo_root):
    for problem in load_problems(repo_root):
        rendered = render_template(problem)
        compile(rendered, f"{problem['id']}.py", "exec")
        assert max(map(len, rendered.splitlines())) <= 100


def test_runner_reports_passes_and_failures(tmp_path, repo_root):
    problem = problem_by_id(repo_root, "arrays-001-pair-sum")
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "def pair_sum_indices(nums, target):\n"
        "    seen = {}\n"
        "    for i, value in enumerate(nums):\n"
        "        if target - value in seen:\n"
        "            return [seen[target - value], i]\n"
        "        seen[value] = i\n"
    )
    assert run_solution(candidate, problem) == []
    candidate.write_text("def pair_sum_indices(nums, target):\n    return [0, 1]\n")
    assert run_solution(candidate, problem)


def test_review_events_rebuild_deterministic_fsrs_card(tmp_path):
    root = seed_repo(tmp_path)
    problem = problem_by_id(root, "one")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    record_review(root, problem, "good", 20, True, 0, True, reviewed_at=now)
    first = rebuild_cards(root)["one"]
    second = rebuild_cards(root)["one"]
    assert first.to_dict() == second.to_dict()
    assert first.due > now
    assert due_problems(root, now=now) == []
    assert [item["id"] for item in due_problems(root, now=now + timedelta(days=400))] == ["one"]


def test_new_problem_selection_skips_reviewed_items(tmp_path):
    root = seed_repo(tmp_path)
    first = next_new_problem(root)
    assert first["id"] == "one"
    record_review(
        root,
        first,
        "again",
        10,
        False,
        2,
        False,
        reviewed_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )
    assert next_new_problem(root)["id"] == "two"


def test_event_files_are_immutable_and_unique(tmp_path):
    root = seed_repo(tmp_path)
    problem = problem_by_id(root, "one")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    first = record_review(root, problem, "good", 20, True, 0, True, reviewed_at=now)
    second = record_review(root, problem, "easy", 15, True, 0, True, reviewed_at=now)
    assert first != second
    assert len(list((root / "progress" / "reviews").glob("*.json"))) == 2


def test_review_correction_replaces_rating_without_adding_attempt(tmp_path):
    root = seed_repo(tmp_path)
    problem = problem_by_id(root, "one")
    review = record_review(
        root,
        problem,
        "hard",
        20,
        True,
        0,
        True,
        assistance_level="substantial",
        assistance_count=4,
        reviewed_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )
    event = json.loads(review.read_text())
    corrections = root / "progress" / "corrections"
    corrections.mkdir()
    correction = {
        "schema_version": 1,
        "correction_id": "test-correction",
        "target_event_id": event["event_id"],
        "problem_id": "one",
        "corrected_rating": "again",
        "corrected_at": "2026-08-27T00:00:00+00:00",
        "reason": "Substantial help supplied the approach.",
    }
    (corrections / "correction.json").write_text(json.dumps(correction))

    events = effective_events(root)

    assert len(events) == 1
    assert events[0]["original_rating"] == "hard"
    assert events[0]["rating"] == "again"
    assert len(rebuild_cards(root)) == 1


def test_learning_evidence_survives_modern_session_upgrade(tmp_path):
    root = seed_repo(tmp_path)
    (root / "attempt").mkdir()
    session = {
        "schema_version": 3,
        "problem_id": "one",
        "started_at": "2026-08-26T12:00:00+00:00",
        "active_started_at": None,
        "accumulated_seconds": 0,
        "hints_used": 0,
        "checkpoint_count": 0,
    }
    save_session(root, session)
    record_initial_reasoning(root, "Use two pointers.", "Pointers converge.", "O(n)")
    record_assistance(root, "substantial", "Changed to a frequency map.")

    saved = json.loads((root / "attempt" / "session.json").read_text())
    assert saved["schema_version"] == 5
    assert saved["initial_reasoning"]["approach"] == "Use two pointers."
    assert saved["assistance_log"][0]["level"] == "substantial"


def test_pause_and_resume_preserve_all_current_and_future_session_evidence(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    (root / "attempt").mkdir()
    session = {
        "schema_version": 5,
        "problem_id": "one",
        "attempt_kind": "review",
        "started_at": started.isoformat(),
        "active_started_at": started.isoformat(),
        "accumulated_seconds": 0,
        "hints_used": 1,
        "checkpoint_count": 1,
        "checkpoint_count_at_last_hint": 1,
        "first_checkpoint_passed": True,
        "latest_checkpoint": {
            "attempt": 1,
            "checked_at": started.isoformat(),
            "passed_cases": 1,
            "total_cases": 1,
        },
        "initial_reasoning": {"quality": "complete"},
        "future_evidence_field": {"preserve": True},
    }
    save_session(root, session)

    paused = pause_timer(root, started + timedelta(minutes=10))
    resumed = resume_timer(root, started + timedelta(minutes=11))

    for saved in (paused, resumed):
        assert saved["attempt_kind"] == "review"
        assert saved["first_checkpoint_passed"] is True
        assert saved["checkpoint_count_at_last_hint"] == 1
        assert saved["latest_checkpoint"]["passed_cases"] == 1
        assert saved["future_evidence_field"] == {"preserve": True}


def test_reasoning_records_retrieval_fields_and_focus_boundary(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    (root / "attempt").mkdir()
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "one",
            "started_at": started.isoformat(),
            "active_started_at": started.isoformat(),
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    record_initial_reasoning(
        root,
        "Use a set.",
        "Each item is processed once.",
        "O(n)",
        why="Membership checks match the constraint.",
        edge_case="Empty input.",
        quality="complete",
        recorded_at=started,
    )
    session = json.loads((root / "attempt" / "session.json").read_text())
    assert session["initial_reasoning"]["quality"] == "complete"
    assert not focus_boundary_reached(session, started + timedelta(minutes=44))
    assert focus_boundary_reached(session, started + timedelta(minutes=45))


def test_blocking_and_recurring_errors_create_delayed_repair_gates(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    (root / "attempt").mkdir()
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "one",
            "started_at": started.isoformat(),
            "active_started_at": started.isoformat(),
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    blocking = record_learning_error(
        root,
        "hash lookup",
        "pattern-selection",
        "misconception",
        "blocking",
        "Selected sorting despite needing original indices.",
        "Original indices plus constant-time lookup.",
        "Store prior values and indices.",
        "Explain and apply complement lookup to a novel list.",
        recorded_at=started,
    )
    target = json.loads(blocking.read_text())
    gates = open_repair_gates(root, started + timedelta(hours=1))
    assert len(gates) == 1 and not gates[0]["eligible"]
    assert open_repair_gates(root, started + timedelta(days=1))[0]["eligible"]

    record_repair(
        root,
        target["event_id"],
        "Need original indices.",
        "Use a prior-value map.",
        "Sorting lost positions.",
        "Applied it to a new complement example.",
        True,
        recorded_at=started + timedelta(days=1),
    )
    assert open_repair_gates(root, started + timedelta(days=2)) == []
    assert learning_insights(root)["cleared_repairs"] == 1


def test_recurring_minor_error_creates_gate_and_early_repair_is_rejected(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    (root / "attempt").mkdir()
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "one",
            "started_at": started.isoformat(),
            "active_started_at": started.isoformat(),
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    paths = []
    for offset in range(2):
        paths.append(
            record_learning_error(
                root,
                "edge handling",
                "edge-case",
                "omission",
                "minor",
                "Missed the empty input case.",
                "Check the smallest legal input.",
                "Handle empty input before scanning.",
                "Apply the boundary rule to a new input shape.",
                recorded_at=started + timedelta(hours=offset),
            )
        )
    target = json.loads(paths[-1].read_text())
    gates = open_repair_gates(root, started + timedelta(hours=2))
    assert [gate["event_id"] for gate in gates] == [target["event_id"]]
    try:
        record_repair(
            root,
            target["event_id"],
            "Smallest input.",
            "Handle empty input first.",
            "I omitted the boundary.",
            "Applied it to an empty matrix.",
            True,
            recorded_at=started + timedelta(hours=2),
        )
    except RuntimeError as exc:
        assert "next Eastern day" in str(exc)
    else:
        raise AssertionError("An early repair should be rejected.")


def test_substantial_help_automatically_creates_repair_gate(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    (root / "attempt").mkdir()
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "one",
            "started_at": started.isoformat(),
            "active_started_at": started.isoformat(),
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    record_assistance(root, "substantial", "Supplied the core representation.", recorded_at=started)
    gates = open_repair_gates(root, started + timedelta(days=1))
    assert len(gates) == 1
    assert gates[0]["source"] == "substantial-help"


def test_successful_repair_resets_recurring_minor_history(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 25, 12, tzinfo=UTC)
    (root / "attempt").mkdir()
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "one",
            "started_at": started.isoformat(),
            "active_started_at": started.isoformat(),
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    latest = None
    for offset in range(2):
        latest = record_learning_error(
            root,
            "edge handling",
            "edge-case",
            "omission",
            "minor",
            "Missed a boundary.",
            "Inspect the smallest input.",
            "Handle the boundary before scanning.",
            "Apply this rule to a fresh container shape.",
            recorded_at=started + timedelta(hours=offset),
        )
    assert latest is not None
    error = json.loads(latest.read_text())
    record_repair(
        root,
        error["event_id"],
        "Smallest legal input.",
        "Handle boundaries first.",
        "I skipped the boundary.",
        "Applied the rule to an empty grid.",
        True,
        recorded_at=started + timedelta(days=1),
    )
    record_learning_error(
        root,
        "edge handling",
        "edge-case",
        "omission",
        "minor",
        "Missed a different boundary.",
        "Inspect the largest input.",
        "Check both ends before scanning.",
        "Apply the rule to a single-row grid.",
        recorded_at=started + timedelta(days=2),
    )
    assert open_repair_gates(root, started + timedelta(days=3)) == []


def test_public_learning_events_reject_sensitive_text(tmp_path):
    root = seed_repo(tmp_path)
    (root / "attempt").mkdir()
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "one",
            "started_at": "2026-08-26T12:00:00+00:00",
            "active_started_at": None,
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    try:
        record_learning_error(
            root,
            "debugging",
            "debugging",
            "execution-slip",
            "minor",
            "Opened C:\\Users\\someone\\secret.txt",
            "Inspect paths.",
            "Use repository-relative paths.",
            "Explain safe path handling.",
        )
    except RuntimeError as exc:
        assert "public-content risks" in str(exc)
    else:
        raise AssertionError("Sensitive learning evidence should be rejected.")


def test_all_seeded_case_shapes_are_json_round_trippable(repo_root):
    for problem in load_problems(repo_root):
        assert json.loads(json.dumps(problem["cases"])) == problem["cases"]


def test_active_timer_caps_long_unpaused_segment(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    session = {
        "schema_version": 3,
        "problem_id": "one",
        "started_at": started.isoformat(),
        "active_started_at": started.isoformat(),
        "accumulated_seconds": 120,
        "hints_used": 0,
        "checkpoint_count": 0,
    }
    save_session(root, session)
    later = started + timedelta(hours=5)
    assert active_seconds(session, later) == MAX_ACTIVE_SEGMENT_SECONDS + 120


def test_save_session_migrates_legacy_checkpoint_history(tmp_path):
    root = tmp_path
    checkpoints = root / "attempt" / "checkpoints"
    checkpoints.mkdir(parents=True)
    legacy = {
        "schema_version": 1,
        "problem_id": "one",
        "attempt": 2,
        "checked_at": "2026-08-26T12:00:00+00:00",
        "passed_cases": 3,
        "total_cases": 4,
    }
    (checkpoints / "002.json").write_text(json.dumps(legacy), encoding="utf-8")
    session = {
        "schema_version": 2,
        "problem_id": "one",
        "started_at": "2026-08-26T12:00:00+00:00",
        "active_started_at": None,
        "accumulated_seconds": 60,
        "hints_used": 0,
        "checkpoint_count": 2,
    }

    save_session(root, session)

    saved = json.loads((root / "attempt" / "session.json").read_text(encoding="utf-8"))
    assert saved["latest_checkpoint"] == {
        "attempt": 2,
        "checked_at": "2026-08-26T12:00:00+00:00",
        "passed_cases": 3,
        "total_cases": 4,
    }
    assert not checkpoints.exists()
