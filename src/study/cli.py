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
    ASSISTANCE_LEVELS,
    EASTERN,
    ERROR_CATEGORIES,
    ERROR_CAUSES,
    ERROR_SEVERITIES,
    RATINGS,
    RECALL_QUALITIES,
    active_seconds,
    assistance_level,
    candidate_path,
    cleanup_legacy_attempt,
    current_eastern_date,
    due_problems,
    effective_events,
    extend_focus,
    find_root,
    focus_boundary_reached,
    format_failure,
    git_output,
    latest_by_problem,
    learning_insights,
    load_problems,
    load_roadmap,
    load_session,
    migrate_legacy_attempt,
    next_new_problem,
    open_repair_gates,
    pause_timer,
    problem_by_id,
    python_version_ok,
    rebuild_cards,
    record_assistance,
    record_initial_reasoning,
    record_learning_error,
    record_repair,
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
        if message := focus_message(session):
            print(f"        {message}")
        return 0

    due = due_problems(root, now)
    if due:
        print("\nDue reviews:")
        for problem in due:
            print_problem(problem, "  - ")
    else:
        print("\nNo reviews are due.")

    gates = open_repair_gates(root, now)
    if gates:
        print("\nRepair gates:")
        for gate in gates:
            lines = repair_gate_lines(gate, indent="    ")
            print(f"  - {lines[0].strip()}")
            print("\n".join(lines[1:]))

    local_now = now.astimezone(EASTERN)
    if local_now.weekday() < 5 or args.include_new:
        new_problem = None if gates else next_new_problem(root, include_diagnostic=args.diagnostic)
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
        if session.get("initial_reasoning"):
            print("Open attempt/current.py and continue your solution.")
        else:
            print("First reconstruct the approach, why, invariant, complexity, and one edge case.")
        if args.open and session.get("initial_reasoning"):
            open_candidate(root)
        return 0

    due = due_problems(root)
    gates = open_repair_gates(root)
    eligible_gates = [gate for gate in gates if gate["eligible"]]
    if not due and eligible_gates:
        gate = eligible_gates[0]
        print("Repair required before new material:")
        print("\n".join(repair_gate_lines(gate)))
        return 0
    if not due and gates:
        print("A repair gate becomes eligible next Eastern day. Due reviews remain available.")
        print("\n".join(repair_gate_lines(gates[0])))
        return 0
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
    if not due and not effective_events(root):
        print_module_map(root)
    print(f"Candidate prepared at {path.relative_to(root)}, but keep it closed for initial recall.")
    print("State the approach, why it fits, invariant, complexity, and one edge case first.")
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
    session = require_reasoning(root)
    problem = problem_by_id(root, session["problem_id"])
    used = session["hints_used"]
    if used and int(session.get("checkpoint_count", 0)) <= int(
        session.get("checkpoint_count_at_last_hint", -1)
    ):
        print("Retry and checkpoint your revised solution before revealing another hint.")
        return 2
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
    session["checkpoint_count_at_last_hint"] = int(session.get("checkpoint_count", 0))
    save_session(root, session)
    level = "guided" if used == 0 else "substantial"
    record_assistance(root, level, problem["hints"][used], source="formal_hint")
    return 0


def cmd_note(root: Path, args: argparse.Namespace) -> int:
    if args.note_kind == "reasoning":
        note = record_initial_reasoning(
            root,
            args.approach,
            args.invariant,
            args.complexity,
            args.why,
            args.edge_case,
            args.quality,
        )
        if args.open:
            open_candidate(root)
        print(json.dumps(note, indent=2) if args.json else "Initial reasoning recorded.")
        return 0
    if args.note_kind == "assistance":
        event = record_assistance(root, args.level, args.summary)
        print(json.dumps(event, indent=2) if args.json else f"{args.level.title()} help recorded.")
        return 0
    path = record_learning_error(
        root,
        args.skill,
        args.category,
        args.cause,
        args.severity,
        args.summary,
        args.trigger,
        args.corrected_rule,
        args.repair_prompt,
    )
    print(f"Learning error recorded in {path.relative_to(root)}")
    return 0


def test_current(root: Path) -> tuple[dict | None, list]:
    session = load_session(root)
    if not session:
        return None, []
    problem = problem_by_id(root, session["problem_id"])
    return problem, run_solution(candidate_path(root), problem)


def cmd_test(root: Path, _args: argparse.Namespace) -> int:
    require_reasoning(root)
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


def cmd_continue(root: Path, args: argparse.Namespace) -> int:
    session = extend_focus(root, args.minutes)
    total = 45 + sum(int(item["minutes"]) for item in session["focus_extensions"])
    print(f"Focus block explicitly extended to {total} active minutes.")
    return 0


def cmd_repair(root: Path, args: argparse.Namespace) -> int:
    path = record_repair(
        root,
        args.error_id,
        args.trigger,
        args.corrected_rule,
        args.why_failed,
        args.application,
        args.passed,
        args.assistance,
    )
    event = json.loads(path.read_text(encoding="utf-8"))
    result = "cleared" if event["passed"] else "remains open"
    relative = path.relative_to(root).as_posix()
    if (root / ".git").exists():
        commit_paths(root, f"study: record repair {event['skill']}", [relative])
        push_current(root)
        suffix = " and synchronized"
    else:
        suffix = ""
    print(f"Repair {result}; evidence recorded{suffix} in {relative}")
    return 0


def cmd_insights(root: Path, args: argparse.Namespace) -> int:
    result = learning_insights(root)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print("Learning ROI")
    def percentage(value: float | None) -> str:
        return "not yet measured" if value is None else f"{value:.0%}"

    print(f"Independent solutions: {percentage(result['independent_solution_rate'])}")
    print(f"Delayed recall success: {result['delayed_recall_success_rate']:.0%}")
    print(f"First-checkpoint passes: {percentage(result['first_checkpoint_pass_rate'])}")
    print(f"Assistance rate: {percentage(result['assistance_rate'])}")
    print(f"Hint rate: {percentage(result['hint_rate'])}")
    ratio = result["median_time_vs_estimate"]
    ratio_text = "not yet measured" if ratio is None else f"{ratio:.2f}x"
    print(f"Median time vs estimate: {ratio_text}")
    print(f"Transfer success: {percentage(result['transfer_success_rate'])}")
    print(f"Active hours recorded: {result['active_hours']}")
    print(f"Open repair gates: {result['open_repair_gates']}")
    for gate in open_repair_gates(root):
        print("\n".join(repair_gate_lines(gate, indent="  ")))
    if result["errors_by_category"]:
        print("Errors by category:")
        for category, count in result["errors_by_category"].items():
            print(f"  - {category}: {count}")
    if result["recurring_errors"]:
        print("Recurring errors:")
        for label, count in result["recurring_errors"].items():
            print(f"  - {label}: {count}")
    return 0


def cmd_pause(root: Path, _args: argparse.Namespace) -> int:
    session = pause_timer(root)
    problem = problem_by_id(root, session["problem_id"])
    paths = ["attempt", *session.get("learning_event_paths", [])]
    commit_paths(root, f"study(draft): pause {problem['id']}", paths)
    push_current(root)
    print(f"Paused and synchronized {problem['title']}.")
    return 0


def rating_recommendation(problem: dict, session: dict, passed: int, total: int) -> tuple[str, str]:
    if passed < total:
        return "again", "The solution does not pass all cases yet."
    level = assistance_level(session)
    checkpoints = int(session.get("checkpoint_count", 0))
    minutes = max(1, round(active_seconds(session) / 60))
    recall = session.get("initial_reasoning", {}).get("quality", "novel")
    if recall == "failed":
        return "again", "The core approach could not be reconstructed before coding."
    if level == "substantial":
        return "again", "It passed, but substantial help supplied the core approach or invariant."
    if level == "guided":
        return "hard", "It passed with guided algorithmic help or targeted debugging."
    if recall == "partial":
        return "hard", "Initial retrieval was partial, even though the final solution passed."
    if checkpoints <= 1 and minutes <= int(problem["estimated_minutes"]):
        if level == "minor":
            return "easy", "It passed on the first checkpoint with only minor clarification."
        return "easy", "It passed on the first checkpoint, independently, within the estimate."
    qualifier = " with only minor clarification" if level == "minor" else " independently"
    return "good", f"It passed{qualifier}; multiple checkpoints or extra time were used."


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
    if args.reflection_file:
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
    if passed and not session.get("initial_reasoning"):
        print("Completion requires recorded initial reasoning.")
        return 2
    recommended, rationale = rating_recommendation(
        problem, session, len(problem["cases"]) - len(failures), len(problem["cases"])
    )
    if rating_too_high(args.rating, recommended):
        print(f"Evidence permits at most {recommended.title()}: {rationale}")
        return 2

    review_path = record_review(
        root,
        problem,
        args.rating,
        args.minutes,
        passed,
        session["hints_used"],
        args.explained,
        assistance_level(session),
        len(session.get("assistance_log", [])),
        session["initial_reasoning"].get("quality", "novel"),
        bool(session.get("first_checkpoint_passed", False)),
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
    if not session.get("initial_reasoning"):
        raise RuntimeError("Completion requires recorded initial reasoning.")
    recommended, rationale = rating_recommendation(
        problem, session, len(problem["cases"]), len(problem["cases"])
    )
    if rating_too_high(args.rating, recommended):
        raise RuntimeError(
            f"Evidence permits at most {recommended.title()}: {rationale}"
        )

    minutes = args.minutes or max(1, round(active_seconds(session) / 60))
    reflection = render_reflection(args, problem, session, recommended, rationale)
    candidate_text = candidate_path(root).read_text(encoding="utf-8")
    unsafe = public_content_errors(reflection + "\n" + candidate_text)
    if unsafe:
        raise RuntimeError(f"Reflection contains public-content risks: {', '.join(unsafe)}")

    name = branch_name(root)
    if not name.startswith("attempt/"):
        raise GitFlowError("Completion must run on an attempt branch.")
    allowed_existing = set(session.get("learning_event_paths", []))
    unrelated = tracked_changes(root, exclude_attempt=True)
    extra = [path for path in unrelated if path not in allowed_existing]
    if extra:
        raise GitFlowError(f"Unrelated tracked changes block completion: {', '.join(extra)}")

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
        assistance_level(session),
        len(session.get("assistance_log", [])),
        session["initial_reasoning"].get("quality", "novel"),
        bool(session.get("first_checkpoint_passed", False)),
    )
    shutil.rmtree(root / "attempt")
    paths = [
        "attempt",
        destination.relative_to(root).as_posix(),
        reflection_file.relative_to(root).as_posix(),
        review_path.relative_to(root).as_posix(),
        *session.get("learning_event_paths", []),
    ]
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
    session = load_session(root)
    assert session is not None
    if not session.get("initial_reasoning"):
        record_initial_reasoning(
            root,
            prompt_nonempty("Initial approach before coaching"),
            prompt_nonempty("Initial invariant or key belief"),
            prompt_nonempty("Initially expected complexity"),
            prompt_nonempty("Why this approach fits"),
            prompt_nonempty("Important edge case"),
            "novel" if session.get("attempt_kind") == "new" else "partial",
        )
        result = evaluation(root)
    print(json.dumps(result, indent=2))
    rating = input(f"Rating [{result['recommended_rating']}]: ").strip().lower()
    rating = rating or result["recommended_rating"]
    if rating not in RATINGS:
        raise RuntimeError("Rating must be Again, Hard, Good, or Easy.")
    if rating_too_high(rating, result["recommended_rating"]):
        raise RuntimeError(
            f"Evidence permits at most {result['recommended_rating'].title()}: "
            f"{result['rating_rationale']}"
        )
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
        assistance=prompt_nonempty("Assistance received"),
        rating_rationale=prompt_nonempty("Rating rationale"),
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
    events = effective_events(root)
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
    transfer_passed = all(p["id"] in passing for p in transfer) and not open_repair_gates(root)
    return mastered_core, len(core), transfer_passed


def cmd_status(root: Path, _args: argparse.Namespace) -> int:
    events = effective_events(root)
    cards = rebuild_cards(root)
    latest = latest_by_problem(root)
    mastered, core_count, transfer = mastery(root)
    print("Foundations / Arrays & Hashing")
    print(f"Core durable reviews: {mastered}/{core_count}")
    print(f"Transfer exercise passed: {'yes' if transfer else 'no'}")
    print(f"Total review events: {len(events)}")
    print(f"Open repair gates: {len(open_repair_gates(root))}")
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
    gates = open_repair_gates(root)
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

    if gates:
        lines.extend(["", "## Repair gates", ""])
        for gate in gates:
            state = "ready now" if gate["eligible"] else "available next Eastern day"
            lines.extend(
                [
                    f"- **{gate['skill']} / {gate['category']}** ({state})",
                    f"  - Error ID: `{gate['event_id']}`",
                    f"  - Prompt: {gate['repair_prompt']}",
                    f"  - Start with: `python -m study repair --error-id {gate['event_id']}`",
                ]
            )

    local_now = datetime.now(EASTERN)
    new_problem = next_new_problem(root)
    if local_now.weekday() < 5 and new_problem and not gates:
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
    note = commands.add_parser("note", help="record learning evidence for the active attempt")
    note_subcommands = note.add_subparsers(dest="note_kind", required=True)
    reasoning = note_subcommands.add_parser("reasoning", help="record the initial reasoning")
    reasoning.add_argument("--approach", required=True)
    reasoning.add_argument("--invariant", required=True)
    reasoning.add_argument("--complexity", required=True)
    reasoning.add_argument("--why", default="Why the selected pattern fits the constraints.")
    reasoning.add_argument("--edge-case", default="An important boundary or duplicate case.")
    reasoning.add_argument("--quality", choices=RECALL_QUALITIES, default="novel")
    reasoning.add_argument("--open", action="store_true")
    reasoning.add_argument("--json", action="store_true")
    assistance = note_subcommands.add_parser("assistance", help="record coaching assistance")
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
    commands.add_parser("hint", help="reveal the next progressive hint")
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
    repair.add_argument("--trigger", required=True)
    repair.add_argument("--corrected-rule", required=True)
    repair.add_argument("--why-failed", required=True)
    repair.add_argument("--application", required=True)
    repair.add_argument("--passed", action="store_true")
    repair.add_argument("--assistance", choices=ASSISTANCE_LEVELS, default="none")
    insights = commands.add_parser("insights", help="show learning ROI and recurring weaknesses")
    insights.add_argument("--json", action="store_true")
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
    if getattr(args, "minutes", 1) <= 0:
        print("--minutes must be positive", file=sys.stderr)
        return 2
    try:
        root = find_root()
        return COMMANDS[args.command](root, args)
    except (KeyError, RuntimeError, GitFlowError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
