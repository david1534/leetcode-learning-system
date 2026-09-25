"""Lossless import of file-based attempts and interrupted grouped completions."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from study import core
from study.database import PUBLIC_PREFIXES


def migrate_saved_work(store):
    first_import = not store.exists(".study-local/migration.json")
    if first_import:
        preferences = store.read_json(".study-local/coach/preferences.json")
        if preferences:
            preferences.update(automatic=False, approach=False, check=False)
            store.write_json(".study-local/coach/preferences.json", preferences)
    portable = store.read_json("attempt/practice.json", {})
    parent = store.read_json(".study-local/practice.json") or portable.get("parent")
    if portable:
        artifacts = portable.get("artifacts", {})
        if any(not path.startswith(PUBLIC_PREFIXES) for path in artifacts):
            raise RuntimeError("The saved portable attempt contains an invalid artifact path.")
        store.import_documents(
            artifacts, "portable-" + portable.get("parent", {}).get("practice_id", "legacy")
        )
        for sid, receipt in portable.get("receipts", {}).items():
            if not sid.isalnum():
                raise RuntimeError("The saved portable attempt has an invalid completion ID.")
            if not store.exists(f".study-local/completions/{sid}.json"):
                store.write_json(f".study-local/completions/{sid}.json", receipt)
        if portable.get("repair") and not store.exists(".study-local/repair-timer.json"):
            timer = portable["repair"]
            timer["started_at"] = None
            store.write_json(".study-local/repair-timer.json", timer)
    session = store.read_json("attempt/session.json")
    parent = parent or (session or {}).get("practice")
    intent = store.read_json(".study-local/practice-completion.json")
    if intent:
        parent = intent["parent"]
    reviews = {e["event_id"]: e for e in store.json_documents("progress/reviews/")}
    # A review may have been written before its file-based receipt. Only a matching
    # archived candidate proves that completion was recorded; never guess from age.
    sid = (session or {}).get("session_id")
    if sid in reviews:
        event = reviews[sid]
        candidate = store.read_text(f"progress/attempts/{sid}/candidate.py")
        if candidate is None or hashlib.sha256(candidate.encode()).hexdigest() != event.get(
            "code_digest"
        ):
            raise RuntimeError(
                "An interrupted completion has conflicting evidence. Its original "
                "files are preserved; review the migration diagnostics."
            )
        current_code = store.read_text("attempt/current.py", "")
        completed_session = store.read_json(f"progress/attempts/{sid}/session.json", {})
        imported_digest = completed_session.get("imported_code_digest")
        if (
            current_code != candidate
            and hashlib.sha256(current_code.encode()).hexdigest() != imported_digest
        ):
            conflict_id = hashlib.sha256((sid + current_code).encode()).hexdigest()[:24]
            store.write_json(
                f".study-local/conflicts/{conflict_id}.json",
                {
                    "id": conflict_id,
                    "path": "attempt/current.py",
                    "source": "edited-after-completion",
                    "incoming": current_code,
                    "saved_digest": hashlib.sha256(b"").hexdigest(),
                    "recover_session": session,
                    "status": "unresolved",
                },
            )
        receipt_key = f".study-local/completions/{sid}.json"
        if not store.exists(receipt_key):
            paths = [f"progress/attempts/{sid}"]
            paths += [
                path
                for path in store.paths("progress/reviews/", ".json")
                if store.read_json(path).get("event_id") == sid
            ]
            paths += session.get("learning_event_paths", [])
            store.write_json(
                receipt_key,
                {
                    "session_id": sid,
                    "event_id": sid,
                    "problem_id": session["problem_id"],
                    "status": "saved",
                    "published": False,
                    "paths": paths,
                    "message": "Recovered a locally saved completion.",
                },
            )
        store.write_json(".study-local/last-completion.json", store.read_json(receipt_key))
        store.delete_tree("attempt/")
        session = None
    if parent:
        pid = parent["practice_id"]
        main_id = (intent or {}).get("session_id") or sid
        key = f"progress/practice-sessions/{pid}.json"
        completed = store.read_json(key)
        stages = parent.get("stages", [])
        stage = stages[parent.get("index", 0)] if stages else {}
        if not completed and main_id in reviews and (intent or stage.get("type") == "main"):
            completed = json.loads(json.dumps(parent))
            completed["attempt_ids"] = list(
                dict.fromkeys([*parent.get("attempt_ids", []), main_id])
            )
            completed["receipts"] = list(
                dict.fromkeys(
                    [
                        *parent.get("receipts", []),
                        main_id,
                        *parent.get("repair_receipts", []),
                    ]
                )
            )
            timing = dict(parent.get("timing", {}))
            for child_id in completed["attempt_ids"]:
                for phase, seconds in reviews.get(child_id, {}).get("timing", {}).items():
                    timing[phase] = timing.get(phase, 0) + seconds
            for path in parent.get("repair_paths", []):
                for phase, seconds in store.read_json(path, {}).get("timing", {}).items():
                    timing[phase] = timing.get(phase, 0) + seconds
            minutes = sum(timing.values()) / 60
            reported = (intent or {}).get("minutes")
            if reported is not None:
                timing["unclassified_adjustment"] = (reported - minutes) * 60
                minutes = reported
            completed.update(
                status="completed",
                completed_at=reviews[main_id]["reviewed_at"],
                main_attempt_id=main_id,
                main_activity=reviews[main_id]["activity"],
                timing=timing,
                minutes=minutes,
            )
            if stages:
                completed["stages"][completed["index"]]["status"] = "completed"
            store.write_json(key, completed)
        if completed:
            paths = [key, *completed.get("repair_paths", [])]
            child_ids = completed.get("receipts", completed.get("attempt_ids", []))
            for child_id in child_ids:
                child_key = f".study-local/completions/{child_id}.json"
                child = store.read_json(child_key)
                if child:
                    paths.extend(child["paths"])
                    child["grouped_into"] = pid
                    store.write_json(child_key, child)
            receipt_key = f".study-local/completions/{pid}.json"
            receipt = store.read_json(receipt_key) or {
                "session_id": pid,
                "event_id": pid,
                "problem_id": reviews.get(main_id, {}).get("problem_id", "legacy-session"),
                "status": "saved",
                "published": False,
                "paths": list(dict.fromkeys(p for p in paths if p != "attempt")),
                "child_receipts": child_ids,
                "message": "Recovered the completed practice session.",
            }
            store.write_json(receipt_key, receipt)
            store.write_json(".study-local/last-completion.json", receipt)
        # The original group stays recoverable; it never drives another automatic stage.
        store.write_json(f".study-local/legacy-groups/{pid}.json", parent)
        store.delete(".study-local/practice.json")
        store.delete(".study-local/practice-completion.json")
        store.delete("attempt/practice.json")
    if session and session.get("workflow_version", 0) < 4:
        original = json.loads(json.dumps(session))
        sid = (
            session.get("session_id")
            or uuid.uuid5(
                uuid.NAMESPACE_URL,
                session["problem_id"]
                + ":"
                + session.get("started_at", json.dumps(session, sort_keys=True)),
            ).hex
        )
        problem = core.problem_by_id(store.root, session["problem_id"])
        session.update(
            session_id=sid,
            schema_version=7,
            workflow_version=4,
            revision=session.get("revision", 0),
            activity=session.get("activity", "implement"),
            budget_minutes=session.get("budget_minutes", 60),
            content_version=session.get("content_version", problem.get("content_version", 1)),
            rubric_version=session.get("rubric_version", 2),
            skill_ids=session.get("skill_ids", problem.get("skill_ids", [])),
            timing=session.get("timing", {"unclassified": session.get("accumulated_seconds", 0)}),
            phase=session.get(
                "phase", "implementation" if session.get("initial_reasoning") else "recall"
            ),
            phase_started_at=None,
            active_started_at=None,
            unseen=session.get("unseen", False),
            code_digest=hashlib.sha256(
                store.read_text("attempt/current.py", "").encode()
            ).hexdigest(),
            saved_at=session.get("saved_at", session.get("started_at")),
            migrated_from=original.get("schema_version", 1),
            imported_code_digest=hashlib.sha256(
                store.read_text("attempt/current.py", "").encode()
            ).hexdigest(),
        )
        session.setdefault("sync_branch", "attempt/" + session["problem_id"] + "-" + sid[:12])
        session["assessment_mode"] = (
            "independent" if session["activity"] == "transfer" else "practice"
        )
        session.pop("practice", None)
        session.pop("practice_session_id", None)
        store.write_json(f".study-local/legacy-attempts/{sid}.json", original)
        store.write_text(
            f".study-local/legacy-candidates/{sid}.py", store.read_text("attempt/current.py", "")
        )
        store.write_json(f".study-local/problem-contracts/{sid}.json", problem)
        store.write_json("attempt/session.json", session)
        if store.read_json(".study-local/repair-timer.json"):
            store.write_json(
                f".study-local/queued-attempts/{sid}.json",
                {
                    "session": session,
                    "code": store.read_text("attempt/current.py", ""),
                },
            )
            store.delete_tree("attempt/")
    pending = store.read_json(".study-local/pending.json")
    if pending and not store.exists(".study-local/legacy-pending.json"):
        frozen = {}
        for path in pending.get("paths", []):
            if path == "attempt":
                continue
            if store.exists(path):
                frozen[path] = store.read_text(path)
            else:
                frozen.update(store.documents(path.rstrip("/") + "/"))
        store.write_json(".study-local/legacy-pending.json", {**pending, "artifacts": frozen})
        store.delete(".study-local/pending.json")
    store.write_json(
        ".study-local/migration.json",
        {
            "version": 1,
            "checked_at": datetime.now(UTC).isoformat(),
            "message": "Original files retained. Local practice uses SQLite.",
        },
    )
