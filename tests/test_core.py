from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from study.core import (
    MAX_ACTIVE_SEGMENT_SECONDS,
    active_seconds,
    due_problems,
    load_problems,
    next_new_problem,
    problem_by_id,
    rebuild_cards,
    record_review,
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


def test_all_seeded_case_shapes_are_json_round_trippable(repo_root):
    for problem in load_problems(repo_root):
        assert json.loads(json.dumps(problem["cases"])) == problem["cases"]


def test_active_timer_caps_long_unpaused_segment(tmp_path):
    root = seed_repo(tmp_path)
    started = datetime(2026, 8, 26, 12, tzinfo=UTC)
    session = {
        "schema_version": 2,
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
