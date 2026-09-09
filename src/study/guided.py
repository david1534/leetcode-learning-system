"""Guided session operations mixed into the single StudyService boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import uuid
from datetime import UTC, datetime

from study import core, policy
from study.storage import atomic_json, atomic_text


class GuidedSession:
    def _portable_practice(self):
        parent = self._read_local("practice")
        if not parent or parent["status"] != "active":
            return
        artifacts = {}
        receipts = {}
        for sid in [*parent.get("receipts", []), *parent.get("repair_receipts", [])]:
            receipt = self._read_local("completions/" + sid)
            if not receipt:
                continue
            receipts[sid] = receipt
            for value in receipt["paths"]:
                if value == "attempt":
                    continue
                path = self.root / value
                for file in path.rglob("*") if path.is_dir() else [path]:
                    if file.is_file():
                        artifacts[file.relative_to(self.root).as_posix()] = file.read_text(
                            encoding="utf-8"
                        )
        timer = self._read_local("repair-timer")
        if timer:
            for gate in core.open_repair_gates(self.root):
                if gate["event_id"] == timer["error_id"]:
                    # The error event is needed to restore the repair on another computer.
                    for file in (self.root / "progress/learning-events").glob("*.json"):
                        if (
                            json.loads(file.read_text(encoding="utf-8"))["event_id"]
                            == timer["error_id"]
                        ):
                            artifacts[file.relative_to(self.root).as_posix()] = file.read_text(
                                encoding="utf-8"
                            )
        atomic_json(
            self.root / "attempt/practice.json",
            {"parent": parent, "repair": timer, "receipts": receipts, "artifacts": artifacts},
        )

    def _restore_portable_practice(self):
        path = self.root / "attempt/practice.json"
        if not path.exists():
            return
        saved = json.loads(path.read_text(encoding="utf-8"))
        current = self._read_local("practice")
        if current and current.get("practice_id") == saved["parent"]["practice_id"]:
            return
        for value, text in saved.get("artifacts", {}).items():
            target = (self.root / value).resolve()
            if not target.is_relative_to(self.root) or not value.startswith(
                (
                    "progress/reviews/",
                    "progress/attempts/",
                    "progress/learning-events/",
                    "reflections/",
                    "solutions/",
                )
            ):
                raise RuntimeError(
                    "The saved session contains an invalid artifact path. "
                    "Keep the draft for recovery."
                )
            if target.exists() and target.read_text(encoding="utf-8") != text:
                atomic_text(self.local / "conflicts" / value, text)
                raise RuntimeError(
                    "A supporting artifact differs on this computer. Both versions are preserved "
                    "in local conflicts; resolve it before resuming."
                )
            atomic_text(target, text)
        for sid, receipt in saved.get("receipts", {}).items():
            if not sid.isalnum():
                raise RuntimeError("The saved session has an invalid receipt ID.")
            atomic_json(self.local / "completions" / f"{sid}.json", receipt)
        atomic_json(self.local / "practice.json", saved["parent"])
        if saved.get("repair"):
            timer = saved["repair"]
            timer["started_at"] = None
            atomic_json(self.local / "repair-timer.json", timer)

    def repair_draft(self, answer, revision=None):
        with self.lock:
            timer = self._read_local("repair-timer")
            if not timer:
                raise RuntimeError("Start an eligible repair first.")
            if revision is not None and revision != timer.get("revision", 0):
                from study.service import Conflict

                raise Conflict(
                    "The repair changed in another window. Preserve and compare your answer."
                )
            if len(answer) > 12000:
                raise RuntimeError("Keep the repair application under 12,000 characters.")
            if timer.get("application") != answer:
                if timer.get("application"):
                    atomic_text(
                        self.local / "repair-drafts" / f"{uuid.uuid4().hex}.txt",
                        timer["application"],
                    )
                timer.update(
                    application=answer,
                    revision=timer.get("revision", 0) + 1,
                    code_digest=hashlib.sha256(answer.encode()).hexdigest(),
                )
            atomic_json(self.local / "repair-timer.json", timer)
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
            atomic_json(self.local / "repair-timer.json", timer)
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
            atomic_json(self.local / "repair-timer.json", timer)
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
                atomic_json(self.local / "repair-timer.json", timer)

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
                atomic_json(self.local / "repair-timer.json", timer)

    def _practice(self):
        parent = self._read_local("practice")
        if parent:
            completed = self.root / "progress/practice-sessions" / f"{parent['practice_id']}.json"
            if completed.exists():
                parent = json.loads(completed.read_text(encoding="utf-8"))
                if self._read_local("practice") != parent:
                    atomic_json(self.local / "practice.json", parent)
                return parent
        session = core.load_session(self.root)
        if (
            session
            and session.get("practice")
            and (
                not parent
                or parent.get("status") == "completed"
                or parent["practice_id"] != session["practice"]["practice_id"]
            )
        ):
            parent = session["practice"]
            atomic_json(self.local / "practice.json", parent)
        return parent

    def _save_practice(self, parent):
        atomic_json(self.local / "practice.json", parent)
        session = core.load_session(self.root)
        if session:
            session["practice"] = parent
            session["practice_session_id"] = parent["practice_id"]
            session["workflow_version"] = 3
            self._save(session)

    def practice_state(self):
        parent = self._practice()
        if not parent:
            return None
        result = json.loads(json.dumps(parent))
        seconds = sum(parent.get("timing", {}).values())
        if parent["status"] != "completed":
            for sid in parent.get("attempt_ids", []):
                path = self.root / "progress/reviews" / f"{sid}.json"
                if path.exists():
                    seconds += sum(json.loads(path.read_text(encoding="utf-8"))["timing"].values())
            for value in parent.get("repair_paths", []):
                seconds += sum(
                    json.loads((self.root / value).read_text(encoding="utf-8"))["timing"].values()
                )
            session = core.load_session(self.root)
            if session:
                self._tick(session)
                seconds += sum(session.get("timing", {}).values())
            timer = self._read_local("repair-timer", {})
            seconds += timer.get("seconds", 0)
            if timer.get("started_at"):
                seconds += max(
                    0,
                    (
                        datetime.now(UTC) - datetime.fromisoformat(timer["started_at"])
                    ).total_seconds(),
                )
        result["elapsed_seconds"] = seconds
        # The browser needs stage labels, not revealing assessment identifiers.
        for stage in result["stages"]:
            stage.pop("problem_id", None)
        return result

    def practice_start(self, minutes=60, include_new=False, synchronize=True):
        with self.lock:
            if synchronize:
                self._pull()
            self._restore_portable_practice()
            parent = self._practice()
            if parent and parent["status"] != "completed":
                parent["include_new"] = parent["include_new"] or include_new
                self._save_practice(parent)
                if core.load_session(self.root):
                    self.start(synchronize=False)
                elif parent["stages"][parent["index"]]["type"] == "repair":
                    self.begin_repair(parent["stages"][parent["index"]]["error_id"])
                else:
                    self._open_practice_stage(parent)
                return self.state()
            existing = core.load_session(self.root)
            choice = self.plan(include_new, minutes)
            stages = []
            if existing:
                main = {"problem_id": existing["problem_id"], "activity": existing["activity"]}
            elif choice["main"]:
                main = {"problem_id": choice["main"]["id"], "activity": choice["activity"]}
                if minutes >= 45 and choice["activity"] != "transfer":
                    gates = [g for g in choice["repairs"] if g["eligible"]]
                    if gates:
                        stages.append(
                            {
                                "type": "repair",
                                "error_id": gates[0]["event_id"],
                                "label": "Apply a corrected rule",
                                "minutes": 5,
                            }
                        )
                    if choice["short_recall"]:
                        stages.append(
                            {
                                "type": "recall",
                                "activity": "recall",
                                "problem_id": choice["short_recall"][0]["id"],
                                "label": "Brief retrieval",
                                "minutes": 5,
                            }
                        )
            elif any(g["eligible"] for g in choice["repairs"]):
                gate = next(g for g in choice["repairs"] if g["eligible"])
                stages.append(
                    {
                        "type": "repair",
                        "error_id": gate["event_id"],
                        "label": "Apply a corrected rule",
                        "minutes": min(5, minutes),
                    }
                )
                main = {"problem_id": None, "activity": "implement"}
            else:
                return {**self.state(), "message": choice["reason"]}
            stages.append({"type": "main", **main, "label": "Main activity", "minutes": minutes})
            parent = {
                "practice_id": uuid.uuid4().hex,
                "workflow_version": 3,
                "started_at": datetime.now(UTC).isoformat(),
                "budget_minutes": minutes,
                "include_new": include_new,
                "status": "active",
                "index": 0,
                "stages": [{**s, "status": "pending"} for s in stages],
                "attempt_ids": [],
                "repair_paths": [],
                "timing": {},
                "receipts": [],
                "automatic_coaching": True,
                "main_was_new": main["problem_id"] not in policy.exposures(self.root)
                if not existing
                else existing.get("unseen", False),
            }
            self._save_practice(parent)
            if existing:
                parent["stages"][0]["status"] = "active"
                self._save_practice(parent)
                self.start(synchronize=False)
            else:
                self._open_practice_stage(parent)
            return self.state()

    def _open_practice_stage(self, parent):
        stage = parent["stages"][parent["index"]]
        if stage["type"] == "repair":
            self.begin_repair(stage["error_id"])
        else:
            if not stage.get("problem_id"):
                choice = self.plan(parent["include_new"], parent["budget_minutes"])
                if not choice["main"]:
                    stage["status"] = "pending"
                    self._save_practice(parent)
                    return
                stage.update(problem_id=choice["main"]["id"], activity=choice["activity"])
                parent["main_was_new"] = stage["problem_id"] not in policy.exposures(self.root)
            self.start(
                stage["problem_id"],
                activity=stage["activity"],
                include_new=parent["include_new"],
                minutes=parent["budget_minutes"],
                synchronize=False,
            )
            session = self._session()
            session["assessment_mode"] = (
                "practice" if session["activity"] == "learn" else "independent"
            )
            self._save(session)
        stage["status"] = "active"
        self._save_practice(parent)

    def practice_advance(
        self,
        answer="",
        quality="complete",
        skip=False,
        passed=False,
        assistance="none",
        revision=None,
    ):
        with self.lock:
            parent = self._practice()
            if not parent or parent["status"] == "completed":
                raise RuntimeError("Start a guided session first.")
            stage = parent["stages"][parent["index"]]
            if stage["type"] == "main":
                raise RuntimeError("Finish the main activity through its review summary.")
            if stage["type"] == "repair":
                if skip:
                    self.cancel_repair(answer)
                    timer = self._read_local("repair-timer", {})
                    parent["timing"]["repair"] = parent["timing"].get("repair", 0) + timer.get(
                        "seconds", 0
                    )
                    # Draft remains recoverable; this session resumes its main activity.
                    atomic_json(self.local / "skipped-repair.json", timer)
                    (self.local / "repair-timer.json").unlink(missing_ok=True)
                else:
                    result = self.repair(stage["error_id"], answer, passed, assistance)
                    parent["repair_paths"].append(result["event_path"])
                    parent["repair_receipts"] = [
                        *parent.get("repair_receipts", []),
                        result["event_id"],
                    ]
            else:
                session = self._session(revision)
                if not skip and not session.get("initial_reasoning"):
                    self.reasoning(answer, quality)
                facts = self.evaluate()
                receipt = self.finish(
                    session["session_id"],
                    facts["recommended_rating"],
                    answer or "Supporting retrieval skipped.",
                    stopped=True,
                )
                parent["attempt_ids"].append(receipt["session_id"])
                parent["receipts"].append(receipt["session_id"])
            stage["status"] = "skipped" if skip else "completed"
            parent["index"] += 1
            self._save_practice(parent)
            self._open_practice_stage(parent)
            return self.state()

    def practice_pause(self):
        with self.lock:
            if core.load_session(self.root):
                self.pause(synchronize=False)
                self._portable_practice()
                return self.pause()
            self.cancel_repair(self._read_local("repair-timer", {}).get("application", ""))
            self._portable_practice()
            parent = self._practice()
            if parent:
                self._publish_paths(["attempt"], "guided-session")
            return self.state()

    def practice_finish(
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
    ):
        with self.lock:
            parent = self._practice()
            if not parent:
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
                )
            if parent["status"] == "completed":
                return self._read_local("completions/" + parent["practice_id"])
            stage = parent["stages"][parent["index"]]
            if stage["type"] != "main":
                raise RuntimeError("Continue or skip the supporting activity first.")
            if minutes is not None and not 0 < minutes <= 1440:
                raise RuntimeError("Minutes must be positive and at most 1440.")
            receipt = self.finish(
                session_id,
                rating,
                takeaway,
                explained,
                constraints_met,
                None,
                False,
                revision,
                stopped,
            )
            parent["attempt_ids"] = list(dict.fromkeys([*parent["attempt_ids"], session_id]))
            parent["receipts"] = list(dict.fromkeys([*parent["receipts"], session_id]))
            parent.update(status="completed", completed_at=datetime.now(UTC).isoformat())
            stage["status"] = "completed"
            paths = list(parent["repair_paths"])
            for sid in parent["receipts"]:
                saved = self._read_local("completions/" + sid)
                if saved:
                    paths.extend(saved["paths"])
                event = json.loads(
                    (self.root / "progress/reviews" / f"{sid}.json").read_text(encoding="utf-8")
                )
                for phase, seconds in event.get("timing", {}).items():
                    parent["timing"][phase] = parent["timing"].get(phase, 0) + seconds
            for path in parent["repair_paths"]:
                event = json.loads((self.root / path).read_text(encoding="utf-8"))
                for phase, seconds in event.get("timing", {}).items():
                    parent["timing"][phase] = parent["timing"].get(phase, 0) + seconds
            parent["receipts"] = list(
                dict.fromkeys([*parent["receipts"], *parent.get("repair_receipts", [])])
            )
            parent["minutes"] = sum(parent["timing"].values()) / 60
            if minutes is not None:
                parent["reported_minutes"] = minutes
                parent["timing"]["unclassified_adjustment"] = (minutes - parent["minutes"]) * 60
                parent["minutes"] = minutes
            parent["main_attempt_id"] = session_id
            parent["main_activity"] = stage["activity"]
            requests = [
                json.loads(p.read_text(encoding="utf-8"))
                for p in (self.local / "coach/requests").glob("*.json")
            ]
            requests = [r for r in requests if r["session_id"] in parent["attempt_ids"]]
            parent["coaching"] = {
                "turns": sum(r.get("turn_id") is not None for r in requests),
                "interruptions": sum(r["status"] in {"interrupted", "uncertain"} for r in requests),
                "latency_seconds": [
                    r["latency_seconds"] for r in requests if "latency_seconds" in r
                ],
                "escalations": sum(
                    r.get("assistance") in {"guided", "substantial"} for r in requests
                ),
            }
            path = f"progress/practice-sessions/{parent['practice_id']}.json"
            atomic_json(self.root / path, parent)
            paths.append(path)
            receipt = {
                "session_id": parent["practice_id"],
                "problem_id": receipt["problem_id"],
                "event_id": parent["practice_id"],
                "status": "saved",
                "published": False,
                "paths": list(dict.fromkeys(paths)),
                "child_receipts": parent["receipts"],
                "message": "Your complete practice session is saved locally.",
            }
            atomic_json(self.local / "completions" / f"{parent['practice_id']}.json", receipt)
            for sid in parent["receipts"]:
                child = self._read_local("completions/" + sid)
                if child:
                    child["grouped_into"] = parent["practice_id"]
                    atomic_json(self.local / "completions" / f"{sid}.json", child)
            self._save_practice(parent)
            atomic_json(self.local / "last-completion.json", receipt)
            if publish:
                result = self.publish(parent["practice_id"], include_saved=True)
                receipt.update(published=result["status"] == "synced", message=result["message"])
            return receipt

    def convert_to_practice(self, revision=None):
        with self.lock:
            session = self._session(revision)
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
            atomic_text(
                self.root / "attempt/assessment.py",
                (self.root / "attempt/current.py").read_text(encoding="utf-8"),
            )
            session.update(assessment_mode="practice", activity="learn", phase="learning")
            self._save(session)
            return self.state()

    def record_retry(self, answer, revision=None):
        if len(answer.strip()) < 12:
            raise RuntimeError("Record the new reasoning you tried, in a short sentence.")
        with self.lock:
            session = self._session(revision)
            previous = session.get("reasoning_retries", [])
            if previous and previous[-1]["answer"] == answer.strip():
                raise RuntimeError("Describe a new attempt rather than repeating the last one.")
            session.setdefault("reasoning_retries", []).append(
                {"answer": answer.strip(), "recorded_at": datetime.now(UTC).isoformat()}
            )
            self._save(session)
            return self.state()

    def evidence(self, findings, revision=None):
        with self.lock:
            session = self._session(revision)
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
                    "session_id": "repair"
                    + hashlib.sha256(timer["error_id"].encode()).hexdigest()[:24],
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
                        if path.exists():
                            memory.append(path.read_text(encoding="utf-8")[:1000])
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
