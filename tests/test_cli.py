from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from study.cli import (
    main,
    public_content_errors,
    rating_recommendation,
    rating_too_high,
    reminder_text,
    render_reflection,
)
from study.core import (
    problem_by_id,
    record_learning_error,
    record_review,
    render_template,
    save_session,
)
from study.gitflow import GitFlowError, cleanup_stale_completed_attempt


def test_stale_completed_attempt_cleanup_is_narrow_and_safe(monkeypatch, tmp_path):
    root = tmp_path
    attempt = root / "attempt"
    solutions = root / "solutions"
    attempt.mkdir()
    solutions.mkdir()
    published = b"def solved():\n    return True\n"
    (solutions / "done.py").write_bytes(published)
    (attempt / "current.py").write_bytes(published)
    (attempt / ".mypy_cache").mkdir()
    (attempt / ".mypy_cache" / "metadata.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "study.gitflow.run_git", lambda *_args: type("Result", (), {"code": 0, "output": ""})()
    )

    assert cleanup_stale_completed_attempt(root) is True
    assert not attempt.exists()


def test_stale_attempt_cleanup_removes_cache_only_residue(monkeypatch, tmp_path):
    attempt = tmp_path / "attempt"
    (attempt / "__pycache__").mkdir(parents=True)
    monkeypatch.setattr(
        "study.gitflow.run_git", lambda *_args: type("Result", (), {"code": 0, "output": ""})()
    )

    assert cleanup_stale_completed_attempt(tmp_path) is True
    assert not attempt.exists()


def test_stale_attempt_cleanup_preserves_ambiguous_work(monkeypatch, tmp_path):
    root = tmp_path
    attempt = root / "attempt"
    solutions = root / "solutions"
    attempt.mkdir()
    solutions.mkdir()
    (solutions / "done.py").write_text("published", encoding="utf-8")
    (attempt / "current.py").write_text("different learner work", encoding="utf-8")
    monkeypatch.setattr(
        "study.gitflow.run_git", lambda *_args: type("Result", (), {"code": 0, "output": ""})()
    )

    with pytest.raises(GitFlowError, match="does not exactly match"):
        cleanup_stale_completed_attempt(root)
    assert (attempt / "current.py").read_text(encoding="utf-8") == "different learner work"

    (attempt / "current.py").write_text("published", encoding="utf-8")
    (attempt / "notes.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(GitFlowError, match="unrecognized files"):
        cleanup_stale_completed_attempt(root)
    assert (attempt / "notes.txt").exists()

    (attempt / "notes.txt").unlink()
    monkeypatch.setattr(
        "study.gitflow.run_git",
        lambda *_args: type("Result", (), {"code": 0, "output": "attempt/current.py"})(),
    )
    assert cleanup_stale_completed_attempt(root) is False
    assert (attempt / "current.py").exists()


def test_stale_attempt_cleanup_preserves_active_session_and_reports_locks(
    monkeypatch, tmp_path
):
    root = tmp_path
    attempt = root / "attempt"
    solutions = root / "solutions"
    attempt.mkdir()
    solutions.mkdir()
    (attempt / "session.json").write_text("{}", encoding="utf-8")
    assert cleanup_stale_completed_attempt(root) is False
    assert attempt.exists()

    (attempt / "session.json").unlink()
    (attempt / "__pycache__").mkdir()
    monkeypatch.setattr(
        "study.gitflow.run_git", lambda *_args: type("Result", (), {"code": 0, "output": ""})()
    )
    monkeypatch.setattr(
        "study.gitflow.shutil.rmtree",
        lambda _path: (_ for _ in ()).throw(PermissionError("locked")),
    )
    with pytest.raises(GitFlowError, match="Close any old attempt/current.py editor tab"):
        cleanup_stale_completed_attempt(root)


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


def test_repair_gate_is_actionable_and_suppresses_new_work_in_reminder(tmp_path, monkeypatch):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "attempt").mkdir()
    started = datetime(2026, 8, 24, 12, tzinfo=UTC)
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "arrays-001-pair-sum",
            "started_at": started.isoformat(),
            "active_started_at": None,
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    path = record_learning_error(
        root,
        "complement lookup",
        "pattern-selection",
        "misconception",
        "blocking",
        "Selected a pattern that loses the required indices.",
        "Notice that original indices must be preserved.",
        "Keep prior values mapped to their indices.",
        "Apply complement lookup to a fresh list.",
        recorded_at=started,
    )
    error_id = json.loads(path.read_text(encoding="utf-8"))["event_id"]

    class WeekdayDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 8, 27, 12, tzinfo=UTC)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr("study.cli.datetime", WeekdayDatetime)
    text = reminder_text(root)

    assert "## Repair gates" in text
    assert f"Error ID: `{error_id}`" in text
    assert f"study repair --error-id {error_id}" in text
    assert "## New foundation work" not in text


def test_practice_and_insights_show_repair_error_id(monkeypatch, tmp_path, capsys):
    root = tmp_path
    (root / "curriculum").mkdir()
    source = Path(__file__).parents[1] / "curriculum" / "problems.json"
    (root / "curriculum" / "problems.json").write_text(source.read_text(encoding="utf-8"))
    (root / "progress" / "reviews").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    (root / "attempt").mkdir()
    started = datetime.now(UTC) - timedelta(days=2)
    save_session(
        root,
        {
            "schema_version": 5,
            "problem_id": "arrays-001-pair-sum",
            "started_at": started.isoformat(),
            "active_started_at": None,
            "accumulated_seconds": 0,
            "hints_used": 0,
            "checkpoint_count": 0,
        },
    )
    path = record_learning_error(
        root,
        "complement lookup",
        "pattern-selection",
        "misconception",
        "blocking",
        "Selected a pattern that loses the required indices.",
        "Notice that original indices must be preserved.",
        "Keep prior values mapped to their indices.",
        "Apply complement lookup to a fresh list.",
        recorded_at=started,
    )
    error_id = json.loads(path.read_text(encoding="utf-8"))["event_id"]
    (root / "attempt" / "session.json").unlink()
    (root / "attempt").rmdir()
    monkeypatch.chdir(root)

    assert main(["practice", "--no-sync"]) == 0
    practice_output = capsys.readouterr().out
    assert f"Error ID: {error_id}" in practice_output
    assert f"study repair --error-id {error_id}" in practice_output

    assert main(["today"]) == 0
    today_output = capsys.readouterr().out
    assert f"Error ID: {error_id}" in today_output

    assert main(["insights"]) == 0
    insights_output = capsys.readouterr().out
    assert f"Error ID: {error_id}" in insights_output


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


def test_finalize_preflight_failures_do_not_mutate_attempt_or_publish_files(
    monkeypatch, tmp_path, capsys
):
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
    candidate = root / "attempt" / "current.py"
    candidate.write_text(
        render_template(problem).replace(
            "    raise NotImplementedError",
            "    seen = {}\n"
            "    for index, value in enumerate(nums):\n"
            "        if target - value in seen:\n"
            "            return [seen[target - value], index]\n"
            "        seen[value] = index",
        ),
        encoding="utf-8",
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
    reflection = root / "reflection.json"
    reflection.write_text(
        json.dumps(
            {
                "approach": "Use a seen-value map.",
                "insight": "Seen contains prior values.",
                "time_complexity": "O(n)",
                "space_complexity": "O(n)",
                "lessons": "Check the complement before storing the current value.",
                "assistance": "No algorithmic assistance was used.",
                "rating_rationale": "The solution was independently reconstructed.",
            }
        ),
        encoding="utf-8",
    )
    command = [
        "finalize",
        "--rating",
        "easy",
        "--minutes",
        "10",
        "--reflection-file",
        str(reflection),
    ]
    capsys.readouterr()

    monkeypatch.setattr("study.cli.branch_name", lambda _root: "main")
    assert main(command) == 2
    assert "attempt branch" in capsys.readouterr().err
    assert candidate.exists()
    assert (root / "attempt" / "session.json").exists()
    assert not (root / "solutions" / f"{problem['id']}.py").exists()
    assert not (root / "reflections").exists()
    assert not list((root / "progress" / "reviews").glob("*.json"))

    monkeypatch.setattr("study.cli.branch_name", lambda _root: f"attempt/{problem['id']}")
    monkeypatch.setattr("study.cli.tracked_changes", lambda _root, exclude_attempt: ["README.md"])
    assert main(command) == 2
    assert "Unrelated tracked changes" in capsys.readouterr().err
    assert candidate.exists()
    assert (root / "attempt" / "session.json").exists()
    assert not (root / "solutions" / f"{problem['id']}.py").exists()
    assert not (root / "reflections").exists()
    assert not list((root / "progress" / "reviews").glob("*.json"))


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
