"""The one mutation boundary used by both app and coach commands."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from study import core, gitflow, policy
from study.database import StudyStore, TransactionLock
from study.guided import GuidedSession
from study.storage import atomic_text

PHASES = {"recall", "implementation", "explanation", "repair", "administration", "learning"}
ACTIVITIES = {"learn", "recall", "implement", "transfer"}
SCHEDULER = {
    "library": "fsrs",
    "version": "6.3.2",
    "desired_retention": 0.9,
    "learning_steps": [],
    "relearning_steps": [],
    "enable_fuzzing": False,
}


class Conflict(RuntimeError):
    """The caller must refresh and preserve their own unsaved text."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class StudyService(GuidedSession):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.store = StudyStore(self.root).initialize()
        self.local = self.store.directory
        self.lock = TransactionLock(self.store)
        self.store.import_workspace()
        from study.migration import migrate_saved_work

        with self.lock:
            migrate_saved_work(self.store)
        from study.synchronization import Synchronizer

        self.synchronizer = Synchronizer(self)

    def _problem(self, session):
        return self._read_local("problem-contracts/" + session["session_id"]) or core.problem_by_id(
            self.root, session["problem_id"]
        )

    def export_editor(self):
        """An explicit, recoverable editor copy; SQLite remains authoritative."""
        with self.lock:
            session = self._session()
            if not session.get("initial_reasoning") and session["activity"] != "learn":
                raise RuntimeError("Record your initial idea before opening the candidate.")
            path = self.local / "editor/current.py"
            saved = self._read_local("editor-copy", {})
            if path.exists():
                text = path.read_text(encoding="utf-8")
                if saved.get("session_id") == session["session_id"] and digest(text) != saved.get(
                    "code_digest"
                ):
                    return path
                if digest(text) != saved.get("code_digest"):
                    self.store.write_text(
                        f".study-local/editor-recovery/{uuid.uuid4().hex}.py", text
                    )
            atomic_text(path, self._code())
            self._write_local(
                "editor-copy",
                {
                    "session_id": session["session_id"],
                    "revision": session["revision"],
                    "code_digest": session["code_digest"],
                },
            )
            return path

    def import_editor(self):
        with self.lock:
            saved = self._read_local("editor-copy")
            path = self.local / "editor/current.py"
            session = core.load_session(self.root)
            if (
                not saved
                or not session
                or saved["session_id"] != session["session_id"]
                or not path.exists()
            ):
                return
            text = path.read_text(encoding="utf-8")
            if digest(text) == saved["code_digest"]:
                if session["code_digest"] != saved["code_digest"]:
                    self.export_editor()
                return
            self.save_code(text, saved["revision"], saved["code_digest"])
            current = self._session()
            self._write_local(
                "editor-copy",
                {
                    "session_id": current["session_id"],
                    "revision": current["revision"],
                    "code_digest": current["code_digest"],
                },
            )

    def continue_focus(self, minutes):
        if not 1 <= minutes <= 15:
            raise RuntimeError("Choose a short extension of 1?15 minutes.")
        with self.lock:
            session = self._session()
            session["budget_minutes"] += minutes
            session.setdefault("focus_extensions", []).append(
                {"minutes": minutes, "recorded_at": datetime.now(UTC).isoformat()}
            )
            session["phase_started_at"] = datetime.now(UTC).isoformat()
            session["active_started_at"] = session["phase_started_at"]
            self._save(session)
        return self.state()

    def _code(self):
        return self.store.read_text("attempt/current.py", "")

    def _write_local(self, name, value):
        self.store.write_json(f".study-local/{name}.json", value)

    def _delete_local(self, name):
        self.store.delete(f".study-local/{name}.json")

    def _artifact(self, path, default=None):
        return self.store.read_text(path, default)

    def _write_artifact(self, path, value, text=False):
        (self.store.write_text if text else self.store.write_json)(path, value)

    def _recover_completed(self):
        session = core.load_session(self.root)
        if session and session.get("session_id"):
            receipt = self._read_local("completions/" + session["session_id"])
            if receipt:
                self._close_attempt(receipt)
        self._recover_practice_completion()

    def _close_attempt(self, receipt):
        session = core.load_session(self.root)
        if session and session.get("session_id") == receipt["session_id"]:
            self.store.delete_tree("attempt/")
        self._write_local("last-completion", receipt)

    def _check_state(self):
        check = self._read_local("check", {})
        if check.get("status") == "running":
            age = (datetime.now(UTC) - datetime.fromisoformat(check["started_at"])).total_seconds()
            if age > 15:
                check.update(status="interrupted", message="Check interrupted; run again.")
                self._write_local("check", check)
        return check

    def _read_local(self, name: str, default=None):
        return self.store.read_json(f".study-local/{name}.json", default)

    def _unpublished(self):
        return [
            r
            for r in self.store.json_documents(".study-local/completions/")
            if not r.get("published") and not r.get("grouped_into")
        ]

    def _save(self, session: dict):
        session["revision"] = session.get("revision", 0) + 1
        session["saved_at"] = datetime.now(UTC).isoformat()
        core.save_session(self.root, session)

    def _session(self, revision: int | None = None, session_id: str | None = None) -> dict:
        session = core.load_session(self.root)
        if session is None:
            raise RuntimeError("No active activity. Start from Today.")
        changed = False
        if session.get("schema_version", 1) < 6:
            session.update(
                schema_version=6,
                session_id=uuid.uuid4().hex,
                revision=0,
                activity="implement",
                phase="implementation",
                timing={},
                phase_started_at=session.get("active_started_at"),
                unseen=False,
                rubric_version=2,
            )
            session["timing"] = {"unclassified": session.get("accumulated_seconds", 0)}
            problem = self._problem(session)
            session.setdefault("attempt_kind", "review")
            session.setdefault("budget_minutes", policy.settings(self.root)["session_minutes"])
            session.setdefault("content_version", problem.get("content_version", 1))
            session.setdefault("skill_ids", problem.get("skill_ids", []))
            changed = True
        code = self._code()
        actual = digest(code)
        if session.get("code_digest") != actual:
            session["code_digest"] = actual
            changed = True
        if changed:
            self._save(session)
        if session_id is not None and session_id != session["session_id"]:
            raise Conflict(
                "The active problem changed in another window. Your draft is "
                "preserved; compare before saving."
            )
        if revision is not None and revision != session["revision"]:
            raise Conflict(
                "The session changed in another window or in Codex. Your text is "
                "preserved; refresh before saving."
            )
        return session

    def _tick(self, session: dict, now: datetime | None = None):
        now = now or datetime.now(UTC)
        if session.get("phase_started_at"):
            elapsed = max(
                0, (now - datetime.fromisoformat(session["phase_started_at"])).total_seconds()
            )
            phase = session.get("phase", "implementation")
            session.setdefault("timing", {})[phase] = session.get("timing", {}).get(
                phase, 0
            ) + round(elapsed, 3)
            session["phase_started_at"] = now.isoformat()
        session["accumulated_seconds"] = int(sum(session.get("timing", {}).values()))
        session["active_started_at"] = session.get("phase_started_at")

    def _public_problem(self, problem: dict, reveal: bool = False):
        fields = (
            "id",
            "title",
            "prompt",
            "signature",
            "parameters",
            "returns",
            "constraints",
            "examples",
            "estimated_minutes",
            "kind",
            "validator",
        )
        safe = {k: problem[k] for k in fields if k in problem}
        if reveal:
            safe.update(topic=problem["topic"], related_url=problem.get("related_url"))
        return safe

    def state(self) -> dict:
        with self.lock:
            self._restore_portable_practice()
            self._recover_completed()
            raw = core.load_session(self.root)
            session = self._session() if raw else None
            if session:
                session = json.loads(json.dumps(session))
                self._tick(session)
                problem = self._problem(session)
                revealed = bool(session.get("initial_reasoning")) or session["activity"] == "learn"
                session["problem"] = self._public_problem(problem, revealed)
                session["code"] = self._code() if revealed else None
                session["elapsed_seconds"] = sum(session.get("timing", {}).values())
                session["break_suggested"] = (
                    session["elapsed_seconds"] >= policy.settings(self.root)["break_minutes"] * 60
                )
                session["budget_reached"] = (
                    session["elapsed_seconds"] >= session.get("budget_minutes", 60) * 60
                )
                if session["activity"] == "learn":
                    session["worked_explanation"] = problem.get(
                        "worked_explanation", "Trace the example and explain each step."
                    )
            check = self._check_state()
            repair = self._read_local("repair-timer")
            if repair:
                gate = next(
                    (
                        g
                        for g in core.open_repair_gates(self.root)
                        if g["event_id"] == repair["error_id"]
                    ),
                    None,
                )
                if gate:
                    repair = {
                        **repair,
                        "prompt": gate["repair_prompt"],
                        "corrected_rule": gate["corrected_rule"],
                        "problem": self._public_problem(
                            core.problem_by_id(self.root, gate["problem_id"]), True
                        ),
                    }
            return {
                "snapshot": time.monotonic_ns() // 1000,
                "session": session,
                "practice": self.practice_state(),
                "sync": self._read_local(
                    "sync", {"status": "local", "message": "Saved on this computer."}
                ),
                "check": check,
                "completion": self._read_local("last-completion"),
                "repair": repair,
                "remote_attempts": self._read_local("remote-attempts", []),
                "unpublished_count": len(self._unpublished()),
                "local_save": {"status": "saved", "saved_at": (session or {}).get("saved_at")},
                "recovery": [
                    {k: item[k] for k in ("id", "path", "source")}
                    for item in self.store.json_documents(".study-local/conflicts/")
                    if item.get("status") == "unresolved"
                ],
            }

    def plan(self, include_new=False, minutes=None):
        with self.lock:
            result = policy.queue(self.root, include_new=include_new, minutes=minutes)
            for key in ("due", "postponed", "short_recall", "support"):
                result[key] = [self._public_problem(p, key == "support") for p in result[key]]
            if result["main"]:
                result["main"] = self._public_problem(result["main"])
            return result

    def progress(self):
        with self.lock:
            return policy.metrics(self.root)

    def _set_sync(self, status, message):
        result = {"status": status, "message": message}
        self._write_local("sync", result)
        return result

    def _pull(self):
        active = core.load_session(self.root)
        paused_checkpoint = (
            active and not active.get("phase_started_at") and active.get("sync_base")
        )
        wait = bool(paused_checkpoint) or not (
            active or self._read_local("repair-timer") or self._unpublished()
        )
        return self.synchronizer.pull(wait=wait)

    def start(
        self,
        problem_id=None,
        activity="implement",
        include_new=False,
        minutes=None,
        synchronize=True,
        revision=None,
    ):
        if activity not in ACTIVITIES:
            raise RuntimeError("Choose Learn, Recall, Implement, or Transfer.")
        if minutes is not None and not 5 <= minutes <= 180:
            raise RuntimeError("Choose a session budget between 5 and 180 minutes.")
        if synchronize:
            self._pull()
        with self.lock:
            self._recover_completed()
            if self._read_local("remote-attempts") and not core.load_session(self.root):
                return {**self.state(), "message": "Choose a saved attempt before starting."}
            if core.load_session(self.root):
                session = self._session(revision)
                if not session.get("phase_started_at"):
                    session["phase_started_at"] = datetime.now(UTC).isoformat()
                    session["active_started_at"] = session["phase_started_at"]
                    self._save(session)
                return self.state()
            if synchronize and self._read_local("sync", {}).get("status") in {
                "pending",
                "checking",
            }:
                return {
                    **self.state(),
                    "message": (
                        "GitHub could not be verified. Choose Continue locally to start here."
                    ),
                }
            choice = policy.queue(self.root, include_new=include_new, minutes=minutes)
            if problem_id is None:
                if not choice["main"]:
                    return {
                        **self.state(),
                        "message": choice["reason"],
                        "queue": self.plan(include_new, minutes),
                    }
                problem_id, activity = choice["main"]["id"], choice["activity"]
            problem = core.problem_by_id(self.root, problem_id)
            if activity in {"implement", "transfer"} and not policy.eligible(self.root, problem):
                raise RuntimeError(
                    "Practice the prerequisite anchors or relevant repair first. "
                    "Learn mode remains available."
                )
            seen = problem_id in policy.exposures(self.root)
            if (
                not seen
                and choice["weekend"]
                and not (include_new or policy.settings(self.root)["new_on_weekends"])
            ):
                raise RuntimeError(
                    "Weekend review day. Enable new material to open unseen content."
                )
            if activity == "transfer" and seen:
                activity = "implement"
            if problem["kind"] in {"worked", "faded", "warmup"}:
                activity = "learn"
            if self.store.exists("attempt/current.py"):
                raise RuntimeError(
                    "A draft exists without a session. It has been preserved; use "
                    "Recover draft before starting."
                )
            core.start_problem(self.root, problem_id)
            session = core.load_session(self.root)
            now = datetime.now(UTC).isoformat()
            session.update(
                schema_version=7,
                workflow_version=4,
                session_id=uuid.uuid4().hex,
                revision=0,
                activity=activity,
                assessment_mode="independent" if activity == "transfer" else "practice",
                unseen=not seen,
                phase="learning" if activity == "learn" else "recall",
                timing={},
                phase_started_at=now,
                budget_minutes=minutes or policy.settings(self.root)["session_minutes"],
                content_version=problem.get("content_version", 1),
                rubric_version=2,
                skill_ids=[
                    policy.skill_id(s) for s in problem.get("skill_ids", problem.get("skills", []))
                ],
            )
            code = f"def {problem['signature']}:\n    raise NotImplementedError\n"
            if problem.get("validator") == "codec":
                code += (
                    "\n\ndef decode_strings(encoded: str) -> list[str]:\n"
                    "    raise NotImplementedError\n"
                )
            if activity == "learn":
                code = problem.get("starter_code") or code
            session["sync_branch"] = (
                gitflow.attempt_branch(problem_id) + "-" + session["session_id"][:12]
            )
            self._write_local("problem-contracts/" + session["session_id"], problem)
            # The prompt is shown beside the editor; the candidate starts at its signature.
            self.store.write_text("attempt/current.py", code)
            session["code_digest"] = digest(self._code())
            exposure = core._write_learning_event(
                self.root,
                {
                    "event_type": "exposure",
                    "problem_id": problem_id,
                    "session_id": session["session_id"],
                    "activity": activity,
                    "content_version": session["content_version"],
                },
            )
            session.setdefault("learning_event_paths", []).append(
                exposure.relative_to(self.root).as_posix()
            )
            self._delete_local("check")
            self._save(session)
            return self.state()

    def reasoning(self, answer: str, quality="unknown", revision=None, session_id=None, **details):
        if not answer.strip():
            raise RuntimeError(
                "Record your approach, why it fits, and a correctness condition "
                "or edge case. 'I don't know yet' is a valid attempt."
            )
        if quality not in core.RECALL_QUALITIES:
            raise RuntimeError("Unknown recall quality.")
        with self.lock:
            session = self._session(revision, session_id)
            if session.get("initial_reasoning"):
                raise RuntimeError(
                    "Initial reasoning is already recorded. Keep the original evidence."
                )
            if quality == "novel" and session.get("attempt_kind") == "review":
                raise RuntimeError(
                    "For a previously studied problem, record complete, partial, or failed recall."
                )
            self._tick(session)
            session["initial_reasoning"] = {
                "approach": answer.strip(),
                "quality": quality,
                "why": details.get("why") or "Not recorded",
                "invariant": details.get("invariant") or "Not recorded",
                "expected_complexity": details.get("complexity") or "Not recorded",
                "edge_case": details.get("edge_case") or "Not recorded",
                "recorded_at": datetime.now(UTC).isoformat(),
            }
            session["phase"] = (
                "implementation" if session["activity"] in {"implement", "transfer"} else "recall"
            )
            self._save(session)
            return self.state()

    def save_code(self, code: str, revision: int, code_digest: str | None = None, session_id=None):
        if len(code) > 200_000:
            raise RuntimeError("Candidate is too large (limit 200 KB).")
        with self.lock:
            session = self._session(session_id=session_id)
            if revision != session["revision"] and code_digest != session["code_digest"]:
                raise Conflict(
                    "The candidate changed. Preserve your draft and compare before saving."
                )
            if code_digest is not None and code_digest != session["code_digest"]:
                raise Conflict(
                    "Candidate changed externally. Keep your text and compare before saving."
                )
            if not session.get("initial_reasoning") and session["activity"] != "learn":
                raise RuntimeError("Record a compact initial approach first.")
            previous = self._code()
            if previous != code:
                self.store.write_text(
                    f".study-local/drafts/{session['session_id']}-{session['code_digest']}.py",
                    previous,
                )
            self.store.write_text("attempt/current.py", code)
            session["code_digest"] = digest(code)
            self._save(session)
            return self.state()

    def assistance(
        self,
        level,
        summary,
        revision=None,
        source="conversation",
        supplied_missing_recall=False,
        session_id=None,
    ):
        if level not in core.ASSISTANCE_LEVELS or not summary.strip():
            raise RuntimeError("Record the assistance level and what help actually supplied.")
        with self.lock:
            session = self._session(revision, session_id)
            if not session.get("initial_reasoning") and session["activity"] != "learn":
                raise RuntimeError("An initial attempt is required before coaching.")
            if (
                session.get("workflow_version", 0) >= 3
                and session.get("assessment_mode", "independent") == "independent"
                and level in {"guided", "substantial"}
            ):
                raise RuntimeError("Switch to guided practice before substantive help.")
            session.setdefault("assistance_log", []).append(
                {
                    "level": level,
                    "summary": summary,
                    "source": source,
                    "supplied_missing_recall": supplied_missing_recall,
                    "recorded_at": datetime.now(UTC).isoformat(),
                }
            )
            self._save(session)
            return self.state()

    def hint(self, revision=None, retried=False, session_id=None):
        with self.lock:
            session = self._session(revision, session_id)
            if session.get("workflow_version", 0) >= 3:
                if session.get("assessment_mode", "independent") == "independent":
                    raise RuntimeError("Switch to guided practice before revealing a hint.")
                retried = len(session.get("reasoning_retries", [])) > session.get(
                    "last_hint_retry", 0
                )
            if not session.get("initial_reasoning") and session["activity"] != "learn":
                raise RuntimeError("Record your initial attempt before asking for a hint.")
            p = core.problem_by_id(self.root, session["problem_id"])
            used = session.get("hints_used", 0)
            if used >= len(p["hints"]):
                return {
                    "message": "The hint ladder is complete. Ask Codex for a worked example.",
                    **self.state(),
                }
            if (
                used
                and not retried
                and session.get("code_digest") == session.get("last_hint_digest")
            ):
                raise RuntimeError(
                    "Retry the reasoning or code before the next hint; acknowledge a "
                    "reasoning retry when appropriate."
                )
            text = p["hints"][used]
            level = p.get("hint_levels", ["minor", "guided", "substantial"])[used]
            session["hints_used"] = used + 1
            session["last_hint_digest"] = session["code_digest"]
            session["last_hint_retry"] = len(session.get("reasoning_retries", []))
            session.setdefault("assistance_log", []).append(
                {
                    "level": level,
                    "summary": text,
                    "source": "formal_hint",
                    "recorded_at": datetime.now(UTC).isoformat(),
                }
            )
            session.setdefault("revealed_hints", []).append(text)
            self._save(session)
            return {"hint": text, "level": level, **self.state()}

    def worked_example(self, revision=None, session_id=None):
        with self.lock:
            session = self._session(revision, session_id)
            if (
                session.get("workflow_version", 0) >= 3
                and session.get("assessment_mode") != "practice"
            ):
                raise RuntimeError("Switch to guided practice before revealing an example.")
            if not session.get("initial_reasoning"):
                raise RuntimeError("Record an initial attempt before opening a worked example.")
            self._tick(session)
            session.update(activity="learn", phase="learning")
            reference = json.loads(
                (self.root / "curriculum/validation.json").read_text(encoding="utf-8")
            )
            session["worked_example"] = reference[session["problem_id"]]["reference"]
            session.setdefault("assistance_log", []).append(
                {
                    "level": "substantial",
                    "source": "worked_example",
                    "summary": "Studied the complete reference after an initial attempt.",
                    "recorded_at": datetime.now(UTC).isoformat(),
                }
            )
            self._save(session)
            return self.state()

    def phase(self, phase, revision=None, session_id=None):
        if phase not in PHASES:
            raise RuntimeError("Unknown study phase.")
        with self.lock:
            session = self._session(revision, session_id)
            self._tick(session)
            if phase == "administration" and session["phase"] != "administration":
                session["previous_phase"] = session["phase"]
            session["phase"] = phase
            self._save(session)
            return self.state()

    def check(self, revision=None, timeout=10, session_id=None, code_digest=None):
        with self.lock:
            session = self._session(None if code_digest is not None else revision, session_id)
            if code_digest is not None and code_digest != session["code_digest"]:
                raise Conflict(
                    "The candidate changed before the check started. Save and check the "
                    "current code."
                )
            if not session.get("initial_reasoning") and session["activity"] != "learn":
                raise RuntimeError("Record your initial approach first.")
            existing = self._read_local("check", {})
            if (
                existing.get("status") == "running"
                and (
                    datetime.now(UTC) - datetime.fromisoformat(existing["started_at"])
                ).total_seconds()
                < 15
            ):
                raise Conflict("A check is already running.")
            snapshot = dict(session)
            problem = self._problem(session)
            candidate = self.local / f"check-{uuid.uuid4().hex}.py"
            atomic_text(candidate, self._code())
            job = {
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
                "session_id": session["session_id"],
                "code_digest": session["code_digest"],
            }
            self._write_local("check", job)
            (self.local / "stop-check").unlink(missing_ok=True)

        class Cancel:
            def is_set(inner):
                return (self.local / "stop-check").exists()

        try:
            failures = core.run_solution(candidate, problem, min(10, max(0.1, timeout)), Cancel())
        finally:
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass  # Generated check files can be cleaned later; the result remains valid.
        with self.lock:
            session = core.load_session(self.root) or {}
            stale = (
                session.get("session_id") != snapshot["session_id"]
                or session.get("code_digest") != snapshot["code_digest"]
            )
            total = len(problem["cases"])
            failed_all = any(f.index == 0 for f in failures)
            passed = 0 if failed_all else total - len(failures)
            error = next((f.error for f in failures if f.index == 0), None)
            status = (
                "stale"
                if stale
                else (
                    "timeout"
                    if error and "timed out" in error
                    else "stopped"
                    if error and "stopped" in error
                    else "complete"
                )
            )
            result = {
                **job,
                "status": status,
                "passed_cases": passed,
                "total_cases": total,
                "all_passed": passed == total and not stale,
                "failure_count": len(failures),
                "message": (
                    "Code changed during this check; run again."
                    if stale
                    else error or "Check finished."
                ),
                "problem_id": problem["id"],
                "public_failures": [],
            }
            # Only public examples may disclose input/output details.
            public_args = [list(e["inputs"].values()) for e in problem["examples"]]
            for f in failures:
                if f.index > 0 and problem["cases"][f.index - 1]["args"] in public_args:
                    result["public_failures"].append(
                        {
                            "example": public_args.index(problem["cases"][f.index - 1]["args"]) + 1,
                            "error": f.error or "Output did not match the public example.",
                        }
                    )
            if not stale:
                session["checkpoint_count"] = session.get("checkpoint_count", 0) + 1
                if session["checkpoint_count"] == 1:
                    session["first_checkpoint_passed"] = passed == total
                session["latest_checkpoint"] = {
                    "attempt": session["checkpoint_count"],
                    "checked_at": datetime.now(UTC).isoformat(),
                    "passed_cases": passed,
                    "total_cases": total,
                    "code_digest": snapshot["code_digest"],
                    "status": status,
                }
                self._save(session)
            result["checkpoint_count"] = session.get("checkpoint_count", 0)
            self._write_local("check", result)
            return result

    def stop_check(self):
        atomic_text(self.local / "stop-check", "stop")
        return {"message": "Stopping check; your saved code is preserved."}

    def evaluate(self):
        with self.lock:
            session = self._session()
            self._tick(session)
            core.save_session(self.root, session)
            levels = [e["level"] for e in session.get("assistance_log", [])]
            level = max(levels, key=core.ASSISTANCE_LEVELS.index, default="none")
            quality = session.get("recall_self_report", {}).get(
                "quality", session.get("initial_reasoning", {}).get("quality", "unknown")
            )
            initial_quality = session.get("initial_reasoning", {}).get("quality", "unknown")
            failed = quality in {"partial", "failed"} or level in {"guided", "substantial"}
            if session.get("workflow_version", 0) >= 3:
                failed = (
                    initial_quality in {"partial", "failed"}
                    or quality in {"partial", "failed"}
                    or any(
                        e.get("supplied_missing_recall") for e in session.get("assistance_log", [])
                    )
                )
            dimensions = {}
            for finding in session.get("evidence_amendments", []):
                if finding.get("code_digest") == session["code_digest"]:
                    dimensions[finding["dimension"]] = finding["value"]
            failed = failed or dimensions.get("recall") == "failure"
            unknown = (
                session.get("workflow_version", 0) >= 3
                and (quality == "unknown" or dimensions.get("recall") == "unknown")
                and not failed
            )
            recommendation = "unknown" if unknown else "again" if failed else "good"
            latest = session.get("latest_checkpoint", {})
            return {
                "session_id": session["session_id"],
                "revision": session["revision"],
                "problem_id": session["problem_id"],
                "recommended_rating": recommendation,
                "rating_rationale": "Recall is unknown. The scheduling interval stays unchanged."
                if unknown
                else ("Help supplied missing reasoning or initial recall was incomplete.")
                if failed
                else "Independent recall; select Hard, Good, or Easy according to recall effort.",
                "recall_outcome": "unknown" if unknown else "failure" if failed else "success",
                "assistance_level": level,
                "active_minutes": round(sum(session.get("timing", {}).values()) / 60, 2),
                "tests_current": latest.get("code_digest") == session["code_digest"],
                "tests_passed": latest.get("passed_cases", 0) == latest.get("total_cases", -1)
                and latest.get("status") == "complete"
                and latest.get("code_digest") == session["code_digest"],
                "timing": session["timing"],
                "initial_reasoning": session.get("initial_reasoning"),
                "evidence": session.get("evidence_amendments", []),
                "dimensions": dimensions,
                "assessment_before_help": session.get("assessment_before_help"),
                "timing_uncertain": session.get("timing_uncertain"),
                "prompt": "What would you recognize or do differently next time?",
                "unpublished_count": len(self._unpublished()),
                "unpublished_session_ids": [r["session_id"] for r in self._unpublished()],
                "public_repository": "https://github.com/david1534/leetcode-learning-system",
                "files": [
                    "solution or saved unsuccessful candidate",
                    "review evidence",
                    "brief reflection",
                ],
            }

    def pause(self, revision=None, synchronize=True, session_id=None):
        with self.lock:
            session = self._session(revision, session_id)
            self._tick(session)
            session["phase_started_at"] = None
            session["active_started_at"] = None
            self._save(session)
        if synchronize:
            self.synchronizer.enqueue_draft()
        return self.state()

    def _publish_paths(self, paths, problem_id, complete=False):
        return self.synchronizer.enqueue(paths, problem_id, complete=complete)

    def recover(self, conflict_id=None, use_incoming=False):
        with self.lock:
            if conflict_id:
                key = f".study-local/conflicts/{conflict_id}.json"
                item = self.store.read_json(key)
                if not item:
                    raise RuntimeError("Choose a saved conflict to recover.")
                if use_incoming:
                    if item["path"].startswith(
                        ("progress/reviews/", "progress/corrections/", "progress/learning-events/")
                    ):
                        raise RuntimeError(
                            "Historical evidence stays unchanged. "
                            "Keep this version and record a "
                            "correction after comparing the copies."
                        )
                    current = self.store.read_text(item["path"], "")
                    if digest(current) != item["saved_digest"]:
                        raise Conflict("The saved version changed. Compare the drafts again.")
                    self.store.write_text(f".study-local/recovery/{uuid.uuid4().hex}.txt", current)
                    if item.get("recover_session"):
                        if core.load_session(self.root):
                            raise Conflict(
                                "Finish the current problem before recovering this earlier draft."
                            )
                        recovered = {
                            **item["recover_session"],
                            "session_id": uuid.uuid4().hex,
                            "schema_version": 7,
                            "workflow_version": 4,
                            "revision": 0,
                            "activity": "learn",
                            "assessment_mode": "practice",
                            "unseen": False,
                            "timing": {},
                            "accumulated_seconds": 0,
                            "phase": "learning",
                            "phase_started_at": None,
                            "active_started_at": None,
                            "code_digest": digest(item["incoming"]),
                            "recovered_from_session": item["recover_session"]["session_id"],
                        }
                        recovered.pop("latest_checkpoint", None)
                        recovered.pop("practice", None)
                        self._save(recovered)
                    self.store.write_text(item["path"], item["incoming"])
                item["status"] = "resolved"
                self.store.write_json(key, item)
            else:
                # An explicit recovery keeps the old synchronized draft and publishes a new branch.
                session = core.load_session(self.root)
                if session:
                    self._write_local(
                        "recovery/" + uuid.uuid4().hex, {"session": session, "code": self._code()}
                    )
                    for key in self.store.paths(".study-local/outbox/", ".json"):
                        job = self.store.read_json(key)
                        if job["kind"] == "draft" and session["session_id"] in job["session_ids"]:
                            if job["status"] == "running":
                                raise Conflict(
                                    "A draft sync is still running. "
                                    "Retry recovery after it finishes."
                                )
                            if job["status"] == "pending":
                                job["status"] = "deferred"
                                self.store.write_json(key, job)
                    session["sync_branch"] = "attempt/recovered-" + uuid.uuid4().hex[:12]
                    session.pop("sync_base", None)
                    self._save(session)
                elif self.store.exists("attempt/current.py"):
                    self.store.write_text(
                        f"progress/orphan-drafts/{uuid.uuid4().hex}.py", self._code()
                    )
                    self.store.delete_tree("attempt/")
            return self._set_sync("local", "Both drafts are preserved. You can continue locally.")

    def choose_attempt(self, branch):
        return self.synchronizer.choose_attempt(branch)

    def finish(
        self,
        session_id,
        rating,
        takeaway,
        explained=False,
        constraints_met=False,
        minutes=None,
        publish=False,
        revision=None,
        stopped=False,
        recall_confirmed=False,
        expected_session_ids=None,
    ):
        if rating not in {*core.RATINGS, "unknown"}:
            raise RuntimeError("Select Again, Hard, Good, or Easy.")
        if minutes is not None and not 0 < minutes <= 1440:
            raise RuntimeError("Minutes must be between 0 and 1440.")
        with self.lock:
            receipt_path = f".study-local/completions/{session_id}.json"
            # IDs are created by this service, never arbitrary filesystem paths.
            if not isinstance(session_id, str) or not session_id.isalnum() or len(session_id) > 64:
                raise RuntimeError("Invalid session ID.")
            if self.store.exists(receipt_path):
                return self.store.read_json(receipt_path)
            session = self._session(revision)
            if session["session_id"] != session_id:
                raise Conflict("The active session changed; refresh before completion.")
            if self._check_state().get("status") == "running":
                raise RuntimeError("Stop or finish the running check before closing the activity.")
            if recall_confirmed and session.get("initial_reasoning"):
                session["recall_self_report"] = {
                    "quality": "unknown"
                    if rating == "unknown"
                    else "failed"
                    if rating == "again"
                    else "complete",
                    "rating": rating,
                    "recorded_at": datetime.now(UTC).isoformat(),
                }
                self._save(session)
            facts = self.evaluate()
            session = self._session()
            if facts["recall_outcome"] == "unknown":
                rating = "unknown"
            elif rating == "unknown":
                raise RuntimeError("Recall evidence is available; review its suggested rating.")
            explained = explained and facts["dimensions"].get("explanation", "success") == "success"
            constraints_met = (
                constraints_met and facts["dimensions"].get("constraints", "success") == "success"
            )
            if facts["recall_outcome"] == "failure" and rating != "again":
                raise RuntimeError(
                    "Again records the missing independent recall; implementation and"
                    " explanation are scored separately."
                )
            if (
                session["activity"] in {"implement", "transfer"}
                and not facts["tests_passed"]
                and not stopped
            ):
                raise RuntimeError(
                    "Run a current passing check, or choose Stop for today to "
                    "preserve an unsuccessful attempt."
                )
            text = self._code()
            if digest(text) != session["code_digest"]:
                raise Conflict("The candidate changed during completion; rerun its check.")
            self._tick(session)
            timing = session.get("timing", {})
            calculated = sum(timing.values()) / 60
            if minutes is not None and calculated:
                timing = {k: round(v * minutes / calculated, 3) for k, v in timing.items()}
            elif minutes is not None:
                timing = {"unclassified": minutes * 60}
            event = {
                "schema_version": 4,
                "event_id": session_id,
                "session_id": session_id,
                "problem_id": session["problem_id"],
                "topic": core.problem_by_id(self.root, session["problem_id"])["topic"],
                "kind": core.problem_by_id(self.root, session["problem_id"])["kind"],
                "reviewed_at": datetime.now(UTC).isoformat(),
                "recall_at": session.get("initial_reasoning", {}).get("recorded_at"),
                "rating": rating,
                "minutes": round(minutes if minutes is not None else calculated, 3),
                "timing": timing,
                "timing_adjusted": minutes is not None,
                "activity": session["activity"],
                "attempt_kind": session["attempt_kind"],
                "unseen": session["unseen"],
                "recall_outcome": facts["recall_outcome"],
                "recall_quality": session.get("recall_self_report", {}).get(
                    "quality", session.get("initial_reasoning", {}).get("quality", "unknown")
                ),
                "assistance_level": facts["assistance_level"],
                "assistance_count": len(session.get("assistance_log", [])),
                "hints_used": session.get("hints_used", 0),
                "first_checkpoint_passed": session.get("first_checkpoint_passed", False),
                "tests_passed": facts["tests_passed"],
                "explained": explained,
                "assessment": {
                    "constraints_met": constraints_met,
                    "dimensions": facts["dimensions"],
                    "explanation_source": "reviewed_evidence"
                    if "explanation" in facts["dimensions"]
                    else "learner_report",
                    "constraints_source": "reviewed_evidence"
                    if "constraints" in facts["dimensions"]
                    else "learner_report",
                    "status": "stopped" if stopped else "completed",
                },
                "skill_ids": session["skill_ids"],
                "content_version": session["content_version"],
                "rubric_version": 2,
                "scheduler": SCHEDULER,
                "code_digest": session["code_digest"],
            }
            if session.get("workflow_version", 0) >= 3:
                event.update(
                    workflow_version=4,
                    practice_session_id=session.get("practice_session_id"),
                    evidence=session.get("evidence_amendments", []),
                    timing_uncertain=session.get("timing_uncertain"),
                )
                original = session.get("assessment_before_help")
                if original:
                    event.update(
                        activity=original["activity"],
                        unseen=original["unseen"],
                        assessment_before_help=original,
                        tests_passed=False,
                        guided_outcome={"tests_passed": facts["tests_passed"], "activity": "learn"},
                    )
                    event["assessment"]["status"] = "ended_for_help"
            archive = f"progress/attempts/{session_id}"
            self.store.write_text(archive + "/candidate.py", text)
            self.store.write_json(archive + "/session.json", session)
            prior = self.store.read_text("attempt/assessment.py")
            if prior is not None:
                self.store.write_text(archive + "/assessment.py", prior)
            review = f"progress/reviews/{session_id}.json"
            self.store.write_json(review, event)
            reflection = f"reflections/{session['problem_id']}.md"
            reflection_text = (
                "# Learning reflection\n\n"
                f"{takeaway.strip() or 'No takeaway recorded.'}\n\n"
                f"Activity: {session['activity']}. Recall: {rating}. "
                f"Assistance: {facts['assistance_level']}.\n"
                f"Explanation recorded: {explained}. Constraints checked: {constraints_met}.\n"
            )
            self.store.write_text(reflection, reflection_text)
            self.store.write_text(archive + "/reflection.md", reflection_text)
            paths = [archive, review, reflection, *session.get("learning_event_paths", [])]
            if facts["tests_passed"] and session["activity"] in {"implement", "transfer"}:
                solution = f"solutions/{session['problem_id']}.py"
                self.store.write_text(solution, text)
                paths.append(solution)
            summary = self._session_summary(session, event)
            summary_path = f"progress/practice-sessions/{session_id}.json"
            self.store.write_json(summary_path, summary)
            paths.append(summary_path)
            receipt = {
                "session_id": session_id,
                "problem_id": session["problem_id"],
                "event_id": session_id,
                "status": "saved",
                "published": False,
                "paths": paths,
                "message": "Session saved on this computer.",
                "saved_at": event["reviewed_at"],
            }
            self.store.write_json(receipt_path, receipt)
            self._close_attempt(receipt)
        if publish:
            # The local transaction has committed before any export/network work begins.
            try:
                self.publish(
                    session_id, include_saved=True, expected_session_ids=expected_session_ids
                )
            except (RuntimeError, OSError) as exc:
                self._set_sync(
                    "pending", "Session saved locally. Publication needs attention: " + str(exc)
                )
            receipt = self.store.read_json(receipt_path)
        return receipt

    def sync(self, wait=False):
        return self.synchronizer.sync(wait=wait)

    def publish(
        self,
        session_id,
        include_saved=False,
        wait=False,
        expected_session_ids=None,
        session_ids=None,
    ):
        return self.synchronizer.publish(
            session_id,
            include_saved,
            wait=wait,
            expected_session_ids=expected_session_ids,
            session_ids=session_ids,
        )

    def keep_local(self):
        with self.lock:
            for path in self.store.paths(".study-local/outbox/", ".json"):
                job = self.store.read_json(path)
                if job.get("status") == "pending":
                    job["status"] = "deferred"
                    self.store.write_json(path, job)
            return self._set_sync(
                "local", "Saved on this computer. Publication can be requested later."
            )

    def begin_repair(self, error_id):
        with self.lock:
            gate = next(
                (g for g in core.open_repair_gates(self.root) if g["event_id"] == error_id), None
            )
            if not gate or not gate["eligible"]:
                raise RuntimeError("This repair is not eligible yet; allow at least 24 hours.")
            if core.load_session(self.root):
                self.pause(synchronize=False)
                session = self._session()
                self._write_local(
                    "queued-attempts/" + session["session_id"],
                    {
                        "session": session,
                        "code": self._code(),
                        "artifacts": self.store.documents("attempt/"),
                    },
                )
                self.store.delete_tree("attempt/")
            timer = self._read_local("repair-timer", {})
            if timer.get("error_id") != error_id:
                if timer:
                    raise RuntimeError("Finish the saved repair before opening a different one.")
                timer = {
                    "error_id": error_id,
                    "seconds": 0,
                    "application": "",
                    "session_id": uuid.uuid4().hex,
                    "budget_minutes": 15,
                    "revision": 0,
                }
            timer.setdefault("session_id", uuid.uuid4().hex)
            if not timer.get("started_at"):
                timer["started_at"] = datetime.now(UTC).isoformat()
            self._write_local("repair-timer", timer)
            return {"prompt": gate["repair_prompt"], "error_id": error_id}

    def cancel_repair(self, application=""):
        with self.lock:
            timer = self._read_local("repair-timer")
            if timer:
                if timer.get("started_at"):
                    timer["seconds"] = (
                        timer.get("seconds", 0)
                        + (
                            datetime.now(UTC) - datetime.fromisoformat(timer["started_at"])
                        ).total_seconds()
                    )
                timer.update(started_at=None, application=application)
                self._write_local("repair-timer", timer)
            return {"message": "Repair paused; its draft and time are saved."}

    def repair(
        self,
        error_id,
        application,
        passed,
        assistance="none",
        explanation="",
        minutes=None,
        session_id=None,
    ):
        with self.lock:
            timer = self._read_local("repair-timer")
            session_id = session_id or (timer or {}).get("session_id")
            if session_id and self._read_local("completions/" + session_id):
                return self._read_local("completions/" + session_id)
            if timer and timer.get("check", {}).get("status") == "running":
                raise RuntimeError("Stop or finish the repair check before continuing.")
            review = timer.get("coach_review") if timer else None
            if review and (
                review["code_digest"] != digest(application) or review["value"] != "success"
            ):
                passed = False
            if not application.strip():
                raise RuntimeError("Apply the corrected rule to a fresh example.")
            if not timer or timer["error_id"] != error_id:
                if minutes is None:
                    raise RuntimeError("Start the repair timer first, or supply its minutes.")
            elapsed = (
                minutes * 60
                if minutes is not None
                else timer.get("seconds", 0)
                + (
                    max(
                        1,
                        (
                            datetime.now(UTC) - datetime.fromisoformat(timer["started_at"])
                        ).total_seconds(),
                    )
                    if timer.get("started_at")
                    else 0
                )
            )
            if not 0 < elapsed <= 86400:
                raise RuntimeError("Repair time must be positive and no more than one day.")
            path = core.record_repair(
                self.root,
                error_id,
                "Not separately recorded",
                "Assessed through fresh application",
                explanation or "Not separately recorded",
                application,
                passed,
                assistance,
                event_id=session_id,
            )
            event = core.artifact_json(self.root, path)
            event["timing"] = {"repair": round(elapsed, 3)}
            event["minutes"] = round(elapsed / 60, 3)
            event["workflow_version"] = 4
            event["skill_id"] = policy.skill_id(event["skill"])
            event["evidence_version"] = 2
            event["misconception"] = None
            event["recognition_trigger"] = None
            event["why_failed"] = explanation or None
            event["assessment_source"] = (
                "reviewed_coach_judgment" if review else "learner_or_external_coach_report"
            )
            event["assessment"] = review
            event["check"] = timer.get("check") if timer else None
            parent = self._practice()
            event["practice_session_id"] = (
                parent["practice_id"] if parent and parent["status"] == "active" else None
            )
            core.write_artifact(self.root, path, event)
            self._delete_local("repair-timer")
            summary_path = f"progress/practice-sessions/{event['event_id']}.json"
            self.store.write_json(
                summary_path,
                self._session_summary(
                    {"session_id": (timer or {}).get("session_id", event["event_id"])}, event
                ),
            )
            receipt = {
                "session_id": event["event_id"],
                "event_id": event["event_id"],
                "problem_id": event["problem_id"],
                "published": False,
                "status": "saved",
                "paths": [path.relative_to(self.root).as_posix(), summary_path],
                "message": "Repair saved on this computer. Publish when ready.",
            }
            self._write_local("completions/" + event["event_id"], receipt)
            self._write_local("last-completion", receipt)
            return {
                "event_path": path.relative_to(self.root).as_posix(),
                "event_id": event["event_id"],
                "passed": event["passed"],
                "message": "Repair cleared." if event["passed"] else "Repair remains open.",
                "minutes": round(elapsed / 60, 2),
            }
