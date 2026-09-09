from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from study.core import (
    ASSISTANCE_LEVELS,
    ERROR_CATEGORIES,
    ERROR_CAUSES,
    ERROR_SEVERITIES,
    RATINGS,
    RECALL_QUALITIES,
    active_seconds,
    assistance_level,
    candidate_path,
    display_value,
    find_root,
    focus_boundary_reached,
    git_output,
    load_problems,
    load_roadmap,
    load_session,
    problem_by_id,
    python_version_ok,
    run_solution,
    save_session,
)
from study.gitflow import (
    GitFlowError,
)


def print_problem(problem: dict, prefix: str = "") -> None:
    print(f"{prefix}{problem['id']} - {problem['title']} ({problem['estimated_minutes']} min)")


def print_problem_context(problem: dict) -> None:
    """Show learner-safe problem context without hints, cases, or candidate code."""
    print("\nProblem")
    print(problem["prompt"])
    print(f"\nFunction signature\n{problem['signature']}")
    print("\nConstraints")
    for constraint in problem["constraints"]:
        print(f"- {constraint}")
    for index, example in enumerate(problem["examples"], start=1):
        print(f"\nExample {index}")
        for name, value in example["inputs"].items():
            print(f"{name} = {display_value(value)}")
        print(f"Output: {display_value(example['output'])}")
        if example.get("explanation"):
            print(f"Explanation: {example['explanation']}")


def print_module_map(root: Path) -> None:
    roadmap = load_roadmap(root)
    module = roadmap.get("module_map")
    if not module:
        return
    print("\nModule map")
    print(f"Purpose: {module['purpose']}")
    print(f"Prerequisites: {', '.join(module['prerequisites'])}")
    print(f"Transfer target: {module['transfer_target']}\n")


def open_candidate(root: Path) -> None:
    code = shutil.which("code")
    if code:
        subprocess.run([code, "-r", str(candidate_path(root))], check=False)


def require_reasoning(root: Path) -> dict:
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem. Press Ctrl+Shift+B to start one.")
    if not session.get("initial_reasoning"):
        raise RuntimeError(
            "Record blank-slate reasoning before hints, code checks, or completion. "
            "Use `study note reasoning` after stating the approach, why it fits, invariant, "
            "complexity, and an edge case."
        )
    return session


def focus_message(session: dict) -> str | None:
    if focus_boundary_reached(session):
        return (
            "The 45-minute focus block is complete. Pause for a short break, or explicitly "
            "extend productive work with `study continue --minutes 10`."
        )
    return None


def repair_gate_lines(gate: dict, *, indent: str = "") -> list[str]:
    state = "ready now" if gate["eligible"] else "available next Eastern day"
    return [
        f"{indent}{gate['skill']} / {gate['category']} ({state})",
        f"{indent}Error ID: {gate['event_id']}",
        f"{indent}Prompt: {gate['repair_prompt']}",
        f"{indent}Start with: python -m study repair --error-id {gate['event_id']}",
    ]


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
    problems = load_problems(root)
    problem_count = len(problems)
    valid = bool(problems) and len({p["id"] for p in problems}) == problem_count
    checks.append(("Problem catalog", valid, f"{problem_count} exercises"))

    for label, passed, detail in checks:
        print(f"[{'OK' if passed else '!!'}] {label}: {detail}")
    return 0 if all(passed for _, passed, _ in checks) else 1


def cmd_today(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "today"
    return dispatch(root, args)


def cmd_practice(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "practice"
    return dispatch(root, args)


def cmd_start(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "start"
    return dispatch(root, args)


def cmd_hint(root: Path, _args: argparse.Namespace) -> int:
    from study.commands import dispatch

    _args.command = "hint"
    return dispatch(root, _args)


def cmd_note(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "note"
    return dispatch(root, args)


def test_current(root: Path) -> tuple[dict | None, list]:
    session = load_session(root)
    if not session:
        return None, []
    problem = problem_by_id(root, session["problem_id"])
    return problem, run_solution(candidate_path(root), problem)


def cmd_test(root: Path, _args: argparse.Namespace) -> int:
    from study.commands import dispatch

    _args.command = "test"
    return dispatch(root, _args)


def passed_count(total: int, failures: list) -> int:
    return 0 if any(failure.index == 0 for failure in failures) else total - len(failures)


def checkpoint(root: Path) -> tuple[dict, int, int, list]:
    session = require_reasoning(root)
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
    if session["checkpoint_count"] == 1:
        session["first_checkpoint_passed"] = passed == total
    save_session(root, session)
    return problem, passed, total, failures


def cmd_checkpoint(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "checkpoint"
    return dispatch(root, args)


def cmd_continue(root: Path, args: argparse.Namespace) -> int:
    from study.service import StudyService

    service = StudyService(root)
    with service.lock:
        session = service._session()
        session["budget_minutes"] = min(180, session.get("budget_minutes", 60) + args.minutes)
        service._save(session)
    service.start(synchronize=False)
    print("Session budget extended; the timer is running.")
    return 0


def cmd_repair(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "repair"
    return dispatch(root, args)


def cmd_insights(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "insights"
    return dispatch(root, args)


def cmd_pause(root: Path, _args: argparse.Namespace) -> int:
    from study.commands import dispatch

    _args.command = "pause"
    return dispatch(root, _args)


def rating_recommendation(problem: dict, session: dict, passed: int, total: int) -> tuple[str, str]:
    levels = [item["level"] for item in session.get("assistance_log", [])]
    quality = session.get("initial_reasoning", {}).get("quality", "novel")
    if quality in {"partial", "failed"} or any(x in {"guided", "substantial"} for x in levels):
        return "again", "Missing independent reasoning requires Again."
    return "good", "Independent recall: choose Hard, Good, or Easy according to effort."


def rating_too_high(selected: str, recommended: str) -> bool:
    rank = {rating: index for index, rating in enumerate(RATINGS)}
    return rank[selected] > rank[recommended]


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
        "assistance_level": assistance_level(session),
        "assistance_log": session.get("assistance_log", []),
        "initial_reasoning": session.get("initial_reasoning"),
        "checkpoint_count": int(session.get("checkpoint_count", 0)),
        "active_minutes": max(1, round(active_seconds(session) / 60)),
        "focus_boundary_reached": focus_boundary_reached(session),
        "recommended_rating": rating,
        "rating_rationale": rationale,
    }


def cmd_evaluate(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "evaluate"
    return dispatch(root, args)


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


def render_reflection(
    args: argparse.Namespace,
    problem: dict,
    session: dict,
    recommended_rating: str,
    recommendation_rationale: str,
) -> str:
    reasoning = session["initial_reasoning"]
    assistance = session.get("assistance_log", [])
    assistance_lines = [
        f"- Formal hints invoked: {int(session.get('hints_used', 0))}",
        f"- Highest assistance level: {assistance_level(session)}",
    ]
    assistance_lines.extend(
        f"- {event['level'].title()} ({event['source']}): {event['summary']}"
        for event in assistance
    )
    if not assistance:
        assistance_lines.append("- No conversational assistance was recorded.")
    return (
        f"# {problem['title']}\n\n"
        f"## Approach\n\n"
        f"### Initial reasoning\n\n"
        f"- Approach: {reasoning['approach']}\n"
        f"- Why it fit: {reasoning.get('why', 'Not recorded')}\n"
        f"- Invariant or key belief: {reasoning['invariant']}\n"
        f"- Expected complexity: {reasoning['expected_complexity']}\n"
        f"- Edge case: {reasoning.get('edge_case', 'Not recorded')}\n"
        f"- Recall quality: {reasoning.get('quality', 'novel')}\n\n"
        f"### Final approach\n\n{args.approach.strip()}\n\n"
        f"## Key invariant or insight\n\n{args.insight.strip()}\n\n"
        f"## Complexity\n\n- Time: `{args.time_complexity.strip()}`\n"
        f"- Space: `{args.space_complexity.strip()}`\n\n"
        f"## Mistakes and lessons\n\n{args.lessons.strip()}\n\n"
        f"## Assistance received\n\n{chr(10).join(assistance_lines)}\n\n"
        f"{args.assistance.strip()}\n\n"
        f"## Rating rationale\n\n"
        f"- Enforced maximum rating: {recommended_rating.title()}\n"
        f"- Evidence: {recommendation_rationale}\n\n"
        f"{args.rating_rationale.strip()}\n"
    )


def apply_reflection_file(args: argparse.Namespace) -> argparse.Namespace:
    payload = {}
    if getattr(args, "reflection_file", None):
        payload = json.loads(Path(args.reflection_file).read_text(encoding="utf-8"))
    for field in (
        "approach",
        "insight",
        "time_complexity",
        "space_complexity",
        "lessons",
        "assistance",
        "rating_rationale",
    ):
        value = payload.get(field) or getattr(args, field, None)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Completion needs a non-empty {field!r} reflection field.")
        setattr(args, field, value)
    return args


def cmd_finish(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "finish"
    return dispatch(root, args)


def cmd_finalize(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "finalize"
    return dispatch(root, args)


def prompt_nonempty(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Please enter a response.")


def cmd_complete(root: Path, _args: argparse.Namespace) -> int:
    from study.commands import dispatch

    _args.command = "complete"
    return dispatch(root, _args)


def cmd_sync(root: Path, args: argparse.Namespace) -> int:
    from study.commands import dispatch

    args.command = "sync"
    return dispatch(root, args)


def mastery(root: Path) -> tuple[int, int, bool]:
    from study.policy import topic_progress

    topic = next((t for t in topic_progress(root) if t["id"] == "arrays-hashing"), {})
    return (
        topic.get("retained_core", 0),
        topic.get("core_count", 0),
        topic.get("unseen_transfer_passed", False),
    )


def cmd_status(root: Path, _args: argparse.Namespace) -> int:
    from study.commands import dispatch

    _args.command = "status"
    return dispatch(root, _args)


def reminder_text(root: Path) -> str:
    from study.policy import queue

    result = queue(root, now=datetime.now(UTC))
    lines = ["# Today’s practice", "", result["reason"], "", "## Due reviews", ""]
    lines += [f"- {p['id']}: full implementation remains due." for p in result["due"]]
    if result["repairs"]:
        lines += ["", "## Repair gates", ""]
        for gate in result["repairs"]:
            lines += [
                f"- {gate['skill']}: {'ready' if gate['eligible'] else 'wait 24 hours'}",
                f"  Error ID: `{gate['event_id']}`",
                f"  Apply: {gate['repair_prompt']}",
                f"  Use `study repair --error-id {gate['event_id']} "
                "--application <text> --minutes <n>` or the app.",
            ]
    if result["main"]:
        lines += ["", "## Next activity", "", result["activity"] + ". " + result["reason"]]
    lines += [
        "",
        "Open **Start Study** or run `study app`. Codex uses `study summary`.",
        "Finish locally at any point; use Publish for your reviewed learning artifacts.",
    ]
    return "\n".join(lines) + "\n"


def cmd_reminder(root: Path, _args: argparse.Namespace) -> int:
    print(reminder_text(root), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="study", description="Algorithm learning companion")
    parser.add_argument("--root", type=Path, help="Explicit learning repository")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check local setup")
    app = commands.add_parser("app", help="open the local practice app")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--no-open", action="store_true")
    commands.add_parser("summary", help="JSON session summary for Codex")
    commands.add_parser(
        "coach-context", help="Restricted context for coaching the current activity"
    )
    commands.add_parser("guided", help="Explicitly convert an assessment to guided practice")
    retry = commands.add_parser("retry", help="Save a substantive reasoning retry")
    retry.add_argument("answer")
    advance = commands.add_parser("advance", help="Continue or skip a supporting activity")
    advance.add_argument("--answer", default="")
    advance.add_argument("--skip", action="store_true")
    advance.add_argument("--passed", action="store_true")
    publish = commands.add_parser("publish", help="explicitly publish a saved completion")
    publish.add_argument("session_id")
    commands.add_parser("recover", help="preserve a divergent or orphan draft")
    commands.add_parser("learn-example", help="study a worked solution after an initial attempt")
    commands.add_parser("keep-local", help="defer pending publication")
    save = commands.add_parser("save", help="save candidate without overwriting another editor")
    save.add_argument("--file", required=True)
    save.add_argument("--revision", type=int, required=True)
    save.add_argument("--digest")
    phase = commands.add_parser("phase", help="record the current study phase")
    phase.add_argument(
        "phase",
        choices=("recall", "implementation", "explanation", "repair", "administration", "learning"),
    )
    commands.add_parser("stop", help="stop a running code check")
    practice = commands.add_parser(
        "practice", help="start or resume today's highest-priority problem"
    )
    practice.add_argument("--no-sync", action="store_true", help=argparse.SUPPRESS)
    practice.add_argument("--include-new", action="store_true")
    practice.add_argument("--minutes", type=int)
    practice.add_argument("--open", action="store_true", help="open the candidate in VS Code")
    today = commands.add_parser("today", help="show today's study queue")
    today.add_argument("--diagnostic", action="store_true", help="offer unreviewed diagnostic work")
    today.add_argument("--include-new", action="store_true", help="offer new work on weekends")
    start = commands.add_parser("start", help="begin one exercise")
    start.add_argument("problem_id")
    start.add_argument(
        "--include-new", action="store_true", help="allow unseen content on weekends"
    )
    start.add_argument(
        "--activity", choices=("learn", "recall", "implement", "transfer"), default="implement"
    )
    start.add_argument("--minutes", type=int)
    start.add_argument("--replace", action="store_true", help="replace an unfinished session")
    note = commands.add_parser("note", help="record learning evidence for the active attempt")
    note_subcommands = note.add_subparsers(dest="note_kind", required=True)
    reasoning = note_subcommands.add_parser("reasoning", help="record the initial reasoning")
    reasoning.add_argument("--approach", required=True)
    reasoning.add_argument("--invariant")
    reasoning.add_argument("--complexity")
    reasoning.add_argument("--why", default=None)
    reasoning.add_argument("--edge-case", default=None)
    reasoning.add_argument("--quality", choices=RECALL_QUALITIES, default="novel")
    reasoning.add_argument("--open", action="store_true")
    reasoning.add_argument("--json", action="store_true")
    assistance = note_subcommands.add_parser("assistance", help="record coaching assistance")
    assistance.add_argument("--missing-recall", action="store_true")
    assistance.add_argument("--level", required=True, choices=ASSISTANCE_LEVELS[1:])
    assistance.add_argument("--summary", required=True)
    assistance.add_argument("--json", action="store_true")
    error = note_subcommands.add_parser("error", help="record a reusable learning error")
    error.add_argument("--skill", required=True)
    error.add_argument("--category", required=True, choices=ERROR_CATEGORIES)
    error.add_argument("--cause", required=True, choices=ERROR_CAUSES)
    error.add_argument("--severity", required=True, choices=ERROR_SEVERITIES)
    error.add_argument("--summary", required=True)
    error.add_argument("--trigger", required=True)
    error.add_argument("--corrected-rule", required=True)
    error.add_argument("--repair-prompt", required=True)
    hint = commands.add_parser("hint", help="reveal the next progressive hint")
    hint.add_argument("--retried", action="store_true", help="confirm a reasoning retry")
    commands.add_parser("test", help="run cases for the active attempt")
    checkpoint_command = commands.add_parser(
        "checkpoint", help="run cases and save a local checkpoint"
    )
    checkpoint_command.add_argument(
        "--json", action="store_true", help="emit coaching metadata as JSON"
    )
    commands.add_parser("pause", help="pause active time and synchronize the draft")
    continuation = commands.add_parser("continue", help="explicitly extend focused practice")
    continuation.add_argument("--minutes", required=True, type=int)
    repair = commands.add_parser("repair", help="submit a delayed repair-gate response")
    repair.add_argument("--error-id", required=True)
    repair.add_argument("--trigger")
    repair.add_argument("--corrected-rule")
    repair.add_argument("--why-failed")
    repair.add_argument("--application", required=True)
    repair.add_argument("--minutes", type=float, required=True)
    repair.add_argument("--passed", action="store_true")
    repair.add_argument("--assistance", choices=ASSISTANCE_LEVELS, default="none")
    insights = commands.add_parser("insights", help="show learning ROI and recurring weaknesses")
    insights.add_argument("--json", action="store_true")
    evaluate = commands.add_parser("evaluate", help="show completion facts and rating guidance")
    evaluate.add_argument("--json", action="store_true")
    finish = commands.add_parser("finish", help="record a review and close the active attempt")
    finish.add_argument("--rating", required=True, choices=RATINGS)
    finish.add_argument("--minutes", type=float)
    finish.add_argument("--takeaway")
    finish.add_argument("--constraints-met", action="store_true")
    finish.add_argument("--stopped", action="store_true")
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
    finalize.add_argument("--assistance")
    finalize.add_argument("--rating-rationale")
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
    "note": cmd_note,
    "hint": cmd_hint,
    "test": cmd_test,
    "checkpoint": cmd_checkpoint,
    "pause": cmd_pause,
    "continue": cmd_continue,
    "repair": cmd_repair,
    "insights": cmd_insights,
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
    if getattr(args, "minutes", None) is not None and args.minutes <= 0:
        print("--minutes must be positive", file=sys.stderr)
        return 2
    try:
        root = find_root(args.root)
        from study.commands import dispatch

        result = dispatch(root, args)
        return result if result is not None else COMMANDS[args.command](root, args)
    except (KeyError, RuntimeError, ValueError, GitFlowError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
