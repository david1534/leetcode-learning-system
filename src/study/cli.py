from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from study.core import (
    EASTERN,
    RATINGS,
    active_seconds,
    candidate_path,
    cleanup_legacy_attempt,
    current_eastern_date,
    due_problems,
    find_root,
    format_failure,
    git_output,
    latest_by_problem,
    load_events,
    load_problems,
    load_session,
    migrate_legacy_attempt,
    next_new_problem,
    pause_timer,
    problem_by_id,
    python_version_ok,
    rebuild_cards,
    record_review,
    resume_timer,
    run_solution,
    save_session,
    session_path,
    start_problem,
)
from study.gitflow import (
    GitFlowError,
    branch_name,
    commit_paths,
    create_attempt_branch,
    fast_forward_main,
    merge_completed_attempt,
    push_current,
    remote_attempts,
    require_git,
    switch_to_remote_attempt,
    sync_branch,
    tracked_changes,
    update_current_attempt,
)


def print_problem(problem: dict, prefix: str = "") -> None:
    print(f"{prefix}{problem['id']} - {problem['title']} ({problem['estimated_minutes']} min)")


def open_candidate(root: Path) -> None:
    code = shutil.which("code")
    if code:
        subprocess.run([code, "-r", str(candidate_path(root))], check=False)


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
        print(f"        {session['hints_used']} hint(s) used; edit attempt/current.py")
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


def cmd_practice(root: Path, args: argparse.Namespace) -> int:
    """Resume active work or automatically start the highest-priority problem."""
    if not args.no_sync:
        require_git(root)
        current_branch = branch_name(root)
        if current_branch.startswith("attempt/"):
            if update_current_attempt(root):
                resume_timer(root)
            current_branch = branch_name(root)
        if current_branch == "main":
            fast_forward_main(root)
            attempts = remote_attempts(root)
            if len(attempts) > 1:
                raise GitFlowError(
                    "More than one public attempt exists. Finish or remove the extra "
                    "attempt branch."
                )
            if attempts:
                switch_to_remote_attempt(root, attempts[0])
                resume_timer(root)

            legacy = root / ".practice" / "session.json"
            if legacy.exists() and not attempts:
                legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
                create_attempt_branch(root, legacy_data["problem_id"])
                migrate_legacy_attempt(root)
                commit_paths(
                    root,
                    f"study(draft): migrate {legacy_data['problem_id']}",
                    ["attempt"],
                )
                push_current(root, set_upstream=True)
                cleanup_legacy_attempt(root)

    session = load_session(root)
    if session:
        if args.no_sync and migrate_legacy_attempt(root):
            session = load_session(root)
        assert session is not None
        problem = problem_by_id(root, session["problem_id"])
        print_problem(problem, "Resuming: ")
        print("Open attempt/current.py and continue your solution.")
        if args.open:
            open_candidate(root)
        return 0

    due = due_problems(root)
    problem = due[0] if due else next_new_problem(root)
    if problem is None:
        print("No problem is available. Your current exercise catalog is complete.")
        return 0

    if not args.no_sync:
        create_attempt_branch(root, problem["id"])
    path = start_problem(root, problem["id"])
    if not args.no_sync:
        commit_paths(root, f"study(draft): start {problem['id']}", ["attempt"])
        push_current(root, set_upstream=True)
    reason = "due review" if due else "next roadmap problem"
    print_problem(problem, f"Started {reason}: ")
    print(f"Open {path.relative_to(root)} and write your solution.")
    print("When ready, run the VS Code task: Study: Check Solution Locally")
    if args.open:
        open_candidate(root)
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
        print("No active problem. Press Ctrl+Shift+B to start one.")
        return 2
    problem = problem_by_id(root, session["problem_id"])
    used = session["hints_used"]
    if used >= len(problem["hints"]):
        print(
            "The full hint ladder has already been used. "
            "Ask Codex for a solution review if needed."
        )
        return 0
    stages = ("Targeted question", "Pattern clue", "Pseudocode")
    label = stages[used] if used < len(stages) else f"Hint {used + 1}"
    print(f"{label}: {problem['hints'][used]}")
    session["hints_used"] = used + 1
    save_session(root, session)
    return 0


def test_current(root: Path) -> tuple[dict | None, list]:
    session = load_session(root)
    if not session:
        return None, []
    problem = problem_by_id(root, session["problem_id"])
    return problem, run_solution(candidate_path(root), problem)


def cmd_test(root: Path, _args: argparse.Namespace) -> int:
    problem, failures = test_current(root)
    if problem is None:
        print("No active problem. Press Ctrl+Shift+B to start one.")
        return 2
    if failures:
        print(f"{len(failures)} of {len(problem['cases'])} case(s) failed:")
        for failure in failures:
            print(f"  - {format_failure(failure)}")
        return 1
    print(f"PASS — all {len(problem['cases'])} cases passed for {problem['id']}")
    return 0


def passed_count(total: int, failures: list) -> int:
    return 0 if any(failure.index == 0 for failure in failures) else total - len(failures)


def checkpoint(root: Path) -> tuple[dict, int, int, list]:
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem. Press Ctrl+Shift+B to start one.")
    problem, failures = test_current(root)
    assert problem is not None
    total = len(problem["cases"])
    passed = passed_count(total, failures)
    session["checkpoint_count"] = int(session.get("checkpoint_count", 0)) + 1
    session["latest_checkpoint"] = {
        "attempt": session["checkpoint_count"],
        "checked_at": datetime.now(UTC).isoformat(),
        "passed_cases": passed,
        "total_cases": total,
    }
    save_session(root, session)
    return problem, passed, total, failures


def cmd_checkpoint(root: Path, args: argparse.Namespace) -> int:
    problem, passed, total, failures = checkpoint(root)
    result = {
        "problem_id": problem["id"],
        "passed_cases": passed,
        "total_cases": total,
        "all_passed": passed == total,
        "checkpoint_count": load_session(root)["checkpoint_count"],
        "failure_count": len(failures),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Local check saved for {problem['id']}: {passed}/{total} cases passed.")
    if passed < total and not args.json:
        print("Failure details stayed local:")
        for failure in failures:
            print(f"  - {format_failure(failure)}")
        print("Ask Codex to discuss one issue, then revise the draft and check again.")
    return 0


def cmd_pause(root: Path, _args: argparse.Namespace) -> int:
    session = pause_timer(root)
    problem = problem_by_id(root, session["problem_id"])
    commit_paths(root, f"study(draft): pause {problem['id']}", ["attempt"])
    push_current(root)
    print(f"Paused and synchronized {problem['title']}.")
    return 0


def rating_recommendation(problem: dict, session: dict, passed: int, total: int) -> tuple[str, str]:
    if passed < total:
        return "again", "The solution does not pass all cases yet."
    hints = int(session.get("hints_used", 0))
    checkpoints = int(session.get("checkpoint_count", 0))
    minutes = max(1, round(active_seconds(session) / 60))
    if hints > 1:
        return "hard", "It passed, but more than one hint was used."
    if hints == 1:
        return "good", "It passed with one hint."
    if checkpoints <= 1 and minutes <= int(problem["estimated_minutes"]):
        return "easy", "It passed on the first checkpoint, independently, within the estimate."
    return "good", "It passed independently; multiple checkpoints or extra time were used."


def evaluation(root: Path) -> dict:
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem to evaluate.")
    problem, failures = test_current(root)
    assert problem is not None
    total = len(problem["cases"])
    passed = passed_count(total, failures)
    rating, rationale = rating_recommendation(problem, session, passed, total)
    return {
        "problem_id": problem["id"],
        "title": problem["title"],
        "passed_cases": passed,
        "total_cases": total,
        "hints_used": int(session.get("hints_used", 0)),
        "checkpoint_count": int(session.get("checkpoint_count", 0)),
        "active_minutes": max(1, round(active_seconds(session) / 60)),
        "recommended_rating": rating,
        "rating_rationale": rationale,
    }


def cmd_evaluate(root: Path, args: argparse.Namespace) -> int:
    result = evaluation(root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['passed_cases']}/{result['total_cases']} cases passed")
        print(f"Active time: {result['active_minutes']} minutes")
        print(
            f"Recommended rating: {result['recommended_rating'].title()} — "
            f"{result['rating_rationale']}"
        )
    return 0


def reflection_path(root: Path, problem_id: str) -> Path:
    return root / "reflections" / f"{problem_id}.md"


def public_content_errors(text: str) -> list[str]:
    lowered = text.lower()
    errors = []
    for marker in ("password=", "api_key", "api-key", "token=", "david.1.wan@lmco.com"):
        if marker in lowered:
            errors.append(marker)
    if "c:\\users\\" in lowered or "/home/" in lowered:
        errors.append("local filesystem path")
    if re.search(r"[\w.+-]+@lmco\.com", lowered):
        errors.append("employer email")
    return errors


def render_reflection(args: argparse.Namespace, problem: dict) -> str:
    return (
        f"# {problem['title']}\n\n"
        f"## Approach\n\n{args.approach.strip()}\n\n"
        f"## Key invariant or insight\n\n{args.insight.strip()}\n\n"
        f"## Complexity\n\n- Time: `{args.time_complexity.strip()}`\n"
        f"- Space: `{args.space_complexity.strip()}`\n\n"
        f"## Mistakes and lessons\n\n{args.lessons.strip()}\n\n"
        f"## Effect of hints\n\n{args.hint_effect.strip()}\n"
    )


def apply_reflection_file(args: argparse.Namespace) -> argparse.Namespace:
    payload = {}
    if args.reflection_file:
        payload = json.loads(Path(args.reflection_file).read_text(encoding="utf-8"))
    for field in (
        "approach",
        "insight",
        "time_complexity",
        "space_complexity",
        "lessons",
        "hint_effect",
    ):
        value = payload.get(field) or getattr(args, field, None)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Completion needs a non-empty {field!r} reflection field.")
        setattr(args, field, value)
    return args


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
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(candidate_path(root), destination)
    candidate_path(root).unlink(missing_ok=True)
    session_path(root).unlink(missing_ok=True)

    card = rebuild_cards(root)[problem["id"]]
    print(f"Recorded {args.rating.title()} review in {review_path.relative_to(root)}")
    if passed:
        print(f"Promoted passing solution to solutions/{problem['id']}.py")
    print(f"Next review: {card.due.astimezone(EASTERN):%A, %B %d at %I:%M %p %Z}")
    return 0


def cmd_finalize(root: Path, args: argparse.Namespace) -> int:
    args = apply_reflection_file(args)
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem to finalize.")
    problem, failures = test_current(root)
    assert problem is not None
    if failures:
        raise RuntimeError("The solution must pass all cases before completion.")
    if args.rating == "good" and int(session.get("hints_used", 0)) > 1:
        raise RuntimeError("Good permits at most one hint; choose Hard.")
    if args.rating == "easy" and int(session.get("hints_used", 0)) > 0:
        raise RuntimeError("Easy requires an independent solution; choose Good or Hard.")

    minutes = args.minutes or max(1, round(active_seconds(session) / 60))
    reflection = render_reflection(args, problem)
    candidate_text = candidate_path(root).read_text(encoding="utf-8")
    unsafe = public_content_errors(reflection + "\n" + candidate_text)
    if unsafe:
        raise RuntimeError(f"Reflection contains public-content risks: {', '.join(unsafe)}")

    destination = root / "solutions" / f"{problem['id']}.py"
    destination.parent.mkdir(exist_ok=True)
    shutil.copy2(candidate_path(root), destination)
    reflection_file = reflection_path(root, problem["id"])
    reflection_file.parent.mkdir(exist_ok=True)
    reflection_file.write_text(reflection, encoding="utf-8")
    review_path = record_review(
        root,
        problem,
        args.rating,
        minutes,
        True,
        int(session.get("hints_used", 0)),
        True,
    )
    shutil.rmtree(root / "attempt")
    name = branch_name(root)
    if not name.startswith("attempt/"):
        raise GitFlowError("Completion must run on an attempt branch.")
    paths = [
        "attempt",
        destination.relative_to(root).as_posix(),
        reflection_file.relative_to(root).as_posix(),
        review_path.relative_to(root).as_posix(),
    ]
    unrelated = tracked_changes(root, exclude_attempt=True)
    allowed = set(paths[1:])
    extra = [path for path in unrelated if path not in allowed]
    if extra:
        raise GitFlowError(f"Unrelated tracked changes block completion: {', '.join(extra)}")
    commit_paths(root, f"study: finish {problem['id']} ({args.rating})", paths)
    push_current(root)
    if args.sync:
        merge_completed_attempt(root, name)
        print(f"Completed and synchronized {problem['title']} to main.")
    else:
        print(
            "Completion is committed on the attempt branch. "
            "Run `python -m study sync --complete`."
        )
    return 0


def prompt_nonempty(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Please enter a response.")


def cmd_complete(root: Path, _args: argparse.Namespace) -> int:
    result = evaluation(root)
    if result["passed_cases"] < result["total_cases"]:
        print("The current solution does not pass all cases. Test details:")
        return cmd_test(root, argparse.Namespace())
    print(json.dumps(result, indent=2))
    rating = input(f"Rating [{result['recommended_rating']}]: ").strip().lower()
    rating = rating or result["recommended_rating"]
    if rating not in RATINGS:
        raise RuntimeError("Rating must be Again, Hard, Good, or Easy.")
    minutes_text = input(f"Active minutes [{result['active_minutes']}]: ").strip()
    minutes = int(minutes_text) if minutes_text else result["active_minutes"]
    args = argparse.Namespace(
        rating=rating,
        minutes=minutes,
        approach=prompt_nonempty("Approach"),
        insight=prompt_nonempty("Key invariant or insight"),
        time_complexity=prompt_nonempty("Time complexity"),
        space_complexity=prompt_nonempty("Space complexity"),
        lessons=prompt_nonempty("Mistakes and lessons"),
        hint_effect=prompt_nonempty("Effect of hints"),
        sync=False,
    )
    print("\nFiles will be committed on the public attempt branch, then merged to public main.")
    if input("Type YES to publish and synchronize: ").strip() != "YES":
        print("Completion cancelled; your attempt remains intact.")
        return 1
    args.sync = True
    return cmd_finalize(root, args)


def cmd_sync(root: Path, args: argparse.Namespace) -> int:
    name = branch_name(root)
    if args.complete and name.startswith("attempt/") and not (root / "attempt").exists():
        push_current(root)
        merge_completed_attempt(root, name)
        print("Completed attempt merged and synchronized to main.")
        return 0
    synced = sync_branch(root)
    print(f"Synchronized {synced}.")
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
        print("Next step: press Ctrl+Shift+B in VS Code")
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
            "# In VS Code, press Ctrl+Shift+B",
            "python -m study practice",
            "```",
            "",
            "When finished, tell Codex: I'm finished.",
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
    practice = commands.add_parser(
        "practice", help="start or resume today's highest-priority problem"
    )
    practice.add_argument("--no-sync", action="store_true", help=argparse.SUPPRESS)
    practice.add_argument("--open", action="store_true", help="open the candidate in VS Code")
    today = commands.add_parser("today", help="show today's study queue")
    today.add_argument("--diagnostic", action="store_true", help="offer unreviewed diagnostic work")
    today.add_argument("--include-new", action="store_true", help="offer new work on weekends")
    start = commands.add_parser("start", help="begin one exercise")
    start.add_argument("problem_id")
    start.add_argument("--replace", action="store_true", help="replace an unfinished session")
    commands.add_parser("hint", help="reveal the next progressive hint")
    commands.add_parser("test", help="run cases for the active attempt")
    checkpoint_command = commands.add_parser(
        "checkpoint", help="run cases and save a local checkpoint"
    )
    checkpoint_command.add_argument(
        "--json", action="store_true", help="emit coaching metadata as JSON"
    )
    commands.add_parser("pause", help="pause active time and synchronize the draft")
    evaluate = commands.add_parser("evaluate", help="show completion facts and rating guidance")
    evaluate.add_argument("--json", action="store_true")
    finish = commands.add_parser("finish", help="record a review and close the active attempt")
    finish.add_argument("--rating", required=True, choices=RATINGS)
    finish.add_argument("--minutes", required=True, type=int)
    finish.add_argument(
        "--explained",
        action="store_true",
        help="confirm you explained the approach and time/space complexity",
    )
    finalize = commands.add_parser("finalize", help="publish reflection and finish an attempt")
    finalize.add_argument("--rating", required=True, choices=RATINGS)
    finalize.add_argument("--minutes", type=int)
    finalize.add_argument("--reflection-file")
    finalize.add_argument("--approach")
    finalize.add_argument("--insight")
    finalize.add_argument("--time-complexity")
    finalize.add_argument("--space-complexity")
    finalize.add_argument("--lessons")
    finalize.add_argument("--hint-effect")
    finalize.add_argument("--sync", action="store_true")
    commands.add_parser("complete", help="guided completion fallback")
    sync = commands.add_parser("sync", help="retry GitHub synchronization")
    sync.add_argument("--complete", action="store_true")
    commands.add_parser("status", help="show roadmap and review progress")
    commands.add_parser("reminder", help="render today's GitHub reminder issue")
    return parser


COMMANDS = {
    "doctor": cmd_doctor,
    "practice": cmd_practice,
    "today": cmd_today,
    "start": cmd_start,
    "hint": cmd_hint,
    "test": cmd_test,
    "checkpoint": cmd_checkpoint,
    "pause": cmd_pause,
    "evaluate": cmd_evaluate,
    "finish": cmd_finish,
    "finalize": cmd_finalize,
    "complete": cmd_complete,
    "sync": cmd_sync,
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
    except (KeyError, RuntimeError, GitFlowError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
