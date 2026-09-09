from __future__ import annotations

from argparse import Namespace

from study.cli import apply_reflection_file, main
from study.core import problem_by_id, run_solution


def test_optional_completion_inputs_do_not_crash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # No session is a recoverable error, not a None-versus-int TypeError.
    assert main(["finalize", "--rating", "good"]) == 2
    args = Namespace(
        **dict.fromkeys(
            (
                "approach",
                "insight",
                "time_complexity",
                "space_complexity",
                "lessons",
                "assistance",
                "rating_rationale",
            ),
            "Recorded evidence",
        )
    )
    assert apply_reflection_file(args).approach == "Recorded evidence"


def test_encoding_cannot_be_an_identity_function(tmp_path, repo_root):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def round_trip_strings(values):\n    return values\n")
    assert run_solution(candidate, problem_by_id(repo_root, "arrays-007-encode-decode"))


def test_sudoku_must_check_rows_and_boxes(tmp_path, repo_root):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "def valid_partial_grid(board):\n"
        "    return all(len([r[i] for r in board if r[i] != '.']) == "
        "len({r[i] for r in board if r[i] != '.'}) for i in range(9))\n"
    )
    assert run_solution(candidate, problem_by_id(repo_root, "arrays-005-sudoku-check"))


def test_runner_timeout_preserves_candidate(tmp_path, repo_root):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def pair_sum_indices(nums, target):\n    while True: pass\n")
    failures = run_solution(candidate, problem_by_id(repo_root, "arrays-001-pair-sum"), timeout=0.3)
    assert "timed out" in failures[0].error.lower()
    assert candidate.exists()
