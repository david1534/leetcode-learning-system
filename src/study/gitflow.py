from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitFlowError(RuntimeError):
    """A recoverable Git condition that needs learner attention."""


@dataclass
class GitResult:
    code: int
    output: str


def run_git(root: Path, *args: str) -> GitResult:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return GitResult(124, f"git {' '.join(args)} timed out after 20 seconds")
    parts = [part.rstrip() for part in (result.stdout, result.stderr) if part.strip()]
    output = "\n".join(parts)
    return GitResult(result.returncode, output)


def require_git(root: Path) -> None:
    result = run_git(root, "rev-parse", "--is-inside-work-tree")
    if result.code or result.output.splitlines()[0] != "true":
        raise GitFlowError("This folder is not an initialized Git repository.")


def branch_name(root: Path) -> str:
    result = run_git(root, "branch", "--show-current")
    if result.code or not result.output:
        raise GitFlowError("Git could not determine the current branch.")
    return result.output.splitlines()[0]


def attempt_branch(problem_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", problem_id).strip("-")
    return f"attempt/{safe}"


def tracked_changes(root: Path, exclude_attempt: bool = False) -> list[str]:
    result = run_git(root, "status", "--porcelain", "--untracked-files=all")
    if result.code:
        raise GitFlowError(f"Git status failed: {result.output}")
    paths = []
    for line in result.output.splitlines():
        path = line[3:].split(" -> ")[-1].replace("\\", "/")
        if exclude_attempt and path.startswith("attempt/"):
            continue
        paths.append(path)
    return paths


def cleanup_stale_completed_attempt(root: Path) -> bool:
    """Remove only attempt residue that is provably safe to discard."""
    attempt = root / "attempt"
    if not attempt.exists() or (attempt / "session.json").exists():
        return False

    tracked = run_git(root, "ls-files", "--", "attempt")
    if tracked.code:
        raise GitFlowError(f"Could not inspect stale attempt files: {tracked.output}")
    if tracked.output:
        return False

    allowed_cache_dirs = {".mypy_cache", "__pycache__"}
    unknown = sorted(
        child.name
        for child in attempt.iterdir()
        if not (
            child.name == "current.py" and child.is_file()
            or child.name in allowed_cache_dirs and child.is_dir()
        )
    )
    if unknown:
        raise GitFlowError(
            "Practice startup preserved attempt/ because it contains unrecognized files that "
            f"may be learner work: {', '.join(unknown)}"
        )

    candidate = attempt / "current.py"
    if candidate.exists():
        candidate_bytes = candidate.read_bytes()
        published = root / "solutions"
        matches_published = published.exists() and any(
            path.read_bytes() == candidate_bytes for path in published.glob("*.py")
        )
        if not matches_published:
            raise GitFlowError(
                "Practice startup preserved attempt/current.py because it does not exactly "
                "match a published solution. Inspect it before removing anything."
            )

    try:
        shutil.rmtree(attempt)
    except OSError as exc:
        raise GitFlowError(
            "A completed attempt left safe-to-remove files, but Windows could not remove them. "
            "Close any old attempt/current.py editor tab and retry practice. "
            f"Details: {exc}"
        ) from exc
    return True


def fetch(root: Path) -> None:
    result = run_git(root, "fetch", "--prune", "origin")
    if result.code:
        raise GitFlowError(f"Could not contact GitHub: {result.output}")


def fast_forward_main(root: Path) -> bool:
    if branch_name(root) != "main":
        raise GitFlowError("Start/Resume expected the main branch. Run `python -m study sync`.")
    recovered_stale_attempt = cleanup_stale_completed_attempt(root)
    if tracked_changes(root):
        raise GitFlowError(
            "Git has unsaved tracked changes. Commit, stash, or restore them before "
            "starting practice."
        )
    fetch(root)
    result = run_git(root, "merge", "--ff-only", "origin/main")
    if result.code:
        raise GitFlowError(
            "Local main and GitHub main have diverged. No files were changed; resolve Git manually."
        )
    return recovered_stale_attempt


def remote_attempts(root: Path) -> list[str]:
    result = run_git(
        root,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/remotes/origin/attempt",
    )
    if result.code:
        raise GitFlowError(f"Could not list attempt branches: {result.output}")
    return [line.removeprefix("origin/") for line in result.output.splitlines() if line]


def create_attempt_branch(root: Path, problem_id: str) -> str:
    name = attempt_branch(problem_id)
    result = run_git(root, "switch", "-c", name)
    if result.code:
        raise GitFlowError(f"Could not create {name}: {result.output}")
    return name


def switch_to_remote_attempt(root: Path, name: str) -> None:
    if tracked_changes(root):
        raise GitFlowError("Unsaved tracked changes prevent switching to the remote attempt.")
    result = run_git(root, "switch", "--track", "-c", name, f"origin/{name}")
    if result.code:
        result = run_git(root, "switch", name)
    if result.code:
        raise GitFlowError(f"Could not resume {name}: {result.output}")
    result = run_git(root, "merge", "--ff-only", f"origin/{name}")
    if result.code:
        raise GitFlowError(f"Local and remote {name} have diverged; no merge was attempted.")


def update_current_attempt(root: Path) -> bool:
    """Update a clean attempt; return False when it was completed elsewhere."""
    name = branch_name(root)
    if not name.startswith("attempt/") or tracked_changes(root):
        return True
    fetch(root)
    remote = run_git(root, "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{name}")
    if remote.code:
        merged = run_git(root, "merge-base", "--is-ancestor", name, "origin/main")
        if merged.code == 0:
            switched = run_git(root, "switch", "main")
            if switched.code:
                raise GitFlowError(f"Could not return to main: {switched.output}")
            updated = run_git(root, "merge", "--ff-only", "origin/main")
            if updated.code:
                raise GitFlowError(f"Could not update completed main: {updated.output}")
            deleted = run_git(root, "branch", "-D", name)
            if deleted.code:
                raise GitFlowError(
                    "Main updated, but stale local branch cleanup failed: "
                    f"{deleted.output}"
                )
            return False
        return True
    result = run_git(root, "merge", "--ff-only", f"origin/{name}")
    if result.code:
        raise GitFlowError(f"Local and remote {name} have diverged; no files were changed.")
    return True


def commit_paths(root: Path, message: str, paths: list[str]) -> bool:
    if not paths:
        return False
    add = run_git(root, "add", "--", *paths)
    if add.code:
        raise GitFlowError(f"Could not stage practice files: {add.output}")
    staged = run_git(root, "diff", "--cached", "--quiet", "--", *paths)
    if staged.code == 0:
        return False
    commit = run_git(root, "commit", "-m", message, "--", *paths)
    if commit.code:
        raise GitFlowError(f"Could not create practice checkpoint: {commit.output}")
    return True


def push_current(root: Path, set_upstream: bool = False) -> None:
    name = branch_name(root)
    args = ("push", "-u", "origin", name) if set_upstream else ("push", "origin", name)
    result = run_git(root, *args)
    if result.code:
        raise GitFlowError(
            "The local checkpoint is safe, but GitHub sync failed. "
            f"Run `python -m study sync` later. Details: {result.output}"
        )


def merge_completed_attempt(root: Path, name: str) -> None:
    result = run_git(root, "switch", "main")
    if result.code:
        raise GitFlowError(f"Could not switch to main: {result.output}")
    fetch(root)
    result = run_git(root, "merge", "--ff-only", "origin/main")
    if result.code:
        raise GitFlowError("GitHub main changed during completion; merge stopped safely.")
    result = run_git(
        root,
        "merge",
        "--no-ff",
        "-m",
        f"study: complete {name.removeprefix('attempt/')}",
        name,
    )
    if result.code:
        raise GitFlowError(f"Attempt merge requires manual resolution: {result.output}")
    push = run_git(root, "push", "origin", "main")
    if push.code:
        raise GitFlowError(f"Merge is local but main did not push: {push.output}")
    deleted = run_git(root, "branch", "-D", name)
    if deleted.code:
        raise GitFlowError(f"Main is published, but local branch cleanup failed: {deleted.output}")
    deleted_remote = run_git(root, "push", "origin", "--delete", name)
    if deleted_remote.code:
        raise GitFlowError(
            f"Main is published, but remote branch cleanup failed: {deleted_remote.output}"
        )


def sync_branch(root: Path) -> str:
    name = branch_name(root)
    push_current(root, set_upstream=False)
    return name
