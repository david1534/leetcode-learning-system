from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    return root / ".practice" / "session.json"


def load_session(root: Path) -> dict[str, Any] | None:
    path = session_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def render_template(problem: dict[str, Any]) -> str:
    examples = json.dumps(problem["examples"], indent=2)
    return (
        f'"""{problem["title"]}\n\n{problem["prompt"]}\n\n'
        f"Examples:\n{examples}\n\nRelated practice: {problem['related_url']}\n"
        '"""\n\n\n'
        f"def {problem['function']}(*args):\n"
        '    """Replace *args with a clear typed signature, then implement your solution."""\n'
        "    raise NotImplementedError\n"
    )


def start_problem(root: Path, problem_id: str) -> Path:
    problem = problem_by_id(root, problem_id)
    practice = root / ".practice"
    practice.mkdir(exist_ok=True)
    current = practice / "current.py"
    current.write_text(render_template(problem), encoding="utf-8")
    session = {
        "problem_id": problem_id,
        "started_at": datetime.now(UTC).isoformat(),
        "hints_used": 0,
    }
    session_path(root).write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
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
