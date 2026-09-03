from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pprint
import re
import statistics
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copy2, rmtree
from typing import Any
from zoneinfo import ZoneInfo

from fsrs import Card, Rating, Scheduler

EASTERN = ZoneInfo("America/New_York")
RATINGS = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}
ASSISTANCE_LEVELS = ("none", "minor", "guided", "substantial")
RECALL_QUALITIES = ("novel", "complete", "partial", "failed")
ERROR_CATEGORIES = (
    "problem-modeling",
    "pattern-selection",
    "representation",
    "invariant",
    "complexity",
    "edge-case",
    "implementation",
    "python-api",
    "debugging",
    "explanation",
)
ERROR_CAUSES = ("recall-gap", "misconception", "transfer-failure", "omission", "execution-slip")
ERROR_SEVERITIES = ("minor", "blocking")
MAX_ACTIVE_SEGMENT_SECONDS = 60 * 60
FOCUS_BLOCK_SECONDS = 45 * 60


def find_root(start: Path | None = None) -> Path:
    """Find the repository root from the working directory."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "curriculum").exists():
            return candidate
    module_root = Path(__file__).resolve().parents[2]
    if (module_root / "pyproject.toml").exists():
        return module_root
    raise RuntimeError("Run this command from the learning-system repository.")


def load_problems(root: Path) -> list[dict[str, Any]]:
    source = root / "curriculum" / "problems.json"
    return json.loads(source.read_text(encoding="utf-8"))["problems"]


def load_roadmap(root: Path) -> dict[str, Any]:
    source = root / "curriculum" / "roadmap.json"
    return json.loads(source.read_text(encoding="utf-8")) if source.exists() else {}


def problem_by_id(root: Path, problem_id: str) -> dict[str, Any]:
    for problem in load_problems(root):
        if problem["id"] == problem_id:
            return problem
    raise KeyError(f"Unknown problem ID: {problem_id}")


def event_files(root: Path) -> list[Path]:
    return sorted((root / "progress" / "reviews").glob("*.json"))


def load_events(root: Path) -> list[dict[str, Any]]:
    events = [json.loads(path.read_text(encoding="utf-8")) for path in event_files(root)]
    return sorted(events, key=lambda event: (event["reviewed_at"], event["event_id"]))


def correction_files(root: Path) -> list[Path]:
    return sorted((root / "progress" / "corrections").glob("*.json"))


def load_corrections(root: Path) -> dict[str, dict[str, Any]]:
    corrections: dict[str, dict[str, Any]] = {}
    for path in correction_files(root):
        correction = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "correction_id",
            "target_event_id",
            "problem_id",
            "corrected_rating",
            "corrected_at",
            "reason",
        }
        missing = sorted(required - correction.keys())
        if missing:
            raise RuntimeError(f"Correction {path.name} is missing: {', '.join(missing)}")
        if correction["corrected_rating"] not in RATINGS:
            raise RuntimeError(f"Correction {path.name} has an invalid rating.")
        target = correction["target_event_id"]
        if target in corrections:
            raise RuntimeError(f"More than one correction targets review event {target}.")
        corrections[target] = correction
    return corrections


def effective_events(root: Path) -> list[dict[str, Any]]:
    events = load_events(root)
    corrections = load_corrections(root)
    event_ids = {event["event_id"] for event in events}
    unknown = sorted(set(corrections) - event_ids)
    if unknown:
        raise RuntimeError(f"Review corrections target unknown events: {', '.join(unknown)}")
    effective = []
    for event in events:
        item = copy.deepcopy(event)
        correction = corrections.get(event["event_id"])
        if correction:
            if correction["problem_id"] != event["problem_id"]:
                raise RuntimeError(
                    f"Correction {correction['correction_id']} has the wrong problem ID."
                )
            item["original_rating"] = item["rating"]
            item["rating"] = correction["corrected_rating"]
            item["rating_correction"] = correction
        effective.append(item)
    return effective


def card_id(problem_id: str) -> int:
    return int.from_bytes(hashlib.sha256(problem_id.encode()).digest()[:7], "big")


def scheduler() -> Scheduler:
    # Day-scale steps suit coding problems better than flashcard-style minute steps.
    return Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False)


def rebuild_cards(root: Path) -> dict[str, Card]:
    cards: dict[str, Card] = {}
    engine = scheduler()
    for event in effective_events(root):
        problem_id = event["problem_id"]
        card = cards.setdefault(problem_id, Card(card_id=card_id(problem_id)))
        reviewed_at = datetime.fromisoformat(event["reviewed_at"]).astimezone(UTC)
        cards[problem_id], _ = engine.review_card(
            card,
            RATINGS[event["rating"]],
            review_datetime=reviewed_at,
            review_duration=event["minutes"] * 60 * 1000,
        )
    return cards


def latest_by_problem(root: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in effective_events(root):
        latest[event["problem_id"]] = event
    return latest


def is_independent_successful_review(event: dict[str, Any]) -> bool:
    """Return whether a review is complete, independent mastery evidence."""
    return (
        int(event.get("schema_version", 1)) >= 3
        and event.get("rating") in {"good", "easy"}
        and bool(event.get("tests_passed", False))
        and bool(event.get("explained", False))
        and event.get("recall_quality") in {"novel", "complete"}
        and event.get("assistance_level") in {"none", "minor"}
    )


def due_problems(root: Path, now: datetime | None = None) -> list[dict[str, Any]]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    cards = rebuild_cards(root)
    catalog = {problem["id"]: problem for problem in load_problems(root)}
    due = [catalog[problem_id] for problem_id, card in cards.items() if card.due <= now]
    return sorted(due, key=lambda problem: cards[problem["id"]].due)


def next_new_problem(root: Path, include_diagnostic: bool = False) -> dict[str, Any] | None:
    reviewed = {event["problem_id"] for event in effective_events(root)}
    for problem in load_problems(root):
        if problem["id"] in reviewed:
            continue
        if problem["kind"] == "diagnostic" and not include_diagnostic:
            continue
        return problem
    return None


def is_review_attempt(root: Path, problem_id: str) -> bool:
    return any(event["problem_id"] == problem_id for event in effective_events(root))


def learning_event_files(root: Path) -> list[Path]:
    return sorted((root / "progress" / "learning-events").glob("*.json"))


def load_learning_events(root: Path) -> list[dict[str, Any]]:
    events = [json.loads(path.read_text(encoding="utf-8")) for path in learning_event_files(root)]
    return sorted(events, key=lambda event: (event["recorded_at"], event["event_id"]))


def _write_learning_event(
    root: Path, event: dict[str, Any], recorded_at: datetime | None = None
) -> Path:
    recorded_at = (recorded_at or datetime.now(UTC)).astimezone(UTC)
    event_id = uuid.uuid4().hex
    payload = {
        "schema_version": 1,
        "event_id": event_id,
        "recorded_at": recorded_at.isoformat(),
        **event,
    }
    directory = root / "progress" / "learning-events"
    directory.mkdir(parents=True, exist_ok=True)
    name = recorded_at.strftime("%Y%m%dT%H%M%S%fZ") + f"-{event['event_type']}-{event_id[:8]}.json"
    path = directory / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def record_learning_error(
    root: Path,
    skill: str,
    category: str,
    cause: str,
    severity: str,
    summary: str,
    trigger: str,
    corrected_rule: str,
    repair_prompt: str,
    recorded_at: datetime | None = None,
) -> Path:
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem to annotate.")
    if category not in ERROR_CATEGORIES:
        raise RuntimeError(f"Unknown error category: {category}.")
    if cause not in ERROR_CAUSES:
        raise RuntimeError(f"Unknown error cause: {cause}.")
    if severity not in ERROR_SEVERITIES:
        raise RuntimeError(f"Unknown error severity: {severity}.")
    values = {
        "skill": skill,
        "summary": summary,
        "trigger": trigger,
        "corrected_rule": corrected_rule,
        "repair_prompt": repair_prompt,
    }
    empty = [name for name, value in values.items() if not value.strip()]
    if empty:
        raise RuntimeError(f"Learning error requires: {', '.join(empty)}.")
    unsafe = public_learning_text_errors("\n".join(values.values()))
    if unsafe:
        raise RuntimeError(f"Learning error contains public-content risks: {', '.join(unsafe)}")
    path = _write_learning_event(
        root,
        {
            "event_type": "error",
            "problem_id": session["problem_id"],
            "skill": skill.strip(),
            "category": category,
            "cause": cause,
            "severity": severity,
            "summary": summary.strip(),
            "trigger": trigger.strip(),
            "corrected_rule": corrected_rule.strip(),
            "repair_prompt": repair_prompt.strip(),
        },
        recorded_at,
    )
    session.setdefault("learning_event_paths", []).append(path.relative_to(root).as_posix())
    save_session(root, session)
    return path


def open_repair_gates(root: Path, now: datetime | None = None) -> list[dict[str, Any]]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    events = load_learning_events(root)
    latest_repairs: dict[tuple[str, str], datetime] = {}
    for event in events:
        if event["event_type"] != "repair" or not event["passed"]:
            continue
        key = (event["skill"], event["category"])
        repaired_at = datetime.fromisoformat(event["recorded_at"]).astimezone(UTC)
        previous = latest_repairs.get(key, datetime.min.replace(tzinfo=UTC))
        latest_repairs[key] = max(previous, repaired_at)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        if event["event_type"] != "error":
            continue
        key = (event["skill"], event["category"])
        recorded_at = datetime.fromisoformat(event["recorded_at"]).astimezone(UTC)
        if recorded_at <= latest_repairs.get(key, datetime.min.replace(tzinfo=UTC)):
            continue
        grouped.setdefault(key, []).append(event)
    gates = []
    for errors in grouped.values():
        blocking = [event for event in errors if event["severity"] == "blocking"]
        minor = [event for event in errors if event["severity"] == "minor"]
        if not blocking and len(minor) < 2:
            continue
        trigger = (blocking or minor)[-1]
        eligible_at = datetime.fromisoformat(trigger["recorded_at"]).astimezone(EASTERN)
        eligible_at = datetime.combine(
            eligible_at.date() + timedelta(days=1), datetime.min.time(), tzinfo=EASTERN
        ).astimezone(UTC)
        gate = copy.deepcopy(trigger)
        gate["eligible_at"] = eligible_at.isoformat()
        gate["eligible"] = eligible_at <= now
        gates.append(gate)
    return sorted(gates, key=lambda gate: gate["recorded_at"])


def blocking_repair_gates(root: Path) -> list[dict[str, Any]]:
    """Return gates that block new curriculum work, including not-yet-eligible gates."""
    return open_repair_gates(root)


def learning_insights(root: Path) -> dict[str, Any]:
    reviews = effective_events(root)
    learning = load_learning_events(root)
    errors = [event for event in learning if event["event_type"] == "error"]
    repairs = [event for event in learning if event["event_type"] == "repair"]
    review_attempts = [
        event for event in reviews if event.get("recall_quality", "novel") != "novel"
    ]
    measurable_reviews = [event for event in reviews if event.get("schema_version", 1) >= 3]
    independent = [event for event in measurable_reviews if is_independent_successful_review(event)]
    delayed_success = [
        event
        for event in review_attempts
        if event.get("recall_quality") == "complete"
        and is_independent_successful_review(event)
    ]
    category_counts: dict[str, int] = {}
    cause_counts: dict[str, int] = {}
    skill_counts: dict[str, int] = {}
    for event in errors:
        category_counts[event["category"]] = category_counts.get(event["category"], 0) + 1
        cause_counts[event["cause"]] = cause_counts.get(event["cause"], 0) + 1
        skill_counts[event["skill"]] = skill_counts.get(event["skill"], 0) + 1
    minutes = sum(int(event["minutes"]) for event in reviews)
    catalog = {problem["id"]: problem for problem in load_problems(root)}
    time_ratios = [
        int(event["minutes"]) / int(catalog[event["problem_id"]]["estimated_minutes"])
        for event in reviews
        if event["problem_id"] in catalog
    ]
    transfer = [event for event in measurable_reviews if event.get("kind") == "transfer"]
    repeated = {
        f"{skill} / {category}": count
        for (skill, category), count in {
            key: sum((event["skill"], event["category"]) == key for event in errors)
            for key in {(event["skill"], event["category"]) for event in errors}
        }.items()
        if count > 1
    }
    return {
        "review_count": len(reviews),
        "active_hours": round(minutes / 60, 2),
        "independent_solution_rate": (
            round(len(independent) / len(measurable_reviews), 3) if measurable_reviews else None
        ),
        "delayed_recall_success_rate": (
            round(len(delayed_success) / len(review_attempts), 3) if review_attempts else 0.0
        ),
        "first_checkpoint_pass_rate": (
            round(
                sum(bool(event.get("first_checkpoint_passed")) for event in measurable_reviews)
                / len(measurable_reviews),
                3,
            )
            if measurable_reviews
            else None
        ),
        "assistance_rate": (
            round(
                sum(
                    event.get("assistance_level", "none") != "none"
                    for event in measurable_reviews
                )
                / len(measurable_reviews),
                3,
            )
            if measurable_reviews
            else None
        ),
        "hint_rate": (
            round(
                sum(int(event.get("hints_used", 0)) > 0 for event in measurable_reviews)
                / len(measurable_reviews),
                3,
            )
            if measurable_reviews
            else None
        ),
        "median_time_vs_estimate": (
            round(statistics.median(time_ratios), 3) if time_ratios else None
        ),
        "transfer_success_rate": (
            round(
                sum(is_independent_successful_review(event) for event in transfer) / len(transfer),
                3,
            )
            if transfer
            else None
        ),
        "errors_by_category": dict(sorted(category_counts.items())),
        "errors_by_cause": dict(sorted(cause_counts.items())),
        "errors_by_skill": dict(sorted(skill_counts.items())),
        "recurring_errors": dict(sorted(repeated.items())),
        "open_repair_gates": len(open_repair_gates(root)),
        "cleared_repairs": sum(bool(event["passed"]) for event in repairs),
    }


def record_repair(
    root: Path,
    target_error_id: str,
    recognition_trigger: str,
    corrected_rule: str,
    why_failed: str,
    application: str,
    passed: bool,
    assistance: str = "none",
    recorded_at: datetime | None = None,
) -> Path:
    if assistance not in ASSISTANCE_LEVELS:
        raise RuntimeError(f"Unknown assistance level: {assistance}.")
    target = next(
        (event for event in load_learning_events(root) if event["event_id"] == target_error_id),
        None,
    )
    if target is None or target["event_type"] != "error":
        raise RuntimeError(f"Unknown learning error: {target_error_id}.")
    recorded_at = (recorded_at or datetime.now(UTC)).astimezone(UTC)
    gate = next(
        (
            item
            for item in open_repair_gates(root, recorded_at)
            if item["event_id"] == target_error_id
        ),
        None,
    )
    if gate is None:
        raise RuntimeError("This error does not currently require a repair gate.")
    if not gate["eligible"]:
        raise RuntimeError("This repair is deliberately delayed until the next Eastern day.")
    required = {
        "recognition trigger": recognition_trigger,
        "corrected rule": corrected_rule,
        "why the earlier reasoning failed": why_failed,
        "novel application": application,
    }
    empty = [name for name, value in required.items() if not value.strip()]
    if empty:
        raise RuntimeError(f"Repair requires: {', '.join(empty)}.")
    unsafe = public_learning_text_errors("\n".join(required.values()))
    if unsafe:
        raise RuntimeError(f"Repair contains public-content risks: {', '.join(unsafe)}")
    independent = passed and assistance in {"none", "minor"}
    return _write_learning_event(
        root,
        {
            "event_type": "repair",
            "problem_id": target["problem_id"],
            "skill": target["skill"],
            "category": target["category"],
            "target_error_id": target_error_id,
            "recognition_trigger": recognition_trigger.strip(),
            "corrected_rule": corrected_rule.strip(),
            "why_failed": why_failed.strip(),
            "application": application.strip(),
            "passed": independent,
            "assistance_level": assistance,
        },
        recorded_at,
    )


def session_path(root: Path) -> Path:
    tracked = root / "attempt" / "session.json"
    legacy = root / ".practice" / "session.json"
    return tracked if tracked.exists() or not legacy.exists() else legacy


def candidate_path(root: Path) -> Path:
    tracked = root / "attempt" / "current.py"
    legacy = root / ".practice" / "current.py"
    return tracked if tracked.exists() or not legacy.exists() else legacy


def load_session(root: Path) -> dict[str, Any] | None:
    path = session_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _modern_session(session: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    started_at = session.get("started_at", now.isoformat())
    # Preserve all evidence fields when pausing/resuming. Explicit normalization upgrades legacy
    # sessions, while the copy prevents newer fields from being silently discarded here.
    modern = copy.deepcopy(session)
    modern.update(
        {
            "schema_version": 5,
            "problem_id": session["problem_id"],
            "started_at": started_at,
            "active_started_at": session.get("active_started_at", started_at),
            "accumulated_seconds": int(session.get("accumulated_seconds", 0)),
            "hints_used": int(session.get("hints_used", 0)),
            "checkpoint_count": int(session.get("checkpoint_count", 0)),
            "assistance_log": list(session.get("assistance_log", [])),
            "focus_extensions": list(session.get("focus_extensions", [])),
            "learning_event_paths": list(session.get("learning_event_paths", [])),
            "substantial_gate_recorded": bool(session.get("substantial_gate_recorded", False)),
        }
    )
    return modern


def save_session(root: Path, session: dict[str, Any]) -> Path:
    legacy_checkpoints = root / "attempt" / "checkpoints"
    legacy_files = sorted(legacy_checkpoints.glob("*.json"))
    if "latest_checkpoint" not in session and legacy_files:
        latest = json.loads(legacy_files[-1].read_text(encoding="utf-8"))
        session["latest_checkpoint"] = {
            key: latest[key]
            for key in ("attempt", "checked_at", "passed_cases", "total_cases")
        }
    if legacy_checkpoints.exists():
        rmtree(legacy_checkpoints)
    path = root / "attempt" / "session.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return path


def record_initial_reasoning(
    root: Path,
    approach: str,
    invariant: str,
    complexity: str,
    why: str = "Not recorded in the legacy workflow.",
    edge_case: str = "Not recorded in the legacy workflow.",
    quality: str = "novel",
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    if quality not in RECALL_QUALITIES:
        raise RuntimeError(f"Recall quality must be one of: {', '.join(RECALL_QUALITIES)}.")
    values = {
        "approach": approach,
        "why": why,
        "invariant": invariant,
        "complexity": complexity,
        "edge_case": edge_case,
    }
    empty = [name for name, value in values.items() if not value.strip()]
    if empty:
        raise RuntimeError(f"Initial reasoning requires: {', '.join(empty)}.")
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem to annotate.")
    if session.get("initial_reasoning"):
        raise RuntimeError("Initial reasoning is already recorded for this attempt.")
    attempt_kind = session.get("attempt_kind")
    if attempt_kind == "new" and quality != "novel":
        raise RuntimeError("A new problem must use novel recall quality.")
    if attempt_kind == "review" and quality == "novel":
        raise RuntimeError("A review must use complete, partial, or failed recall quality.")
    recorded_at = (recorded_at or datetime.now(UTC)).astimezone(UTC)
    session["schema_version"] = 5
    session["initial_reasoning"] = {
        "approach": approach.strip(),
        "why": why.strip(),
        "invariant": invariant.strip(),
        "expected_complexity": complexity.strip(),
        "edge_case": edge_case.strip(),
        "quality": quality,
        "recorded_at": recorded_at.isoformat(),
    }
    save_session(root, session)
    return session["initial_reasoning"]


def record_assistance(
    root: Path,
    level: str,
    summary: str,
    source: str = "conversation",
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    if level not in ASSISTANCE_LEVELS[1:]:
        raise RuntimeError(f"Assistance level must be one of: {', '.join(ASSISTANCE_LEVELS[1:])}.")
    if not summary.strip():
        raise RuntimeError("Assistance summary cannot be empty.")
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active problem to annotate.")
    recorded_at = (recorded_at or datetime.now(UTC)).astimezone(UTC)
    session["schema_version"] = 5
    event = {
        "level": level,
        "summary": summary.strip(),
        "source": source,
        "recorded_at": recorded_at.isoformat(),
    }
    session.setdefault("assistance_log", []).append(event)
    save_session(root, session)
    if level == "substantial" and not session.get("substantial_gate_recorded", False):
        problem = problem_by_id(root, session["problem_id"])
        skill = problem.get("skills", [problem["topic"]])[0]
        path = _write_learning_event(
            root,
            {
                "event_type": "error",
                "problem_id": session["problem_id"],
                "skill": skill,
                "category": "pattern-selection",
                "cause": "recall-gap",
                "severity": "blocking",
                "source": "substantial-help",
                "summary": summary.strip(),
                "trigger": "Recognize the constraints that call for the supplied core pattern.",
                "corrected_rule": "Reconstruct the pattern and invariant without assistance.",
                "repair_prompt": (
                    "Explain the recognition trigger and invariant, then apply the pattern to "
                    "a fresh example without hints."
                ),
            },
            recorded_at,
        )
        session = load_session(root)
        assert session is not None
        session.setdefault("learning_event_paths", []).append(path.relative_to(root).as_posix())
        session["substantial_gate_recorded"] = True
        save_session(root, session)
    return event


def assistance_level(session: dict[str, Any]) -> str:
    rank = {level: index for index, level in enumerate(ASSISTANCE_LEVELS)}
    levels = [event["level"] for event in session.get("assistance_log", [])]
    hints = int(session.get("hints_used", 0))
    if hints >= 2:
        levels.append("substantial")
    elif hints == 1:
        levels.append("guided")
    return max(levels, key=rank.__getitem__, default="none")


def migrate_legacy_attempt(root: Path, now: datetime | None = None) -> bool:
    """Move an ignored v1 attempt into the tracked v2 layout without changing its code."""
    legacy_session = root / ".practice" / "session.json"
    legacy_candidate = root / ".practice" / "current.py"
    if not legacy_session.exists() or (root / "attempt" / "session.json").exists():
        return False
    session = json.loads(legacy_session.read_text(encoding="utf-8"))
    save_session(root, _modern_session(session, now))
    if legacy_candidate.exists():
        copy2(legacy_candidate, root / "attempt" / "current.py")
    return True


def cleanup_legacy_attempt(root: Path) -> None:
    legacy = root / ".practice"
    for name in ("current.py", "session.json"):
        (legacy / name).unlink(missing_ok=True)
    if legacy.exists() and not any(legacy.iterdir()):
        try:
            legacy.rmdir()
        except PermissionError:
            # Managed OneDrive folders may retain an empty reparse-point directory.
            pass


def active_seconds(session: dict[str, Any], now: datetime | None = None) -> int:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    total = int(session.get("accumulated_seconds", 0))
    active = session.get("active_started_at")
    if active:
        elapsed = now - datetime.fromisoformat(active).astimezone(UTC)
        segment = max(0, int(elapsed.total_seconds()))
        extensions = sum(int(item["minutes"]) for item in session.get("focus_extensions", []))
        segment_cap = max(MAX_ACTIVE_SEGMENT_SECONDS, FOCUS_BLOCK_SECONDS + extensions * 60)
        total += min(segment, segment_cap)
    return total


def public_learning_text_errors(text: str) -> list[str]:
    lowered = text.lower()
    errors = []
    for marker in ("password=", "api_key", "api-key", "token="):
        if marker in lowered:
            errors.append(marker)
    if "c:\\users\\" in lowered or "/home/" in lowered:
        errors.append("local filesystem path")
    if re.search(r"[\w.+-]+@lmco\.com", lowered):
        errors.append("employer email")
    return errors


def focus_limit_seconds(session: dict[str, Any]) -> int:
    extensions = sum(int(item["minutes"]) for item in session.get("focus_extensions", []))
    return FOCUS_BLOCK_SECONDS + extensions * 60


def focus_boundary_reached(session: dict[str, Any], now: datetime | None = None) -> bool:
    return active_seconds(session, now) >= focus_limit_seconds(session)


def extend_focus(root: Path, minutes: int, now: datetime | None = None) -> dict[str, Any]:
    if minutes <= 0 or minutes > 30:
        raise RuntimeError("Focus extensions must be between 1 and 30 minutes.")
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active practice session.")
    now = (now or datetime.now(UTC)).astimezone(UTC)
    session.setdefault("focus_extensions", []).append(
        {"minutes": minutes, "recorded_at": now.isoformat()}
    )
    save_session(root, session)
    return session


def pause_timer(root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active practice session.")
    session = _modern_session(session, now)
    session["accumulated_seconds"] = active_seconds(session, now)
    session["active_started_at"] = None
    save_session(root, session)
    return session


def resume_timer(root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    session = load_session(root)
    if session is None:
        raise RuntimeError("No active practice session.")
    session = _modern_session(session, now)
    if session.get("active_started_at") is None:
        session["active_started_at"] = now.isoformat()
        save_session(root, session)
    return session


def display_value(value: Any) -> str:
    """Format JSON-compatible exercise values as readable Python literals."""
    return pprint.pformat(value, width=88, sort_dicts=False)


def wrapped(text: str, *, initial: str = "", subsequent: str = "") -> list[str]:
    return textwrap.wrap(
        text,
        width=88,
        initial_indent=initial,
        subsequent_indent=subsequent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def render_template(problem: dict[str, Any]) -> str:
    lines = [
        '"""',
        problem["title"],
        "=" * len(problem["title"]),
        f"Difficulty: {problem['difficulty'].title()} | Suggested time: "
        f"{problem['estimated_minutes']} minutes",
        "",
        "Problem",
        "-------",
        *wrapped(problem["prompt"]),
        "",
        "Function signature",
        "------------------",
        problem["signature"],
        "",
        "Parameters",
        "----------",
    ]
    for parameter in problem["parameters"]:
        prefix = f"{parameter['name']} ({parameter['type']}): "
        lines.extend(
            wrapped(
                parameter["description"],
                initial=prefix,
                subsequent=" " * len(prefix),
            )
        )
    lines.extend(
        [
            "",
            "Returns",
            "-------",
            *wrapped(
                problem["returns"]["description"],
                initial=f"{problem['returns']['type']}: ",
                subsequent="    ",
            ),
            "",
            "Constraints",
            "-----------",
        ]
    )
    for constraint in problem["constraints"]:
        lines.extend(wrapped(constraint, initial="- ", subsequent="  "))
    for index, example in enumerate(problem["examples"], start=1):
        heading = f"Example {index}"
        lines.extend(["", heading, "-" * len(heading)])
        for name, value in example["inputs"].items():
            lines.append(f"{name} = {display_value(value)}")
        lines.append(f"Output: {display_value(example['output'])}")
        lines.extend(
            wrapped(
                example["explanation"],
                initial="Explanation: ",
                subsequent="             ",
            )
        )
    lines.extend(
        [
            "",
            "Related practice",
            "----------------",
            problem["related_url"],
            '"""',
            "",
            "",
            f"def {problem['signature']}:",
            "    raise NotImplementedError",
            "",
        ]
    )
    return "\n".join(lines)


def start_problem(root: Path, problem_id: str, now: datetime | None = None) -> Path:
    problem = problem_by_id(root, problem_id)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    practice = root / "attempt"
    practice.mkdir(parents=True, exist_ok=True)
    current = practice / "current.py"
    current.write_text(render_template(problem), encoding="utf-8")
    session = {
        "schema_version": 5,
        "problem_id": problem_id,
        "attempt_kind": "review" if is_review_attempt(root, problem_id) else "new",
        "started_at": now.isoformat(),
        "active_started_at": now.isoformat(),
        "accumulated_seconds": 0,
        "hints_used": 0,
        "checkpoint_count": 0,
        "assistance_log": [],
        "focus_extensions": [],
        "learning_event_paths": [],
        "substantial_gate_recorded": False,
    }
    save_session(root, session)
    return current


@dataclass
class CaseFailure:
    index: int
    expected: Any
    actual: Any = None
    error: str | None = None


def run_solution(path: Path, problem: dict[str, Any]) -> list[CaseFailure]:
    module_name = f"study_candidate_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return [CaseFailure(0, None, error="Could not import candidate file")]
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        function = getattr(module, problem["function"])
    except Exception as exc:  # learner-facing runner should report all import errors
        return [CaseFailure(0, None, error=f"{type(exc).__name__}: {exc}")]

    failures = []
    for index, case in enumerate(problem["cases"], start=1):
        try:
            actual = function(*copy.deepcopy(case["args"]))
            if actual != case["expected"]:
                failures.append(CaseFailure(index, case["expected"], actual=actual))
        except Exception as exc:  # learner-facing runner should report the case
            failures.append(
                CaseFailure(index, case["expected"], error=f"{type(exc).__name__}: {exc}")
            )
    return failures


def record_review(
    root: Path,
    problem: dict[str, Any],
    rating: str,
    minutes: int,
    passed: bool,
    hints_used: int,
    explained: bool,
    assistance_level: str = "none",
    assistance_count: int = 0,
    recall_quality: str = "novel",
    first_checkpoint_passed: bool = False,
    reviewed_at: datetime | None = None,
) -> Path:
    if assistance_level not in ASSISTANCE_LEVELS:
        raise RuntimeError(f"Unknown assistance level: {assistance_level}.")
    if assistance_count < 0:
        raise RuntimeError("Assistance count cannot be negative.")
    if recall_quality not in RECALL_QUALITIES:
        raise RuntimeError(f"Unknown recall quality: {recall_quality}.")
    reviewed_at = (reviewed_at or datetime.now(UTC)).astimezone(UTC)
    event_id = uuid.uuid4().hex
    event = {
        "schema_version": 3,
        "event_id": event_id,
        "problem_id": problem["id"],
        "topic": problem["topic"],
        "kind": problem["kind"],
        "reviewed_at": reviewed_at.isoformat(),
        "rating": rating,
        "minutes": minutes,
        "hints_used": hints_used,
        "assistance_level": assistance_level,
        "assistance_count": assistance_count,
        "recall_quality": recall_quality,
        "first_checkpoint_passed": first_checkpoint_passed,
        "explained": explained,
        "tests_passed": passed,
    }
    reviews = root / "progress" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    filename = reviewed_at.strftime("%Y%m%dT%H%M%S%fZ") + f"-{problem['id']}-{event_id[:8]}.json"
    path = reviews / filename
    path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
    return path


def git_output(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def format_failure(failure: CaseFailure) -> str:
    if failure.error:
        return f"case {failure.index}: {failure.error}"
    return f"case {failure.index}: expected {failure.expected!r}, got {failure.actual!r}"


def current_eastern_date() -> str:
    return datetime.now(EASTERN).date().isoformat()


def python_version_ok() -> bool:
    return sys.version_info >= (3, 11)
