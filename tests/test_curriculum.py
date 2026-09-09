"""Every published contract must accept its reference and reject its counterexamples."""

import json
from pathlib import Path

import pytest

from study.core import load_problems, run_solution

ROOT = Path(__file__).parents[1]
CATALOG = load_problems(ROOT)
VALIDATION = json.loads((ROOT / "curriculum/validation.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("problem", CATALOG, ids=lambda p: p["id"])
def test_exercise_contract(problem, tmp_path):
    record = VALIDATION[problem["id"]]
    candidate = tmp_path / "candidate.py"
    candidate.write_text(record["reference"], encoding="utf-8")
    assert not run_solution(candidate, problem)
    assert record["known_wrong"]
    for wrong in record["known_wrong"]:
        candidate.write_text(wrong, encoding="utf-8")
        assert run_solution(candidate, problem), "Known-wrong implementation escaped detection"
    assert problem["examples"] and problem["rubric"] and problem["skill_ids"]
    assert len(problem["hints"]) == len(problem["hint_levels"])
    assert set(problem["prerequisites"]) <= {p["id"] for p in CATALOG}
    assert problem["content_version"] >= 2


def test_frequency_hint_honors_first_appearance_ties(tmp_path):
    problem = next(p for p in CATALOG if p["id"] == "diagnostic-001-frequency")
    assert "first" in problem["hints"][-1].lower()
    namespace = {}
    exec(VALIDATION[problem["id"]]["reference"], namespace)
    assert namespace[problem["function"]]([9, 2, 2, 9]) == 9
    assert namespace[problem["function"]]([2, 9, 9, 2]) == 2


def test_foundation_has_complete_topic_packages():
    for topic in ["two-pointers", "stack", "binary-search"]:
        kinds = [p["kind"] for p in CATALOG if p["topic"] == topic]
        assert kinds.count("worked") == 1
        assert kinds.count("faded") == 1
        assert kinds.count("core") == 3
        assert kinds.count("transfer") == 2
