"""Shared, deterministic learning policy for the CLI, app, and reminders."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path

from study import core

DEFAULTS = {
    "session_minutes": 60,
    "break_minutes": 45,
    "main_minutes": 40,
    "transfer_every": 5,
    "retained_spacing_days": 7,
    "new_on_weekends": False,
}
ALIASES = {
    "hashmap-bucket-initialization": "hashmap-bucket-lifecycle",
    "hashmap-bucket-construction": "hashmap-bucket-lifecycle",
    "hashmap-bucket-preservation": "hashmap-bucket-lifecycle",
    "frequency-vector": "frequency-signature",
}


def skill_id(value: str) -> str:
    value = "-".join(value.lower().replace("_", "-").split())
    return ALIASES.get(value, value)


def settings(root: Path) -> dict:
    return {**DEFAULTS, **core.load_roadmap(root).get("settings", {})}


def implementation_events(root: Path) -> list[dict]:
    return [
        e
        for e in core.effective_events(root)
        if e.get("activity", "implement") in {"implement", "transfer"}
    ]


def independent(event: dict) -> bool:
    if event.get("schema_version", 1) < 4:
        return core.is_independent_successful_review(event)
    return (
        event.get("activity") in {"implement", "transfer"}
        and event.get("assessment", {}).get("status")
        not in {"ended_for_help", "stopped", "incomplete"}
        and event.get("recall_outcome") == "success"
        and event.get("rating") in {"hard", "good", "easy"}
        and event.get("assistance_level") in {"none", "minor"}
        and event.get("tests_passed") is True
        and event.get("explained") is True
        and event.get("assessment", {}).get("constraints_met") is True
    )


def latest_independent(root: Path) -> set[str]:
    latest = {}
    for event in implementation_events(root):
        latest[event["problem_id"]] = event
    return {pid for pid, e in latest.items() if independent(e)}


def exposures(root: Path) -> set[str]:
    result = {e["problem_id"] for e in core.effective_events(root)}
    result.update(
        e["problem_id"] for e in core.load_learning_events(root) if e["event_type"] == "exposure"
    )
    session = core.load_session(root)
    if session:
        result.add(session["problem_id"])
    return result


def relevant_gates(root: Path, problem: dict, now: datetime | None = None) -> list[dict]:
    skills = {skill_id(s) for s in problem.get("skill_ids", problem.get("skills", []))}
    return [gate for gate in core.open_repair_gates(root, now) if skill_id(gate["skill"]) in skills]


def eligible(root: Path, problem: dict, now: datetime | None = None) -> bool:
    return set(problem.get("prerequisites", [])) <= latest_independent(root) and not relevant_gates(
        root, problem, now
    )


def queue(
    root: Path, now: datetime | None = None, include_new: bool = False, minutes: int | None = None
) -> dict:
    now = now or datetime.now(UTC)
    config = settings(root)
    budget = minutes or config["session_minutes"]
    seen = exposures(root)
    catalog = core.load_problems(root)
    due = core.due_problems(root, now)
    events = [e for e in implementation_events(root) if e.get("schema_version", 1) >= 4]
    completed = len(events)
    guided = practice_sessions(root)
    if guided:
        completed = len(guided)
    weekend = now.astimezone(core.EASTERN).weekday() >= 5
    allow_new = include_new or config["new_on_weekends"] or not weekend
    available = [p for p in catalog if eligible(root, p, now)]
    reviewable = [p for p in due if eligible(root, p, now)]
    new = [p for p in available if p["kind"] == "core" and p["id"] not in seen]
    transfer = [p for p in available if p["kind"] == "transfer" and p["id"] not in seen]
    fit = max(5, budget - min(20, budget // 3))
    new = [p for p in new if p["estimated_minutes"] <= fit]
    transfer = [p for p in transfer if p["estimated_minutes"] <= fit]
    chosen, reason, activity = None, "No eligible activity fits this session.", "implement"
    last_transfer = next(
        (
            i + 1
            for i, e in reversed(list(enumerate(guided)))
            if e.get("main_activity") == "transfer"
        ),
        0,
    )
    transfer_due = (
        (completed - last_transfer + 1) >= config["transfer_every"]
        if guided
        else (completed + 1) % config["transfer_every"] == 0
    )
    review_streak = 0
    for completed_parent in reversed(guided):
        if completed_parent.get("main_activity") == "transfer":
            continue
        if completed_parent.get("main_was_new"):
            break
        review_streak += 1
    new_turn = review_streak >= 2 if guided else completed % 3 == 2
    if transfer and allow_new and transfer_due:
        chosen, reason, activity = (
            transfer[0],
            "An unfamiliar assessment checks transfer.",
            "transfer",
        )
    elif new and allow_new and (not reviewable or new_turn):
        chosen, reason = new[0], "Protected time for new material."
    elif reviewable:
        # Prefer a different topic from the preceding main activity when both are due.
        last_topic = events[-1]["topic"] if events else None
        fitting = [p for p in reviewable if p["estimated_minutes"] <= fit]
        fitting.sort(key=lambda p: p["topic"] == last_topic)
        if fitting:
            chosen, reason = fitting[0], "A due implementation review protects retention."
        else:
            chosen, reason, activity = (
                reviewable[0],
                "Short recall; full implementation remains due.",
                "recall",
            )
    elif new and not allow_new:
        reason = "Weekend review day. Enable new material to override."
    gates = core.open_repair_gates(root, now)
    short = [p for p in reviewable if chosen is None or p["id"] != chosen["id"]][:2]
    return {
        "minutes": budget,
        "main": chosen,
        "activity": activity,
        "reason": reason,
        "due": due,
        "postponed": [p for p in due if not chosen or p["id"] != chosen["id"]],
        "short_recall": short,
        "repairs": gates,
        "support": [
            p
            for p in catalog
            if p["kind"] in {"worked", "faded", "warmup"} and eligible(root, p, now)
        ],
        "completed_sessions": completed,
        "weekend": weekend,
    }


def practice_sessions(root: Path) -> list[dict]:
    return sorted(
        (
            json.loads(p.read_text(encoding="utf-8"))
            for p in (root / "progress/practice-sessions").glob("*.json")
        ),
        key=lambda e: e["completed_at"],
    )


def topic_progress(root: Path) -> list[dict]:
    catalog = core.load_problems(root)
    events = implementation_events(root)
    current = latest_independent(root)
    config = settings(root)
    modules = core.load_roadmap(root).get("modules") or [
        {
            "id": t,
            "title": t,
            "anchors": [p["id"] for p in catalog if p["topic"] == t and p["kind"] == "core"],
        }
        for t in dict.fromkeys(p["topic"] for p in catalog if p["topic"] != "diagnostic")
    ]
    result = []
    for module in modules:
        topic = module["id"]
        core_problems = [p for p in catalog if p["topic"] == topic and p["kind"] == "core"]
        retained = []
        for p in core_problems:
            days = [
                datetime.fromisoformat(e["reviewed_at"])
                for e in events
                if e["problem_id"] == p["id"] and independent(e)
            ]
            if (
                p["id"] in current
                and days
                and max(days) - min(days) >= timedelta(days=config["retained_spacing_days"])
            ):
                retained.append(p["id"])
        transfer = any(
            e.get("activity") == "transfer"
            and e.get("unseen") is True
            and e["topic"] == topic
            and independent(e)
            for e in events
        )
        topic_skills = {
            skill_id(s) for p in core_problems for s in p.get("skill_ids", p.get("skills", []))
        }
        gates = [g for g in core.open_repair_gates(root) if skill_id(g["skill"]) in topic_skills]
        ready = bool(module["anchors"]) and set(module["anchors"]) <= current and not gates
        result.append(
            {
                **module,
                "ready": ready,
                "retained_core": len(retained),
                "core_count": len(core_problems),
                "unseen_transfer_passed": transfer,
                "retained": bool(core_problems)
                and len(retained) == len(core_problems)
                and transfer
                and not gates,
            }
        )
    available = {m["id"] for m in result}
    for stage in core.load_roadmap(root).get("stages", []):
        for topic in stage["topics"]:
            if topic not in available and topic != "diagnostic":
                result.append(
                    {
                        "id": topic,
                        "title": topic.replace("-", " ").title(),
                        "status": "planned",
                        "ready": False,
                        "retained": False,
                    }
                )
    return result


def metrics(root: Path) -> dict:
    old = core.learning_insights(root)
    modern = [e for e in core.effective_events(root) if e.get("schema_version", 1) >= 4]
    attempts = [e for e in modern if e.get("activity") in {"implement", "transfer"}]
    previous = {}
    delayed = []
    for event in core.effective_events(root):
        when = datetime.fromisoformat(event["reviewed_at"])
        prior = previous.get(event["problem_id"])
        if event in attempts and prior and when - prior >= timedelta(hours=24):
            delayed.append(event)
        previous[event["problem_id"]] = when
    unseen = [e for e in attempts if e.get("unseen") and e.get("activity") == "transfer"]

    def rate(items):
        passed = sum(independent(e) for e in items)
        return {
            "passed": passed,
            "total": len(items),
            "rate": passed / len(items) if items else None,
        }

    time_by_phase = {}
    timed = [
        *modern,
        *(
            e
            for e in core.load_learning_events(root)
            if e["event_type"] == "repair" and "timing" in e
        ),
    ]
    for e in timed:
        for phase, seconds in e.get("timing", {}).items():
            time_by_phase[phase] = time_by_phase.get(phase, 0) + seconds
    admin = [
        e["timing"]["administration"] / 60
        for e in attempts[:12]
        if "administration" in e.get("timing", {})
    ]
    assistance = {
        level: sum(e.get("assistance_level") == level for e in attempts)
        for level in core.ASSISTANCE_LEVELS
    }
    guided = practice_sessions(root)
    cohort = guided[:12]
    child_ids = {sid for parent in guided for sid in parent.get("attempt_ids", [])}
    parent_repairs = {Path(p).stem for parent in guided for p in parent.get("repair_paths", [])}
    remaining = [
        e for e in timed if e["event_id"] not in child_ids and e["event_id"] not in parent_repairs
    ]
    time_by_phase = {}
    for event in [*remaining, *guided]:
        for phase, seconds in event.get("timing", {}).items():
            time_by_phase[phase] = time_by_phase.get(phase, 0) + seconds
    cohort_ids = {sid for p in cohort for sid in p.get("attempt_ids", [])}
    cohort_delayed = [e for e in delayed if e["event_id"] in cohort_ids]
    cohort_unseen = [e for e in unseen if e["event_id"] in cohort_ids]
    latency = [
        seconds for p in cohort for seconds in p.get("coaching", {}).get("latency_seconds", [])
    ]
    if cohort:
        admin = [p["timing"].get("administration", 0) / 60 for p in cohort]
    return {
        "workflow_version": 3,
        "guided_sessions": len(guided),
        "cohort": {
            "delayed": rate(cohort_delayed),
            "unseen": rate(cohort_unseen),
            "coaching_interruptions": sum(
                p.get("coaching", {}).get("interruptions", 0) for p in cohort
            ),
            "coaching_turns": sum(p.get("coaching", {}).get("turns", 0) for p in cohort),
            "help_escalations": sum(p.get("coaching", {}).get("escalations", 0) for p in cohort),
            "latency_median_seconds": statistics.median(latency) if latency else None,
            "latency_samples": len(latency),
        },
        "unaided": rate([e for e in attempts if e.get("assistance_level") == "none"]),
        "historical": old,
        "repairs": core.open_repair_gates(root),
        "independent": rate(attempts),
        "delayed": rate(delayed),
        "unseen": rate(unseen),
        "assistance": assistance,
        "timing_seconds": time_by_phase,
        "recorded_total_minutes": sum(
            e["minutes"] for e in core.effective_events(root) if e["event_id"] not in child_ids
        )
        + sum(p["minutes"] for p in guided)
        + sum(
            sum(e.get("timing", {}).values()) / 60
            for e in remaining
            if e.get("event_type") == "repair"
        ),
        "legacy_timing_incomplete": any(
            e.get("schema_version", 1) < 4 for e in core.effective_events(root)
        ),
        "baseline_sessions": len(cohort),
        "baseline_target": 12,
        "administration_median_minutes": statistics.median(admin) if admin else None,
        "administration_target_met": statistics.median(admin) <= 3 if admin else None,
        "topics": topic_progress(root),
    }
