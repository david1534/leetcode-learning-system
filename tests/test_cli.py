from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from study.cli import (
    main,
    public_content_errors,
    rating_recommendation,
    rating_too_high,
    reminder_text,
    render_reflection,
)
from study.core import problem_by_id, record_review, render_template


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
    assert main(
        [
            "note",
            "reasoning",
            "--approach",
            "Try a map.",
            "--invariant",
            "Seen contains prior values.",
            "--complexity",
            "O(n)",
        ]
    ) == 0
    assert main(["hint"]) == 0
    assert "Targeted question:" in capsys.readouterr().out
    session = json.loads((root / "attempt" / "session.json").read_text())
    assert session["assistance_log"][0]["level"] == "guided"
    assert session["assistance_log"][0]["source"] == "formal_hint"
    assert main(["hint"]) == 2
    assert "Retry and checkpoint" in capsys.readouterr().out
    assert main(["test"]) == 1


def test_note_records_initial_reasoning_and_conversational_help(monkeypatch, tmp_path, capsys):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(root)

    assert main(["start", "arrays-002-anagram-groups"]) == 0
    assert main(
        [
            "note",
            "reasoning",
            "--approach",
            "Use opposite-direction pointers.",
            "--invariant",
            "The pointers avoid nested loops.",
            "--complexity",
            "O(n)",
        ]
    ) == 0
    assert main(
        [
            "note",
            "assistance",
            "--level",
            "substantial",
            "--summary",
            "Replaced two pointers with a frequency-vector key.",
        ]
    ) == 0
    capsys.readouterr()
    session = json.loads((root / "attempt" / "session.json").read_text())
    assert session["initial_reasoning"]["approach"] == "Use opposite-direction pointers."
    assert session["assistance_log"][0]["level"] == "substantial"


def test_checkpoint_saves_one_local_summary_and_supports_json(monkeypatch, tmp_path, capsys):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "solutions").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(root)

    assert main(["start", "arrays-001-pair-sum"]) == 0
    assert main(
        [
            "note",
            "reasoning",
            "--approach",
            "Try a map.",
            "--invariant",
            "Seen contains prior values.",
            "--complexity",
            "O(n)",
        ]
    ) == 0
    capsys.readouterr()
    assert main(["checkpoint", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    session = json.loads((root / "attempt" / "session.json").read_text(encoding="utf-8"))

    assert result["problem_id"] == "arrays-001-pair-sum"
    assert result["checkpoint_count"] == 1
    assert result["failure_count"] > 0
    assert session["latest_checkpoint"]["total_cases"] == 4
    assert not (root / "attempt" / "checkpoints").exists()


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
    assert main(
        [
            "note",
            "reasoning",
            "--approach",
            "Use a seen-value map.",
            "--invariant",
            "Seen contains prior values.",
            "--complexity",
            "O(n) time and space",
        ]
    ) == 0
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
    session["assistance_log"] = [{"level": "minor"}]
    assert rating_recommendation(problem, session, 4, 4)[0] == "easy"
    session["assistance_log"] = [{"level": "guided"}]
    assert rating_recommendation(problem, session, 4, 4)[0] == "hard"
    session["assistance_log"] = [{"level": "substantial"}]
    assert rating_recommendation(problem, session, 4, 4)[0] == "again"
    assert rating_recommendation(problem, session, 3, 4)[0] == "again"
    assert rating_too_high("hard", "again")
    assert not rating_too_high("again", "again")


def test_recall_quality_caps_rating():
    problem = {"estimated_minutes": 20}
    session = {
        "hints_used": 0,
        "checkpoint_count": 1,
        "accumulated_seconds": 10 * 60,
        "active_started_at": None,
        "initial_reasoning": {"quality": "partial"},
    }
    assert rating_recommendation(problem, session, 4, 4)[0] == "hard"
    session["initial_reasoning"]["quality"] = "failed"
    assert rating_recommendation(problem, session, 4, 4)[0] == "again"


def test_finalize_rejects_rating_above_substantial_help(monkeypatch, tmp_path, capsys):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "solutions").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(root)
    problem = problem_by_id(root, "arrays-001-pair-sum")
    assert main(["start", problem["id"]]) == 0
    (root / "attempt" / "current.py").write_text(
        render_template(problem).replace(
            "    raise NotImplementedError",
            "    seen = {}\n"
            "    for index, value in enumerate(nums):\n"
            "        if target - value in seen:\n"
            "            return [seen[target - value], index]\n"
            "        seen[value] = index",
        )
    )
    assert main(
        [
            "note",
            "reasoning",
            "--approach",
            "Use two pointers.",
            "--invariant",
            "Pointers converge.",
            "--complexity",
            "O(n)",
        ]
    ) == 0
    assert main(
        [
            "note",
            "assistance",
            "--level",
            "substantial",
            "--summary",
            "Supplied the seen-value map invariant.",
        ]
    ) == 0
    reflection = root / "reflection.json"
    reflection.write_text(
        json.dumps(
            {
                "approach": "Use a seen-value map.",
                "insight": "Seen contains prior values.",
                "time_complexity": "O(n)",
                "space_complexity": "O(n)",
                "lessons": "The initial pattern did not fit unsorted input.",
                "assistance": "Codex supplied the core invariant.",
                "rating_rationale": "The solution was not independently recalled.",
            }
        )
    )
    capsys.readouterr()

    assert main(
        [
            "finalize",
            "--rating",
            "hard",
            "--minutes",
            "20",
            "--reflection-file",
            str(reflection),
        ]
    ) == 2
    assert "permits at most Again" in capsys.readouterr().err
    assert (root / "attempt" / "session.json").exists()


def test_reflection_embeds_initial_reasoning_help_and_rating_evidence():
    args = type(
        "Args",
        (),
        {
            "approach": "Group words by frequency tuple.",
            "insight": "Anagrams share all letter counts.",
            "time_complexity": "O(T + W)",
            "space_complexity": "O(W)",
            "lessons": "Two pointers do not represent an entire word.",
            "assistance": "Codex redirected the pattern and explained tuple keys.",
            "rating_rationale": "I did not independently reconstruct the core algorithm.",
        },
    )()
    problem = {"title": "Group Rearranged Words"}
    session = {
        "hints_used": 0,
        "initial_reasoning": {
            "approach": "Use opposite-direction pointers.",
            "invariant": "Pointers avoid nested loops.",
            "expected_complexity": "O(n)",
        },
        "assistance_log": [
            {
                "level": "substantial",
                "source": "conversation",
                "summary": "Supplied the frequency-vector representation.",
            }
        ],
    }

    reflection = render_reflection(
        args,
        problem,
        session,
        "again",
        "Substantial help supplied the core approach.",
    )

    assert "Use opposite-direction pointers" in reflection
    assert "Highest assistance level: substantial" in reflection
    assert "Supplied the frequency-vector representation" in reflection
    assert "Enforced maximum rating: Again" in reflection


def test_public_reflection_scan_rejects_secrets_and_local_paths():
    assert public_content_errors("password=secret")
    assert public_content_errors(r"C:\Users\someone\notes")
    assert public_content_errors("A safe algorithm reflection") == []
