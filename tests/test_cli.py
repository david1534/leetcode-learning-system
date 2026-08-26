from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from study.cli import main, public_content_errors, rating_recommendation, reminder_text
from study.core import problem_by_id, record_review


def test_start_hint_and_test_lifecycle(monkeypatch, tmp_path, capsys):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "solutions").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(root)
    assert main(["start", "arrays-001-pair-sum"]) == 0
    assert (root / "attempt" / "session.json").exists()
    assert main(["hint"]) == 0
    assert "Hint 1/3" in capsys.readouterr().out
    assert main(["test"]) == 1


def test_practice_starts_next_problem_then_resumes(monkeypatch, tmp_path, capsys):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "solutions").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(root)

    assert main(["practice", "--no-sync"]) == 0
    assert "Started next roadmap problem" in capsys.readouterr().out
    session = (root / "attempt" / "session.json").read_text(encoding="utf-8")
    assert "arrays-001-pair-sum" in session

    assert main(["practice", "--no-sync"]) == 0
    assert "Resuming" in capsys.readouterr().out


def test_reminder_has_due_review(tmp_path):
    (tmp_path / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (tmp_path / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (tmp_path / "progress" / "reviews").mkdir(parents=True)
    problem = problem_by_id(tmp_path, "arrays-001-pair-sum")
    record_review(
        tmp_path,
        problem,
        "again",
        20,
        False,
        2,
        False,
        reviewed_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    text = reminder_text(tmp_path)
    assert "Practice due" in text
    assert "arrays-001-pair-sum" in text


def test_passing_finish_promotes_solution_and_records_event(monkeypatch, tmp_path):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "solutions").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(root)

    assert main(["start", "arrays-001-pair-sum"]) == 0
    (root / "attempt" / "current.py").write_text(
        "def pair_sum_indices(nums, target):\n"
        "    seen = {}\n"
        "    for index, value in enumerate(nums):\n"
        "        complement = target - value\n"
        "        if complement in seen:\n"
        "            return [seen[complement], index]\n"
        "        seen[value] = index\n"
    )
    assert main(["finish", "--rating", "good", "--minutes", "20", "--explained"]) == 0
    assert (root / "solutions" / "arrays-001-pair-sum.py").exists()
    assert len(list((root / "progress" / "reviews").glob("*.json"))) == 1
    assert not (root / "attempt" / "session.json").exists()


def test_rating_recommendation_uses_observable_session_data():
    problem = {"estimated_minutes": 20}
    session = {
        "hints_used": 0,
        "checkpoint_count": 1,
        "accumulated_seconds": 10 * 60,
        "active_started_at": None,
    }
    assert rating_recommendation(problem, session, 4, 4)[0] == "easy"
    session["hints_used"] = 1
    assert rating_recommendation(problem, session, 4, 4)[0] == "good"
    session["hints_used"] = 2
    assert rating_recommendation(problem, session, 4, 4)[0] == "hard"
    assert rating_recommendation(problem, session, 3, 4)[0] == "again"


def test_public_reflection_scan_rejects_secrets_and_local_paths():
    assert public_content_errors("password=secret")
    assert public_content_errors(r"C:\Users\someone\notes")
    assert public_content_errors("A safe algorithm reflection") == []
