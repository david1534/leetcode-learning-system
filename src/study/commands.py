"""Human and JSON adapters to the shared service; no second session state machine."""

from __future__ import annotations

import json
from pathlib import Path

from study import core, policy
from study.service import StudyService


def output(value, as_json=False):
    if as_json:
        print(json.dumps(value, indent=2))
    else:
        print(value if isinstance(value, str) else json.dumps(value, indent=2))


def dispatch(root: Path, args) -> int | None:
    command = args.command
    if command == "app":
        from study.app import launch

        launch(root, args.port, not args.no_open)
        return 0
    service = StudyService(root)
    if command in {"coach-context", "guided", "retry", "advance"}:
        if command == "coach-context":
            result = service.coach_context()
        elif command == "guided":
            result = service.convert_to_practice()
        elif command == "retry":
            result = service.record_retry(args.answer)
        else:
            result = service.practice_advance(
                answer=args.answer, skip=args.skip, passed=args.passed
            )
        output(result, True)
        return 0
    if command in {"practice", "start"}:
        result = (
            service.practice_start(
                include_new=getattr(args, "include_new", False),
                minutes=getattr(args, "minutes", None) or 60,
                synchronize=not getattr(args, "no_sync", False),
            )
            if command == "practice"
            else service.start(
                problem_id=getattr(args, "problem_id", None),
                activity=getattr(args, "activity", "implement"),
                include_new=getattr(args, "include_new", False),
                minutes=getattr(args, "minutes", None),
                synchronize=not getattr(args, "no_sync", False),
            )
        )
        session = result.get("session")
        if session:
            print(f"Resuming / started {session['activity']}: {session['problem']['title']}")
            from study.cli import print_problem_context

            print_problem_context(session["problem"])
            print(
                "Record a compact approach, why it fits, and one correctness "
                "condition or edge case."
            )
            if getattr(args, "open", False) and session.get("initial_reasoning"):
                from study.cli import open_candidate

                open_candidate(root)
        else:
            print(result.get("message", "No activity selected."))
        print(result["sync"]["message"])
        for gate in service.plan()["repairs"]:
            print(f"Repair: {gate['skill']}. Error ID: {gate['event_id']}")
            print(f"study repair --error-id {gate['event_id']} --application <text> --minutes <n>")
        return 0
    if command == "summary":
        output(service.state(), True)
        return 0
    if command == "save":
        output(
            service.save_code(
                Path(args.file).read_text(encoding="utf-8"), args.revision, args.digest
            ),
            True,
        )
        return 0
    if command == "phase":
        output(service.phase(args.phase))
        return 0
    if command == "stop":
        output(service.stop_check())
        return 0
    if command == "note":
        if args.note_kind == "reasoning":
            result = service.reasoning(
                args.approach,
                args.quality,
                why=args.why,
                invariant=args.invariant,
                complexity=args.complexity,
                edge_case=args.edge_case,
            )
            if args.open:
                from study.cli import open_candidate

                open_candidate(root)
            output(result["session"]["initial_reasoning"], args.json)
        elif args.note_kind == "assistance":
            output(
                service.assistance(
                    args.level, args.summary, supplied_missing_recall=args.missing_recall
                ),
                args.json,
            )
        else:
            with service.lock:
                service._session()
                path = core.record_learning_error(
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
                session = service._session()
                service._save(session)
                print(f"Learning error recorded in {path.relative_to(root)}")
        return 0
    if command == "hint":
        result = service.hint(retried=getattr(args, "retried", False))
        print("Hint: " + result.get("hint", result.get("message", "")))
        return 0
    if command in {"test", "checkpoint"}:
        result = service.check()
        output(result, getattr(args, "json", False))
        return (0 if result["all_passed"] else 1) if command == "test" else 0
    if command == "pause":
        print(service.practice_pause()["sync"]["message"])
        return 0
    if command == "evaluate":
        output(service.evaluate(), args.json)
        return 0
    if command in {"finish", "finalize", "complete"}:
        state = service.state()
        session = state["session"]
        if not session:
            raise RuntimeError("No active problem to finish.")
        if session["activity"] in {"implement", "transfer"}:
            service.check()
        facts = service.evaluate()
        if command == "complete":
            prior_phase = session["phase"]
            service.phase("administration")
            rating = (
                input(f"Recall rating [{facts['recommended_rating']}]: ").strip().lower()
                or facts["recommended_rating"]
            )
            text = input(f"Minutes [{facts['active_minutes']:.1f}]: ").strip()
            minutes = float(text) if text else None
            takeaway = input("What would you recognize or do differently next time? ").strip()
            explained = input("Did you explain why it works? [y/N] ").lower() == "y"
            constraints = input("Did you check time/space constraints? [y/N] ").lower() == "y"
            print("The candidate, learning evidence, and reflection will be public on GitHub.")
            if facts.get("unpublished_count"):
                print(f"Includes {facts['unpublished_count']} earlier locally saved sessions.")
            choice = input("Type YES to publish, LOCAL to finish locally, or Enter to cancel: ")
            if choice not in {"YES", "LOCAL"}:
                service.phase(prior_phase)
                print("Completion cancelled; your work is preserved.")
                return 1
            # The explicit destination is collected once, after the concrete summary.
            # Re-read below from the captured choice rather than inferring publication.
            publish = choice == "YES"
        else:
            rating = args.rating
            minutes = args.minutes
            payload = {}
            if getattr(args, "reflection_file", None):
                payload = json.loads(Path(args.reflection_file).read_text(encoding="utf-8"))
            takeaway = (
                getattr(args, "takeaway", None)
                or payload.get("lessons")
                or getattr(args, "lessons", None)
                or "No additional takeaway recorded."
            )
            explained = (
                getattr(args, "explained", False)
                or bool(payload.get("insight"))
                or bool(getattr(args, "insight", None))
            )
            constraints = getattr(args, "constraints_met", False) or bool(
                (payload.get("time_complexity") or getattr(args, "time_complexity", None))
                and (payload.get("space_complexity") or getattr(args, "space_complexity", None))
            )
            publish = command == "finalize" and getattr(args, "sync", False)
        result = service.practice_finish(
            session["session_id"],
            rating,
            takeaway,
            explained,
            constraints,
            minutes,
            publish,
            stopped=(session["activity"] in {"implement", "transfer"} and not facts["tests_passed"])
            or getattr(args, "stopped", False),
        )
        output(result)
        return 0
    if command == "recover":
        output(service.recover())
        return 0
    if command == "learn-example":
        output(service.worked_example())
        return 0
    if command == "publish":
        output(service.publish(args.session_id))
        return 0
    if command == "keep-local":
        output(service.keep_local())
        return 0
    if command == "sync":
        output(service.sync())
        return 0
    if command == "today":
        result = service.plan(args.include_new)
        output(result)
        return 0
    if command in {"status", "insights"}:
        result = policy.metrics(root)
        output(result, getattr(args, "json", False))
        return 0
    if command == "repair":
        result = service.repair(
            args.error_id,
            args.application,
            args.passed,
            args.assistance,
            explanation=args.why_failed or "",
            minutes=args.minutes,
        )
        output(result)
        return 0
    return None
