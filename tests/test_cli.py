from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from study.cli import main, reminder_text
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
    assert (root / ".practice" / "session.json").exists()
    assert main(["hint"]) == 0
    assert "Hint 1/3" in capsys.readouterr().out
    assert main(["test"]) == 1


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
    (root / ".practice" / "current.py").write_text(
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
    assert not (root / ".practice" / "session.json").exists()
