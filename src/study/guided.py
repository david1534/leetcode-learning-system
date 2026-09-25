"""One-problem workflow, repair operations, and restricted coaching projections."""

from __future__ import annotations

import ast
import hashlib
import uuid
from datetime import UTC, datetime

from study import core
from study.storage import atomic_text


class GuidedSession:
    def _portable_practice(self):
        # Draft snapshots are assembled from the database by Synchronizer.
        return None

    def _restore_portable_practice(self):
        # Legacy portable files are imported transactionally during initialization.
        return None

    def _recover_practice_completion(self):
        return None

    def repair_draft(self, answer, revision=None, session_id=None):
        with self.lock:
            timer = self._read_local("repair-timer")
            if not timer:
                raise RuntimeError("Start an eligible repair first.")
            if session_id is not None and session_id != timer.get("session_id"):
                raise RuntimeError(
                    "The active repair changed. Preserve and compare your application."
                )
            if revision is not None and revision != timer.get("revision", 0):
                from study.service import Conflict

                raise Conflict(
                    "The repair changed in another window. Preserve and compare your answer."
                )
            if len(answer) > 12000:
                raise RuntimeError("Keep the repair application under 12,000 characters.")
            if timer.get("application") != answer:
                if timer.get("application"):
                    self.store.write_text(
                        f".study-local/repair-drafts/{uuid.uuid4().hex}.txt", timer["application"]
                    )
                timer.update(
                    application=answer,
                    revision=timer.get("revision", 0) + 1,
                    code_digest=hashlib.sha256(answer.encode()).hexdigest(),
                )
            self._write_local("repair-timer", timer)
            return self.state()

    def check_repair(self):
        from study.runner import execute

        with self.lock:
            timer = self._read_local("repair-timer")
            if not timer:
                raise RuntimeError("Start a repair first.")
            answer = timer.get("application", "")
            if not any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(answer))):
                raise RuntimeError(
                    "Include an assert for a fresh example in this small coding repair."
                )
            if timer.get("check", {}).get("status") == "running":
                raise RuntimeError("A repair check is already running.")
            snapshot = timer["code_digest"]
            candidate = self.local / f"repair-check-{uuid.uuid4().hex}.py"
            atomic_text(candidate, answer + "\ndef __study_result__():\n    return True\n")
            timer["check"] = {"status": "running", "code_digest": snapshot}
            self._write_local("repair-timer", timer)
            (self.local / "stop-repair-check").unlink(missing_ok=True)

        class Cancel:
            def is_set(inner):
                return (self.local / "stop-repair-check").exists()

        try:
            failures = execute(
                candidate,
                {"function": "__study_result__", "cases": [{"args": [], "expected": True}]},
                cancel=Cancel(),
            )
        finally:
            candidate.unlink(missing_ok=True)
        with self.lock:
            timer = self._read_local("repair-timer")
            if not timer:
                return {"status": "stale"}
            error = failures[0].get("error", "Check failed.") if failures else None
            result = {
                "code_digest": snapshot,
                "all_passed": not failures,
                "source": "learner_authored_assertions",
                "message": error
                or "Your assertions passed; conceptual correctness still needs review.",
                "status": "stale"
                if timer.get("code_digest") != snapshot
                else "timeout"
                if error and "timed out" in error
                else "stopped"
                if error and "stopped" in error
                else "complete",
            }
            timer["check"] = result
            self._write_local("repair-timer", timer)
            return result

    def stop_repair_check(self):
        atomic_text(self.local / "stop-repair-check", "stop")
        return {"message": "Stopping the repair check; your answer is saved."}

    def recover_timing(self):
        with self.lock:
            session = core.load_session(self.root)
            if session and session.get("phase_started_at"):
                session["timing_uncertain"] = {
                    "reason": "App restarted. Confirm any study time since the last save."
                }
                session.update(phase_started_at=None, active_started_at=None)
                self._save(session)
            timer = self._read_local("repair-timer")
            if timer and timer.get("started_at"):
                timer.update(started_at=None, timing_uncertain=True)
                self._write_local("repair-timer", timer)

    def timer_checkpoint(self, pause=False):
        with self.lock:
            session = core.load_session(self.root)
            if session and session.get("phase_started_at"):
                elapsed = (
                    datetime.now(UTC) - datetime.fromisoformat(session["phase_started_at"])
                ).total_seconds()
                if elapsed > 90:
                    session["timing_uncertain"] = {
                        "reason": "Computer sleep or a timer gap detected. Confirm active minutes."
                    }
                    pause = True
                else:
                    self._tick(session)
                if (
                    sum(session.get("timing", {}).values())
                    >= session.get("budget_minutes", 60) * 60
                ):
                    pause = True
                if pause:
                    session.update(phase_started_at=None, active_started_at=None)
                # Timer checkpoints do not change the evidence revision.
                core.save_session(self.root, session)
            timer = self._read_local("repair-timer")
            if timer and timer.get("started_at"):
                now = datetime.now(UTC)
                elapsed = (now - datetime.fromisoformat(timer["started_at"])).total_seconds()
                if elapsed > 90:
                    timer["timing_uncertain"] = True
                    pause = True
                else:
                    timer["seconds"] = timer.get("seconds", 0) + max(0, elapsed)
                timer["started_at"] = None if pause else now.isoformat()
                self._write_local("repair-timer", timer)

    def _practice(self):
        return self.practice_state()

    def _save_practice(self, parent):
        session = core.load_session(self.root)
        if session:
            session["automatic_coaching"] = parent.get("automatic_coaching", False)
            session["coach_checkpoints"] = parent.get("coach_checkpoints", {})
            self._save(session)

    def practice_state(self):
        """Compatibility projection, derived from the one durable current attempt."""
        session = core.load_session(self.root)
        timer = self._read_local("repair-timer")
        if timer:
            seconds = timer.get("seconds", 0)
            if timer.get("started_at"):
                seconds += max(
                    0,
                    (
                        datetime.now(UTC) - datetime.fromisoformat(timer["started_at"])
                    ).total_seconds(),
                )
            return {
                "practice_id": timer.get("session_id", timer["error_id"]),
                "workflow_version": 4,
                "status": "active",
                "index": 0,
                "budget_minutes": timer.get("budget_minutes", 15),
                "elapsed_seconds": seconds,
                "stages": [
                    {
                        "type": "repair",
                        "label": "Apply a corrected rule",
                        "status": "active",
                        "error_id": timer["error_id"],
                    }
                ],
            }
        if not session:
            return None
        self._tick(session)
        return {
            "practice_id": session["session_id"],
            "workflow_version": 4,
            "status": "active",
            "index": 0,
            "budget_minutes": session["budget_minutes"],
            "elapsed_seconds": sum(session.get("timing", {}).values()),
            "automatic_coaching": session.get("automatic_coaching", False),
            "coach_checkpoints": session.get("coach_checkpoints", {}),
            "stages": [{"type": "main", "label": "Current problem", "status": "active"}],
        }

    def _session_summary(self, session, event):
        sid = event["event_id"]
        requests = [
            r
            for r in self.store.json_documents(".study-local/coach/requests/")
            if r.get("session_id") == session["session_id"]
        ]
        return {
            "practice_id": sid,
            "workflow_version": 4,
            "status": "completed",
            "completed_at": event.get("reviewed_at", event.get("recorded_at")),
            "started_at": session.get("started_at"),
            "minutes": event["minutes"],
            "timing": event["timing"],
            "attempt_ids": [sid],
            "main_attempt_id": sid,
            "main_activity": event.get("activity", "repair"),
            "main_was_new": session.get("unseen", False),
            "coaching": {
                "turns": sum(bool(r.get("turn_id")) for r in requests),
                "interruptions": sum(
                    r.get("status") in {"interrupted", "uncertain"} for r in requests
                ),
                "latency_seconds": [
                    r["latency_seconds"] for r in requests if "latency_seconds" in r
                ],
                "escalations": sum(
                    r.get("assistance") in {"guided", "substantial"} for r in requests
                ),
            },
        }

    def practice_start(self, minutes=60, include_new=False, synchronize=True):
        timer = self._read_local("repair-timer")
        if timer:
            self.begin_repair(timer["error_id"])
            return self.state()
        with self.lock:
            if not core.load_session(self.root):
                queued = self.store.paths(".study-local/queued-attempts/", ".json")
                if queued:
                    saved = self.store.read_json(queued[0])
                    for path, text in saved.get("artifacts", {}).items():
                        self.store.write_text(path, text)
                    self.store.write_json("attempt/session.json", saved["session"])
                    self.store.write_text("attempt/current.py", saved["code"])
                    self.store.delete(queued[0])
        result = self.start(minutes=minutes, include_new=include_new, synchronize=synchronize)
        if (
            not result["session"]
            and not result["remote_attempts"]
            and result["sync"]["status"] not in {"checking", "pending", "choice"}
        ):
            eligible = [g for g in self.plan(include_new, minutes)["repairs"] if g["eligible"]]
            if eligible:
                self.begin_repair(eligible[0]["event_id"])
                return self.state()
        return result

    def practice_advance(
        self,
        answer="",
        quality="unknown",
        skip=False,
        passed=False,
        assistance="none",
        revision=None,
        session_id=None,
    ):
        timer = self._read_local("repair-timer")
        if session_id and self._read_local("completions/" + session_id):
            return self.state()
        if timer:
            self.repair_draft(answer, revision, session_id)
            if skip:
                with self.lock:
                    self.cancel_repair(answer)
                    self._write_local(
                        "repair-drafts/" + uuid.uuid4().hex, self._read_local("repair-timer")
                    )
                    self._delete_local("repair-timer")
            else:
                self.repair(timer["error_id"], answer, passed, assistance)
            return self.state()
        session = self._session(revision, session_id)
        if session["activity"] != "recall":
            raise RuntimeError("Finish this problem from its completion summary.")
        if not skip and not session.get("initial_reasoning"):
            self.reasoning(answer, quality)
        self.finish(
            session["session_id"], self.evaluate()["recommended_rating"], answer, stopped=True
        )
        return self.state()

    def practice_pause(self):
        with self.lock:
            if core.load_session(self.root):
                self.pause(synchronize=False)
            else:
                self.cancel_repair(self._read_local("repair-timer", {}).get("application", ""))
        self.synchronizer.enqueue_draft()
        return self.state()

    def practice_finish(
        self,
        session_id,
        rating,
        takeaway="",
        explained=False,
        constraints_met=False,
        minutes=None,
        publish=False,
        revision=None,
        stopped=False,
        recall_confirmed=False,
        expected_session_ids=None,
    ):
        return self.finish(
            session_id,
            rating,
            takeaway,
            explained,
            constraints_met,
            minutes,
            publish,
            revision,
            stopped,
            recall_confirmed,
            expected_session_ids,
        )

    def convert_to_practice(self, revision=None, session_id=None):
        with self.lock:
            session = self._session(revision, session_id)
            if session.get("assessment_mode") == "practice":
                return self.state()
            if not session.get("initial_reasoning"):
                raise RuntimeError("Record an initial attempt, including 'I don't know yet'.")
            self._tick(session)
            session["assessment_before_help"] = {
                "activity": session["activity"],
                "unseen": session["unseen"],
                "ended_at": datetime.now(UTC).isoformat(),
                "status": "ended_for_help",
                "initial_reasoning": session["initial_reasoning"],
                "code_digest": session["code_digest"],
                "latest_checkpoint": session.get("latest_checkpoint"),
                "timing": dict(session["timing"]),
            }
            self.store.write_text("attempt/assessment.py", self._code())
            session.update(assessment_mode="practice", activity="learn", phase="learning")
            self._save(session)
            return self.state()

    def record_retry(self, answer, revision=None, session_id=None):
        if len(answer.strip()) < 12:
            raise RuntimeError("Record the new reasoning you tried, in a short sentence.")
        with self.lock:
            session = self._session(revision, session_id)
            previous = session.get("reasoning_retries", [])
            if previous and previous[-1]["answer"] == answer.strip():
                raise RuntimeError("Describe a new attempt rather than repeating the last one.")
            session.setdefault("reasoning_retries", []).append(
                {"answer": answer.strip(), "recorded_at": datetime.now(UTC).isoformat()}
            )
            self._save(session)
            return self.state()

    def evidence(self, findings, revision=None, session_id=None):
        with self.lock:
            session = self._session(revision, session_id)
            allowed = {"recall", "explanation", "constraints", "misconception"}
            for finding in findings:
                if finding.get("dimension") not in allowed or finding.get("value") not in {
                    "success",
                    "failure",
                    "unknown",
                }:
                    raise RuntimeError("Invalid evidence finding.")
                session.setdefault("evidence_amendments", []).append(
                    {
                        **finding,
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "code_digest": session["code_digest"],
                    }
                )
            self._save(session)
            return self.state()

    def coach_context(self):
        with self.lock:
            state = self.state()
            timer = state.get("repair")
            if timer:
                gate = next(
                    (
                        g
                        for g in core.open_repair_gates(self.root)
                        if g["event_id"] == timer["error_id"]
                    ),
                    None,
                )
                if not gate:
                    raise RuntimeError("This repair is no longer open.")
                return {
                    "session_id": timer.get("session_id")
                    or ("repair" + hashlib.sha256(timer["error_id"].encode()).hexdigest()[:24]),
                    "revision": timer.get("revision", 0),
                    "code_digest": timer.get("code_digest", ""),
                    "mode": "repair",
                    "activity": "repair",
                    "policy_version": 1,
                    "problem": {
                        "prompt": gate["repair_prompt"],
                        "corrected_rule": gate["corrected_rule"],
                    },
                    "reasoning": {"approach": timer.get("application", "")},
                    "code": "",
                    "check": timer.get("check", {}),
                    "minutes_remaining": max(0, 5 - timer.get("seconds", 0) / 60),
                }
            session = state["session"]
            if not session:
                raise RuntimeError("Open an exercise before asking the coach.")
            independent = session.get("assessment_mode", "independent") == "independent"
            code = session.get("code")
            if independent and code and code.startswith('"""'):
                header, separator, body = code[3:].partition('"""')
                if (
                    separator
                    and "Related practice\n" in header
                    and "Function signature\n" in header
                ):
                    # Legacy starter headers contain identifying links. Keep only learner code.
                    code = body.lstrip("\n")
            p = session["problem"]
            prompt = {k: p[k] for k in ("prompt", "signature", "constraints", "examples") if k in p}
            check = state["check"] or {}
            safe_check = {
                k: check[k]
                for k in (
                    "status",
                    "all_passed",
                    "passed_cases",
                    "total_cases",
                    "public_failures",
                    "code_digest",
                )
                if k in check
            }
            # Deliberately exclude revealing IDs, skill rubrics and archived solutions.
            memory = []
            if not independent:
                for event in core.effective_events(self.root)[-12:]:
                    if (
                        event.get("topic")
                        == core.problem_by_id(self.root, session["problem_id"])["topic"]
                    ):
                        path = self.root / "progress/attempts" / event["event_id"] / "reflection.md"
                        text = core.artifact_text(self.root, path)
                        if text:
                            memory.append(text[:1000])
            return {
                "session_id": session["session_id"],
                "revision": session["revision"],
                "code_digest": session["code_digest"],
                "policy_version": 1,
                "mode": "assessment" if independent else "practice",
                "problem": prompt,
                "reasoning": session.get("initial_reasoning"),
                "code": code,
                "retries": session.get("reasoning_retries", []),
                "check": safe_check,
                "takeaways": memory[-3:],
                "activity": session["activity"],
                "minutes_remaining": max(
                    0, session["budget_minutes"] - session["elapsed_seconds"] / 60
                ),
            }
