from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from study.core import (
    EASTERN,
    RATINGS,
    current_eastern_date,
    due_problems,
    find_root,
    format_failure,
    git_output,
    latest_by_problem,
    load_events,
    load_problems,
    load_session,
    next_new_problem,
    problem_by_id,
    python_version_ok,
    rebuild_cards,
    record_review,
    run_solution,
    session_path,
    start_problem,
)


def print_problem(problem: dict, prefix: str = "") -> None:
    print(f"{prefix}{problem['id']} - {problem['title']} ({problem['estimated_minutes']} min)")


def cmd_doctor(root: Path, _args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python >= 3.11", python_version_ok(), sys.version.split()[0]))
    git_path = shutil.which("git")
    checks.append(("Git available", git_path is not None, git_path or "missing"))
    code, inside = git_output(root, "rev-parse", "--is-inside-work-tree")
    checks.append(("Git repository", code == 0 and inside == "true", inside or "not initialized"))
    _, name = git_output(root, "config", "--local", "user.name")
    _, email = git_output(root, "config", "--local", "user.email")
    personal = bool(email) and "lmco.com" not in email.lower()
    checks.append(
        ("Repo-local personal identity", bool(name) and personal, f"{name} <{email}>".strip())
    )
    try:
        import fsrs  # noqa: F401

        dependency = True
    except ImportError:
        dependency = False
    dependency_detail = "installed" if dependency else "run pip install -e .[dev]"
    checks.append(("FSRS installed", dependency, dependency_detail))
    problem_count = len(load_problems(root))
    checks.append(("Problem catalog", problem_count == 13, f"{problem_count} exercises"))

    for label, passed, detail in checks:
        print(f"[{'OK' if passed else '!!'}] {label}: {detail}")
    return 0 if all(passed for _, passed, _ in checks) else 1


def cmd_today(root: Path, args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    session = load_session(root)
    print(f"Study queue for {now.astimezone(EASTERN):%A, %B %d} (45 minutes)")
    if session:
        problem = problem_by_id(root, session["problem_id"])
        print_problem(problem, "RESUME  ")
        print(f"        {session['hints_used']} hint(s) used; edit .practice/current.py")
        return 0

    due = due_problems(root, now)
    if due:
        print("\nDue reviews:")
        for problem in due:
            print_problem(problem, "  - ")
    else:
        print("\nNo reviews are due.")

    local_now = now.astimezone(EASTERN)
    if local_now.weekday() < 5 or args.include_new:
        new_problem = next_new_problem(root, include_diagnostic=args.diagnostic)
        if new_problem and new_problem not in due:
            print("\nNew foundation work:")
            print_problem(new_problem, "  - ")
    elif not due:
        print("Weekend: no new problem is scheduled; use --include-new to override.")
    return 0


def cmd_start(root: Path, args: argparse.Namespace) -> int:
    existing = load_session(root)
    if existing and not args.replace:
        print(
            f"An unfinished session exists for {existing['problem_id']}. "
            "Use --replace to discard it."
        )
        return 2
    path = start_problem(root, args.problem_id)
    problem = problem_by_id(root, args.problem_id)
    print_problem(problem, "Started: ")
    print(f"Edit {path.relative_to(root)} and run: python -m study test")
    return 0


def cmd_hint(root: Path, _args: argparse.Namespace) -> int:
    session = load_session(root)
    if not session:
        print("No active problem. Run `python -m study start <problem-id>` first.")
        return 2
    problem = problem_by_id(root, session["problem_id"])
    used = session["hints_used"]
    if used >= len(problem["hints"]):
        print(
            "The full hint ladder has already been used. "
            "Ask Codex for a solution review if needed."
        )
        return 0
    print(f"Hint {used + 1}/{len(problem['hints'])}: {problem['hints'][used]}")
    session["hints_used"] = used + 1
    session_path(root).write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return 0


def test_current(root: Path) -> tuple[dict | None, list]:
    session = load_session(root)
    if not session:
        return None, []
    problem = problem_by_id(root, session["problem_id"])
    return problem, run_solution(root / ".practice" / "current.py", problem)


def cmd_test(root: Path, _args: argparse.Namespace) -> int:
    problem, failures = test_current(root)
    if problem is None:
        print("No active problem. Run `python -m study start <problem-id>` first.")
        return 2
    if failures:
        print(f"{len(failures)} of {len(problem['cases'])} case(s) failed:")
        for failure in failures:
            print(f"  - {format_failure(failure)}")
        return 1
    print(f"PASS — all {len(problem['cases'])} cases passed for {problem['id']}")
    return 0


def cmd_finish(root: Path, args: argparse.Namespace) -> int:
    session = load_session(root)
    if not session:
        print("No active problem to finish.")
        return 2
    problem, failures = test_current(root)
    assert problem is not None
    passed = not failures
    if not passed and args.rating != "again":
        print("Only an Again rating may be recorded while tests fail:")
        for failure in failures:
            print(f"  - {format_failure(failure)}")
        return 2
    if args.rating in {"good", "easy"} and not args.explained:
        print("Good and Easy require --explained after stating the approach and complexity.")
        return 2
    if args.rating == "good" and session["hints_used"] > 1:
        print("Good permits at most one hint; use Hard for this review.")
        return 2
    if args.rating == "easy" and session["hints_used"] > 0:
        print("Easy requires an independent solution; use Good or Hard for this review.")
        return 2

    review_path = record_review(
        root,
        problem,
        args.rating,
        args.minutes,
        passed,
        session["hints_used"],
        args.explained,
    )
    if passed:
        destination = root / "solutions" / f"{problem['id']}.py"
        shutil.copy2(root / ".practice" / "current.py", destination)
    (root / ".practice" / "current.py").unlink(missing_ok=True)
    session_path(root).unlink(missing_ok=True)

    card = rebuild_cards(root)[problem["id"]]
    print(f"Recorded {args.rating.title()} review in {review_path.relative_to(root)}")
    if passed:
        print(f"Promoted passing solution to solutions/{problem['id']}.py")
    print(f"Next review: {card.due.astimezone(EASTERN):%A, %B %d at %I:%M %p %Z}")
    return 0


def mastery(root: Path) -> tuple[int, int, bool]:
    problems = [p for p in load_problems(root) if p["topic"] == "arrays-hashing"]
    events = load_events(root)
    passing = {e["problem_id"] for e in events if e["tests_passed"]}
    review_days: dict[str, set[str]] = defaultdict(set)
    for event in events:
        if (
            event["rating"] in {"good", "easy"}
            and event["tests_passed"]
            and event.get("explained", False)
        ):
            reviewed = datetime.fromisoformat(event["reviewed_at"]).astimezone(EASTERN)
            day = reviewed.date().isoformat()
            review_days[event["problem_id"]].add(day)
    core = [p for p in problems if p["kind"] == "core"]
    transfer = [p for p in problems if p["kind"] == "transfer"]
    mastered_core = sum(p["id"] in passing and len(review_days[p["id"]]) >= 2 for p in core)
    transfer_passed = all(p["id"] in passing for p in transfer)
    return mastered_core, len(core), transfer_passed


def cmd_status(root: Path, _args: argparse.Namespace) -> int:
    events = load_events(root)
    cards = rebuild_cards(root)
    latest = latest_by_problem(root)
    mastered, core_count, transfer = mastery(root)
    print("Foundations / Arrays & Hashing")
    print(f"Core durable reviews: {mastered}/{core_count}")
    print(f"Transfer exercise passed: {'yes' if transfer else 'no'}")
    print(f"Total review events: {len(events)}")
    if not events:
        print("Next step: python -m study today")
        return 0
    print("\nReviewed problems:")
    catalog = {p["id"]: p for p in load_problems(root)}
    for problem_id, event in sorted(latest.items()):
        due = cards[problem_id].due.astimezone(EASTERN)
        print(f"  - {catalog[problem_id]['title']}: {event['rating']} -> due {due:%Y-%m-%d}")
    return 0


def reminder_text(root: Path) -> str:
    due = due_problems(root)
    lines = [
        f"# Practice due - {current_eastern_date()}",
        "",
        "Your adaptive review queue is ready. Start with recall before opening old code.",
        "",
    ]
    if due:
        lines.append("## Due reviews")
        lines.append("")
        for problem in due:
            lines.append(
                f"- [ ] `{problem['id']}` - {problem['title']} "
                f"({problem['topic']}, about {problem['estimated_minutes']} min)"
            )
    else:
        lines.extend(["No spaced-repetition reviews are due today.", ""])

    local_now = datetime.now(EASTERN)
    new_problem = next_new_problem(root)
    if local_now.weekday() < 5 and new_problem:
        lines.extend(
            [
                "",
                "## New foundation work",
                "",
                f"- [ ] `{new_problem['id']}` - {new_problem['title']} "
                f"(about {new_problem['estimated_minutes']} min)",
            ]
        )
    lines.extend(
        [
            "",
            "## Start",
            "",
            "```powershell",
            "git pull --rebase",
            "python -m study today",
            "```",
            "",
            "Rate each completed review with Again, Hard, Good, or Easy and push the new event.",
        ]
    )
    return "\n".join(lines) + "\n"


def cmd_reminder(root: Path, _args: argparse.Namespace) -> int:
    print(reminder_text(root), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="study", description="Algorithm learning companion")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check local setup")
    today = commands.add_parser("today", help="show today's study queue")
    today.add_argument("--diagnostic", action="store_true", help="offer unreviewed diagnostic work")
    today.add_argument("--include-new", action="store_true", help="offer new work on weekends")
    start = commands.add_parser("start", help="begin one exercise")
    start.add_argument("problem_id")
    start.add_argument("--replace", action="store_true", help="replace an unfinished session")
    commands.add_parser("hint", help="reveal the next progressive hint")
    commands.add_parser("test", help="run cases for the active attempt")
    finish = commands.add_parser("finish", help="record a review and close the active attempt")
    finish.add_argument("--rating", required=True, choices=RATINGS)
    finish.add_argument("--minutes", required=True, type=int)
    finish.add_argument(
        "--explained",
        action="store_true",
        help="confirm you explained the approach and time/space complexity",
    )
    commands.add_parser("status", help="show roadmap and review progress")
    commands.add_parser("reminder", help="render today's GitHub reminder issue")
    return parser


COMMANDS = {
    "doctor": cmd_doctor,
    "today": cmd_today,
    "start": cmd_start,
    "hint": cmd_hint,
    "test": cmd_test,
    "finish": cmd_finish,
    "status": cmd_status,
    "reminder": cmd_reminder,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "minutes", 1) <= 0:
        print("--minutes must be positive", file=sys.stderr)
        return 2
    try:
        root = find_root()
        return COMMANDS[args.command](root, args)
    except (KeyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
