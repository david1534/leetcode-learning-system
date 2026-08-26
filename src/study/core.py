from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pprint
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
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
MAX_ACTIVE_SEGMENT_SECONDS = 60 * 60


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


def card_id(problem_id: str) -> int:
    return int.from_bytes(hashlib.sha256(problem_id.encode()).digest()[:7], "big")


def scheduler() -> Scheduler:
    # Day-scale steps suit coding problems better than flashcard-style minute steps.
    return Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False)


def rebuild_cards(root: Path) -> dict[str, Card]:
    cards: dict[str, Card] = {}
    engine = scheduler()
    for event in load_events(root):
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
    for event in load_events(root):
        latest[event["problem_id"]] = event
    return latest


def due_problems(root: Path, now: datetime | None = None) -> list[dict[str, Any]]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    cards = rebuild_cards(root)
    catalog = {problem["id"]: problem for problem in load_problems(root)}
    due = [catalog[problem_id] for problem_id, card in cards.items() if card.due <= now]
    return sorted(due, key=lambda problem: cards[problem["id"]].due)


def next_new_problem(root: Path, include_diagnostic: bool = False) -> dict[str, Any] | None:
    reviewed = {event["problem_id"] for event in load_events(root)}
    for problem in load_problems(root):
        if problem["id"] in reviewed:
            continue
        if problem["kind"] == "diagnostic" and not include_diagnostic:
            continue
        return problem
    return None


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
    modern = {
        "schema_version": 3,
        "problem_id": session["problem_id"],
        "started_at": started_at,
        "active_started_at": session.get("active_started_at", started_at),
        "accumulated_seconds": int(session.get("accumulated_seconds", 0)),
        "hints_used": int(session.get("hints_used", 0)),
        "checkpoint_count": int(session.get("checkpoint_count", 0)),
    }
    if "latest_checkpoint" in session:
        modern["latest_checkpoint"] = session["latest_checkpoint"]
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
        total += min(segment, MAX_ACTIVE_SEGMENT_SECONDS)
    return total


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
        "schema_version": 3,
        "problem_id": problem_id,
        "started_at": now.isoformat(),
        "active_started_at": now.isoformat(),
        "accumulated_seconds": 0,
        "hints_used": 0,
        "checkpoint_count": 0,
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
    reviewed_at: datetime | None = None,
) -> Path:
    reviewed_at = (reviewed_at or datetime.now(UTC)).astimezone(UTC)
    event_id = uuid.uuid4().hex
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "problem_id": problem["id"],
        "topic": problem["topic"],
        "kind": problem["kind"],
        "reviewed_at": reviewed_at.isoformat(),
        "rating": rating,
        "minutes": minutes,
        "hints_used": hints_used,
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
