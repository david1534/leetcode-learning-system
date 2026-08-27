from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

from study.cli import cmd_finalize, main


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=20
    )
    return result.stdout.strip()


def configure(root: Path) -> None:
    git(root, "config", "user.name", "Test Learner")
    git(root, "config", "user.email", "learner@users.noreply.github.com")


def seed_remote(tmp_path: Path, repo_root: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-b", "main")
    configure(seed)
    (seed / "curriculum").mkdir()
    catalog = repo_root / "curriculum" / "problems.json"
    (seed / "curriculum" / "problems.json").write_text(catalog.read_text(encoding="utf-8"))
    (seed / "progress" / "reviews").mkdir(parents=True)
    (seed / "progress" / "reviews" / ".gitkeep").write_text("")
    (seed / "pyproject.toml").write_text("[project]\nname='cross-device-test'\n")
    git(seed, "add", ".")
    git(seed, "commit", "-m", "seed")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    return remote, seed


def clone(remote: Path, target: Path) -> Path:
    subprocess.run(["git", "clone", str(remote), str(target)], check=True, capture_output=True)
    configure(target)
    return target


def test_attempt_moves_between_laptops_and_merges_to_main(monkeypatch, tmp_path, repo_root, capsys):
    remote, _seed = seed_remote(tmp_path, repo_root)
    laptop_a = clone(remote, tmp_path / "laptop-a")
    monkeypatch.chdir(laptop_a)
    assert main(["practice"]) == 0
    assert git(laptop_a, "branch", "--show-current") == "attempt/arrays-001-pair-sum"

    candidate = laptop_a / "attempt" / "current.py"
    assert main(
        [
            "note",
            "reasoning",
            "--approach",
            "Use a seen map.",
            "--invariant",
            "Seen contains earlier values.",
            "--complexity",
            "O(n)",
        ]
    ) == 0
    candidate.write_text("def pair_sum_indices(nums, target):\n    return [0, 1]\n")
    assert main(["checkpoint"]) == 0
    checkpoint = json.loads((laptop_a / "attempt" / "session.json").read_text(encoding="utf-8"))[
        "latest_checkpoint"
    ]
    assert set(checkpoint) == {
        "attempt",
        "checked_at",
        "passed_cases",
        "total_cases",
    }

    before_pause = clone(remote, tmp_path / "before-pause")
    git(before_pause, "switch", "--track", "origin/attempt/arrays-001-pair-sum")
    assert "return [0, 1]" not in (before_pause / "attempt" / "current.py").read_text()

    assert main(["pause"]) == 0

    laptop_b = clone(remote, tmp_path / "laptop-b")
    monkeypatch.chdir(laptop_b)
    assert main(["practice"]) == 0
    assert git(laptop_b, "branch", "--show-current") == "attempt/arrays-001-pair-sum"
    (laptop_b / "attempt" / "current.py").write_text(
        "def pair_sum_indices(nums, target):\n"
        "    seen = {}\n"
        "    for i, value in enumerate(nums):\n"
        "        if target - value in seen:\n"
        "            return [seen[target - value], i]\n"
        "        seen[value] = i\n"
    )
    assert main(["checkpoint"]) == 0
    args = Namespace(
        rating="good",
        minutes=15,
        approach="Track each prior value and look up the required complement.",
        insight="Check the complement before storing the current index.",
        time_complexity="O(n)",
        space_complexity="O(n)",
        lessons="A one-pass map avoids checking every pair.",
        assistance="No algorithmic assistance was used.",
        rating_rationale="The approach was independently recalled and verified.",
        reflection_file=None,
        sync=True,
    )
    assert cmd_finalize(laptop_b, args) == 0
    capsys.readouterr()
    assert git(laptop_b, "branch", "--show-current") == "main"
    assert not git(laptop_b, "branch", "-r", "--list", "origin/attempt/*")

    monkeypatch.chdir(laptop_a)
    assert main(["practice"]) == 0
    assert git(laptop_a, "branch", "--show-current").startswith("attempt/arrays-002")
