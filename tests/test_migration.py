"""Import real legacy shapes without rewriting the original learner artifacts."""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from study import core, policy
from study.service import StudyService

PAIR = "arrays-001-pair-sum"
MAIN_ID = "a" * 32
SUPPORT_ID = "b" * 32
PARENT_ID = "c" * 32


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def legacy_group(root, repo_root, failure_at):
    shutil.copytree(repo_root / "curriculum", root / "curriculum")
    problem = core.problem_by_id(root, PAIR)
    code = "def pair_sum_indices(nums, target):\n    return [0, 1]\n"
    checksum = hashlib.sha256(code.encode()).hexdigest()
    parent = {
        "practice_id": PARENT_ID,
        "workflow_version": 3,
        "status": "active",
        "started_at": "2026-09-01T12:00:00+00:00",
        "budget_minutes": 60,
        "include_new": True,
        "index": 1,
        "attempt_ids": [SUPPORT_ID],
        "receipts": [SUPPORT_ID],
        "repair_paths": [],
        "timing": {},
        "stages": [
            {"type": "recall", "status": "completed", "activity": "recall"},
            {"type": "main", "status": "active", "activity": "implement"},
        ],
    }
    session = {
        "session_id": MAIN_ID,
        "schema_version": 6,
        "workflow_version": 3,
        "problem_id": PAIR,
        "attempt_kind": "review",
        "revision": 103,
        "activity": "implement",
        "assessment_mode": "independent",
        "phase": "administration",
        "phase_started_at": None,
        "active_started_at": None,
        "started_at": parent["started_at"],
        "timing": {"implementation": 60},
        "initial_reasoning": {"approach": "Original reconstruction.", "quality": "complete"},
        "assistance_log": [],
        "budget_minutes": 60,
        "code_digest": checksum,
        "content_version": 1,
        "rubric_version": 2,
        "skill_ids": [],
        "unseen": False,
        "practice": parent,
        "practice_session_id": PARENT_ID,
    }
    receipts = {}
    for sid, activity, seconds in [(SUPPORT_ID, "recall", 120), (MAIN_ID, "implement", 60)]:
        event = {
            "event_id": sid,
            "schema_version": 4,
            "session_id": sid,
            "problem_id": PAIR,
            "topic": problem["topic"],
            "kind": problem["kind"],
            "workflow_version": 3,
            "practice_session_id": PARENT_ID,
            "reviewed_at": "2026-09-01T12:10:00+00:00",
            "rating": "good",
            "activity": activity,
            "minutes": seconds / 60,
            "timing": {"implementation": seconds},
            "code_digest": checksum,
            "recall_outcome": "success",
            "recall_quality": "complete",
            "assistance_level": "none",
            "tests_passed": True,
            "explained": True,
            "assessment": {"constraints_met": True},
        }
        write(root, f"progress/reviews/{sid}.json", event)
        write(root, f"progress/attempts/{sid}/candidate.py", code)
        write(root, f"progress/attempts/{sid}/session.json", session)
        write(root, f"progress/attempts/{sid}/reflection.md", "Original takeaway.\n")
        receipt = {
            "session_id": sid,
            "event_id": sid,
            "problem_id": PAIR,
            "status": "saved",
            "published": False,
            "paths": [f"progress/reviews/{sid}.json", f"progress/attempts/{sid}"],
        }
        receipts[sid] = receipt
        if not (failure_at == "main_receipt" and sid == MAIN_ID):
            write(root, f".study-local/completions/{sid}.json", receipt)
    write(root, "attempt/current.py", code)
    write(root, "attempt/session.json", session)
    write(root, ".study-local/practice.json", parent)
    write(
        root,
        ".study-local/practice-completion.json",
        {"parent": parent, "session_id": MAIN_ID, "minutes": 25},
    )
    if failure_at in {"parent_receipt", "grouping", "last_receipt"}:
        completed = copy.deepcopy(parent)
        completed.update(
            status="completed",
            completed_at="2026-09-01T12:10:00+00:00",
            attempt_ids=[SUPPORT_ID, MAIN_ID],
            receipts=[SUPPORT_ID, MAIN_ID],
            timing={"implementation": 180, "unclassified_adjustment": 1320},
            minutes=25,
            main_attempt_id=MAIN_ID,
            main_activity="implement",
        )
        write(root, f"progress/practice-sessions/{PARENT_ID}.json", completed)
    if failure_at in {"grouping", "last_receipt"}:
        write(
            root,
            f".study-local/completions/{PARENT_ID}.json",
            {
                "session_id": PARENT_ID,
                "event_id": PARENT_ID,
                "problem_id": PAIR,
                "published": False,
                "status": "saved",
                "child_receipts": [SUPPORT_ID, MAIN_ID],
                "paths": [
                    f"progress/practice-sessions/{PARENT_ID}.json",
                    *receipts[MAIN_ID]["paths"],
                    *receipts[SUPPORT_ID]["paths"],
                ],
                "message": "Original group saved.",
            },
        )
    return session, code


@pytest.mark.parametrize(
    "failure_at", ["main_receipt", "parent_event", "parent_receipt", "grouping", "last_receipt"]
)
def test_import_recovers_partial_group_once_and_preserves_original_files(
    tmp_path, repo_root, failure_at
):
    root = tmp_path / "legacy"
    legacy_group(root, repo_root, failure_at)
    original = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    events = core.load_events(root)
    before = {key: card.to_dict() for key, card in core.rebuild_cards(root).items()}
    service = StudyService(root)
    state = service.state()
    assert state["session"] is None
    assert state["completion"]["session_id"] == PARENT_ID
    assert state["unpublished_count"] == 1
    assert core.load_events(root) == events
    assert {key: card.to_dict() for key, card in core.rebuild_cards(root).items()} == before
    assert policy.metrics(root)["recorded_total_minutes"] == 25
    assert policy.metrics(root)["baseline_sessions"] == 0
    assert all((root / path).read_bytes() == value for path, value in original.items())
    restarted = StudyService(root)
    assert restarted.state()["completion"]["session_id"] == PARENT_ID
    assert policy.metrics(root)["recorded_total_minutes"] == 25
    assert len(core.load_events(root)) == 2


def test_newer_draft_after_legacy_completion_remains_recoverable(tmp_path, repo_root):
    root = tmp_path / "edited-legacy"
    legacy_group(root, repo_root, "parent_event")
    edited = "def pair_sum_indices(nums, target):\n    # unfinished later edit\n    return []\n"
    write(root, "attempt/current.py", edited)
    service = StudyService(root)
    state = service.state()
    assert state["session"] is None
    recovery = state["recovery"][0]
    stored = service._read_local("conflicts/" + recovery["id"])
    assert stored["incoming"] == edited
    service.recover(recovery["id"], use_incoming=True)
    resumed = service.state()["session"]
    assert resumed["session_id"] != MAIN_ID
    assert resumed["code"] == edited and resumed["activity"] == "learn"
    assert len(core.load_events(root)) == 2
    assert (root / "attempt/current.py").read_text() == edited


def test_actual_saved_repository_state_imports_without_changing_its_history(tmp_path):
    source = Path(__file__).resolve().parents[1]
    root = tmp_path / "actual-history"
    for name in ("curriculum", "attempt", "progress", "solutions", "reflections"):
        if (source / name).exists():
            shutil.copytree(source / name, root / name)
    before_events = core.load_events(root)
    before_cards = {key: card.to_dict() for key, card in core.rebuild_cards(root).items()}
    originals = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    service = StudyService(root)
    state = service.state()
    assert state["session"] or state["repair"] or state["completion"]
    assert core.load_events(root) == before_events
    assert {key: card.to_dict() for key, card in core.rebuild_cards(root).items()} == before_cards
    assert all((root / path).read_bytes() == value for path, value in originals.items())
