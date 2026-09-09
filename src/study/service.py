"""The one mutation boundary used by both app and coach commands."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from study import core, gitflow, policy
from study.guided import GuidedSession
from study.storage import atomic_json, atomic_text

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
        self.local = self.root / ".study-local"
        self.local.mkdir(exist_ok=True)
        self.lock = FileLock(str(self.local / "session.lock"), timeout=25)

    def _recover_completed(self):
        session = core.load_session(self.root)
        if session and session.get("session_id"):
            receipt = self._read_local("completions/" + session["session_id"])
            if receipt:
                self._close_attempt(receipt)

    def _close_attempt(self, receipt):
        active = self.root / "attempt"
        session = core.load_session(self.root)
        if session and session.get("session_id") == receipt["session_id"]:
            # A durable receipt guarantees both archive and event were written first.
            shutil.rmtree(active)
        atomic_json(self.local / "last-completion.json", receipt)

    def _check_state(self):
        check = self._read_local("check", {})
        if check.get("status") == "running":
            age = (datetime.now(UTC) - datetime.fromisoformat(check["started_at"])).total_seconds()
            if age > 15:
                check.update(status="interrupted", message="Check interrupted; run again.")
                atomic_json(self.local / "check.json", check)
        return check

    def _read_local(self, name: str, default=None):
        path = self.local / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def _unpublished(self):
        receipts = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in (self.local / "completions").glob("*.json")
        ]
        return [r for r in receipts if not r.get("published") and not r.get("grouped_into")]

    def _save(self, session: dict):
        parent = self._read_local("practice")
        if parent and parent.get("status") == "active":
            session["practice"] = parent
            session["practice_session_id"] = parent["practice_id"]
            session["workflow_version"] = 3
        session["revision"] = session.get("revision", 0) + 1
        core.save_session(self.root, session)

    def _session(self, revision: int | None = None) -> dict:
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
            problem = core.problem_by_id(self.root, session["problem_id"])
            session.setdefault("attempt_kind", "review")
            session.setdefault("budget_minutes", policy.settings(self.root)["session_minutes"])
            session.setdefault("content_version", problem.get("content_version", 1))
            session.setdefault("skill_ids", problem.get("skill_ids", []))
            changed = True
        path = self.root / "attempt" / "current.py"
        code = path.read_text(encoding="utf-8") if path.exists() else ""
        actual = digest(code)
        if session.get("code_digest") != actual:
            session["code_digest"] = actual
            changed = True
        if changed:
            self._save(session)
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
        if not reveal:
            safe["title"] = "Practice problem"
        else:
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
                problem = core.problem_by_id(self.root, session["problem_id"])
                revealed = bool(session.get("initial_reasoning")) or session["activity"] == "learn"
                session["problem"] = self._public_problem(problem, revealed)
                session["code"] = (
                    (self.root / "attempt/current.py").read_text(encoding="utf-8")
                    if revealed
                    else None
                )
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
                repair["elapsed_seconds"] = repair.get("seconds", 0)
                if repair.get("started_at"):
                    repair["elapsed_seconds"] += max(
                        0,
                        (
                            datetime.now(UTC) - datetime.fromisoformat(repair["started_at"])
                        ).total_seconds(),
                    )
            practice = self.practice_state()
            return {
                "observed_at": datetime.now(UTC).isoformat(timespec="microseconds"),
                "session": session,
                "practice": practice,
                "sync": self._read_local(
                    "sync", {"status": "local", "message": "Saved on this computer."}
                ),
                "check": check,
                "completion": self._read_local("last-completion"),
                "repair": repair,
                "remote_attempts": self._read_local("remote-attempts", []),
                "unpublished_count": len(self._unpublished()),
            }

    def plan(self, include_new=False, minutes=None):
        result = policy.queue(self.root, include_new=include_new, minutes=minutes)
        for key in ("due", "postponed", "short_recall", "support"):
            result[key] = [self._public_problem(p, key == "support") for p in result[key]]
        if result["main"]:
            result["main"] = self._public_problem(result["main"])
        return result

    def _set_sync(self, status, message):
        result = {"status": status, "message": message}
        atomic_json(self.local / "sync.json", result)
        return result

    def _pull(self):
        if not (self.root / ".git").exists():
            return
        try:
            name = gitflow.branch_name(self.root)
            if name.startswith("attempt/"):
                gitflow.update_current_attempt(self.root)
            elif name == "main":
                gitflow.fast_forward_main(self.root)
                attempts = gitflow.remote_attempts(self.root)
                if len(attempts) > 1:
                    atomic_json(self.local / "remote-attempts.json", attempts)
                    self._set_sync("choice", "Several saved attempts exist. Choose one to resume.")
                    return
                atomic_json(self.local / "remote-attempts.json", [])
                if attempts:
                    gitflow.switch_to_remote_attempt(self.root, attempts[0])
            else:
                raise gitflow.GitFlowError(
                    "This is a development branch. Local practice is available; sync "
                    "from main after the app update is merged."
                )
            self._set_sync("synced", "Up to date with GitHub.")
        except gitflow.GitFlowError as exc:
            self._set_sync("pending", str(exc))

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
        with self.lock:
            self._recover_completed()
            if synchronize:
                self._pull()
            if self._read_local("remote-attempts") and not core.load_session(self.root):
                return {**self.state(), "message": "Choose a saved attempt before starting."}
            if core.load_session(self.root):
                session = self._session(revision)
                if not session.get("phase_started_at"):
                    session["phase_started_at"] = datetime.now(UTC).isoformat()
                    session["active_started_at"] = session["phase_started_at"]
                    self._save(session)
                return self.state()
            if self._read_local("pending"):
                raise RuntimeError(
                    "A completed session awaits publication. Publish it or keep it "
                    "local from the completion card before starting another."
                )
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
            if (self.root / "attempt/current.py").exists():
                raise RuntimeError(
                    "A draft exists without a session. It has been preserved; use "
                    "Recover draft before starting."
                )
            core.start_problem(self.root, problem_id)
            session = core.load_session(self.root)
            now = datetime.now(UTC).isoformat()
            session.update(
                schema_version=6,
                workflow_version=3,
                session_id=uuid.uuid4().hex,
                revision=0,
                activity=activity,
                assessment_mode="practice" if activity == "learn" else "independent",
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
            # The prompt is already visible beside the editor; start at the implementation.
            atomic_text(self.root / "attempt/current.py", code)
            session["code_digest"] = digest(
                (self.root / "attempt/current.py").read_text(encoding="utf-8")
            )
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
            self._save(session)
            return self.state()

    def reasoning(self, answer: str, quality="complete", revision=None, **details):
        if not answer.strip():
            raise RuntimeError(
                "Record your approach, why it fits, and a correctness condition "
                "or edge case. 'I don't know yet' is a valid attempt."
            )
        if quality not in core.RECALL_QUALITIES:
            raise RuntimeError("Unknown recall quality.")
        with self.lock:
            session = self._session(revision)
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

    def save_code(
        self,
        code: str,
        revision: int,
        code_digest: str | None = None,
        session_id: str | None = None,
    ):
        if len(code) > 200_000:
            raise RuntimeError("Candidate is too large (limit 200 KB).")
        with self.lock:
            session = self._session()
            if session_id is not None and session_id != session["session_id"]:
                raise Conflict(
                    "The active exercise changed. Preserve your draft before continuing."
                )
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
            previous = (self.root / "attempt/current.py").read_text(encoding="utf-8")
            if previous != code:
                atomic_text(
                    self.local / "drafts" / f"{session['session_id']}-{session['code_digest']}.py",
                    previous,
                )
            atomic_text(self.root / "attempt/current.py", code)
            session["code_digest"] = digest(code)
            self._save(session)
            return self.state()

    def assistance(
        self, level, summary, revision=None, source="conversation", supplied_missing_recall=False
    ):
        if level not in core.ASSISTANCE_LEVELS or not summary.strip():
            raise RuntimeError("Record the assistance level and what help actually supplied.")
        with self.lock:
            session = self._session(revision)
            if not session.get("initial_reasoning") and session["activity"] != "learn":
                raise RuntimeError("An initial attempt is required before coaching.")
            if (
                session.get("workflow_version") == 3
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

    def hint(self, revision=None, retried=False):
        with self.lock:
            session = self._session(revision)
            if session.get("workflow_version") == 3:
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

    def worked_example(self, revision=None):
        with self.lock:
            session = self._session(revision)
            if (
                session.get("workflow_version") == 3
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

    def phase(self, phase, revision=None):
        if phase not in PHASES:
            raise RuntimeError("Unknown study phase.")
        with self.lock:
            session = self._session(revision)
            self._tick(session)
            session["phase"] = phase
            self._save(session)
            return self.state()

    def check(self, revision=None, timeout=10):
        with self.lock:
            session = self._session(revision)
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
            problem = core.problem_by_id(self.root, session["problem_id"])
            candidate = self.local / f"check-{uuid.uuid4().hex}.py"
            atomic_text(candidate, (self.root / "attempt/current.py").read_text(encoding="utf-8"))
            job = {
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
                "session_id": session["session_id"],
                "code_digest": session["code_digest"],
            }
            atomic_json(self.local / "check.json", job)
            (self.local / "stop-check").unlink(missing_ok=True)

        class Cancel:
            def is_set(inner):
                return (self.local / "stop-check").exists()

        try:
            failures = core.run_solution(candidate, problem, min(10, max(0.1, timeout)), Cancel())
        finally:
            candidate.unlink(missing_ok=True)
        with self.lock:
            session = self._session()
            stale = (
                session["session_id"] != snapshot["session_id"]
                or session["code_digest"] != snapshot["code_digest"]
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
            atomic_json(self.local / "check.json", result)
            return result

    def stop_check(self):
        atomic_text(self.local / "stop-check", "stop")
        return {"message": "Stopping check; your saved code is preserved."}

    def evaluate(self):
        with self.lock:
            session = self._session()
            self._tick(session)
            self._save(session)
            levels = [e["level"] for e in session.get("assistance_log", [])]
            level = max(levels, key=core.ASSISTANCE_LEVELS.index, default="none")
            quality = session.get("initial_reasoning", {}).get("quality", "unknown")
            failed = quality in {"partial", "failed"} or level in {"guided", "substantial"}
            if session.get("workflow_version") == 3:
                failed = quality in {"partial", "failed"} or any(
                    e.get("supplied_missing_recall") for e in session.get("assistance_log", [])
                )
            dimensions = {}
            for finding in session.get("evidence_amendments", []):
                if finding.get("code_digest") == session["code_digest"]:
                    dimensions[finding["dimension"]] = finding["value"]
            failed = failed or dimensions.get("recall") == "failure"
            unknown = (
                session.get("workflow_version") == 3
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
                "public_repository": "https://github.com/david1534/leetcode-learning-system",
                "files": [
                    "solution or saved unsuccessful candidate",
                    "review evidence",
                    "brief reflection",
                ],
            }

    def pause(self, revision=None, synchronize=True):
        with self.lock:
            session = self._session(revision)
            self._tick(session)
            session["phase_started_at"] = None
            session["active_started_at"] = None
            self._save(session)
            if synchronize:
                self._publish_paths(
                    ["attempt", *session.get("learning_event_paths", [])], session["problem_id"]
                )
            return self.state()

    def _publish_paths(self, paths, problem_id, complete=False):
        if not (self.root / ".git").exists():
            return self._set_sync("local", "Saved locally. This folder has no Git remote.")
        try:
            paths = [
                p
                for p in paths
                if (self.root / p).exists()
                or gitflow.run_git(self.root, "ls-files", "--", p).output
            ]
            extra = [
                p
                for p in gitflow.tracked_changes(self.root)
                if not any(p == x or p.startswith(x.rstrip("/") + "/") for x in paths)
            ]
            if extra:
                raise gitflow.GitFlowError(
                    "Unrelated changes prevent publication; study files are saved locally."
                )
            # Retrying after a successful remote merge is a no-op, even if cleanup failed.
            if complete:
                gitflow.fetch(self.root)
                reviews = [p for p in paths if p.startswith("progress/reviews/")]
                if reviews and all(
                    gitflow.run_git(self.root, "show", f"origin/main:{p}").output.strip()
                    == (self.root / p).read_text(encoding="utf-8").strip()
                    for p in reviews
                ):
                    return self._set_sync(
                        "synced", "Completion already published; no duplicate review created."
                    )
            name = gitflow.branch_name(self.root)
            if name == "main":
                target = gitflow.attempt_branch(problem_id)
                if (
                    gitflow.run_git(
                        self.root, "show-ref", "--verify", "--quiet", f"refs/heads/{target}"
                    ).code
                    == 0
                ):
                    result = gitflow.run_git(self.root, "switch", target)
                    if result.code:
                        raise gitflow.GitFlowError(result.output)
                else:
                    gitflow.create_attempt_branch(self.root, problem_id)
                name = gitflow.branch_name(self.root)
            if not name.startswith("attempt/"):
                raise gitflow.GitFlowError(
                    "Saved locally on a development branch. Publish from a study "
                    "checkout after merging the update."
                )
            extra = [
                p
                for p in gitflow.tracked_changes(self.root)
                if not any(
                    p == allowed or p.startswith(allowed.rstrip("/") + "/") for allowed in paths
                )
            ]
            if extra:
                raise gitflow.GitFlowError(
                    "Unrelated changes prevent publication. Your study files remain saved locally."
                )
            gitflow.commit_paths(
                self.root, f"study: {'complete' if complete else 'pause'} {problem_id}", paths
            )
            gitflow.push_current(self.root, set_upstream=True)
            if complete:
                gitflow.merge_completed_attempt(self.root, name)
            return self._set_sync("synced", "Published and synchronized with GitHub.")
        except gitflow.GitFlowError as exc:
            return self._set_sync("pending", f"Saved locally; sync pending. {exc}")

    def recover(self):
        """Preserve a divergent draft on a distinct branch, without choosing a winner."""
        with self.lock:
            active = self.root / "attempt"
            if not active.exists():
                raise RuntimeError("No active draft to preserve.")
            backup = self.local / "recovery" / uuid.uuid4().hex
            shutil.copytree(active, backup)
            if (self.root / ".git").exists():
                name = "attempt/recovered-" + uuid.uuid4().hex[:12]
                result = gitflow.run_git(self.root, "switch", "-c", name)
                if result.code:
                    raise RuntimeError(
                        "The draft backup is saved locally; Git could not create a recovery branch."
                    )
            if not core.load_session(self.root):
                # Sessionless work is retained as an orphan archive before a fresh session.
                archive = self.root / "progress/orphan-drafts" / backup.name
                shutil.copytree(active, archive)
                shutil.rmtree(active)
            return self._set_sync(
                "local",
                "Both versions are preserved. Resume this draft, or choose "
                "the other saved attempt in Git.",
            )

    def choose_attempt(self, branch):
        with self.lock:
            if branch not in self._read_local("remote-attempts", []):
                raise RuntimeError("Select a listed saved attempt.")
            if core.load_session(self.root):
                raise RuntimeError("Preserve and finish the current session before switching.")
            gitflow.switch_to_remote_attempt(self.root, branch)
            atomic_json(self.local / "remote-attempts.json", [])
            return self.start(synchronize=False)

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
    ):
        if rating not in {*core.RATINGS, "unknown"}:
            raise RuntimeError("Select Again, Hard, Good, or Easy.")
        if minutes is not None and not 0 < minutes <= 1440:
            raise RuntimeError("Minutes must be between 0 and 1440.")
        with self.lock:
            receipt_path = self.local / "completions" / f"{session_id}.json"
            # IDs are created by this service, never arbitrary filesystem paths.
            if not isinstance(session_id, str) or not session_id.isalnum() or len(session_id) > 64:
                raise RuntimeError("Invalid session ID.")
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                self._close_attempt(receipt)
                return receipt
            session = self._session(revision)
            if session["session_id"] != session_id:
                raise Conflict("The active session changed; refresh before completion.")
            if self._check_state().get("status") == "running":
                raise RuntimeError("Stop or finish the running check before closing the activity.")
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
            if not takeaway.strip() and not stopped:
                raise RuntimeError(
                    "Add a brief takeaway, or say that no new lesson was identified."
                )
            text = (self.root / "attempt/current.py").read_text(encoding="utf-8")
            if digest(text) != session["code_digest"]:
                raise Conflict("The candidate changed during completion; rerun its check.")
            safe = "\n".join(
                [
                    text,
                    takeaway,
                    json.dumps(session.get("initial_reasoning", {})),
                    json.dumps(session.get("assistance_log", [])),
                ]
            )
            if publish and core.public_learning_text_errors(safe):
                raise RuntimeError(
                    "Public-content check found sensitive text. Keep the session "
                    "local and edit it before publication."
                )
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
                "rating": rating,
                "minutes": round(minutes if minutes is not None else calculated, 3),
                "timing": timing,
                "timing_adjusted": minutes is not None,
                "activity": session["activity"],
                "attempt_kind": session["attempt_kind"],
                "unseen": session["unseen"],
                "recall_outcome": facts["recall_outcome"],
                "recall_quality": session.get("initial_reasoning", {}).get("quality", "unknown"),
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
            if session.get("workflow_version") == 3:
                event.update(
                    workflow_version=3,
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
            archive = self.root / "progress/attempts" / session_id
            atomic_text(archive / "candidate.py", text)
            atomic_json(archive / "session.json", session)
            prior = self.root / "attempt/assessment.py"
            if prior.exists():
                atomic_text(archive / "assessment.py", prior.read_text(encoding="utf-8"))
            review = self.root / "progress/reviews" / f"{session_id}.json"
            atomic_json(review, event)
            reflection = self.root / "reflections" / f"{session['problem_id']}.md"
            atomic_text(
                reflection,
                "# Learning reflection\n\n"
                f"{takeaway.strip() or 'Stopped; no takeaway recorded.'}\n\n"
                f"Activity: {session['activity']}. Recall: {rating}. "
                f"Assistance: {facts['assistance_level']}.\n"
                f"Explanation recorded: {explained}. Constraints checked: {constraints_met}.\n",
            )
            atomic_text(archive / "reflection.md", reflection.read_text(encoding="utf-8"))
            paths = [
                archive.relative_to(self.root).as_posix(),
                review.relative_to(self.root).as_posix(),
                reflection.relative_to(self.root).as_posix(),
                *session.get("learning_event_paths", []),
            ]
            if facts["tests_passed"] and session["activity"] in {"implement", "transfer"}:
                solution = self.root / "solutions" / f"{session['problem_id']}.py"
                atomic_text(solution, text)
                paths.append(solution.relative_to(self.root).as_posix())
            # Persist the transaction before removing active work; retries use the same event ID.
            receipt = {
                "session_id": session_id,
                "problem_id": session["problem_id"],
                "event_id": session_id,
                "status": "saved",
                "published": False,
                "paths": paths,
                "message": "Session saved locally.",
            }
            if (self.root / ".git").exists() and gitflow.run_git(
                self.root, "ls-files", "attempt"
            ).output:
                paths.append("attempt")
            atomic_json(receipt_path, receipt)
            atomic_json(self.local / "last-completion.json", receipt)
            self._close_attempt(receipt)
            if publish:
                result = self.publish(session_id, include_saved=True)
                receipt.update(published=result["status"] == "synced", message=result["message"])
            atomic_json(receipt_path, receipt)
            atomic_json(self.local / "last-completion.json", receipt)
            return receipt

    def sync(self):
        with self.lock:
            pending = self._read_local("pending")
            if pending:
                result = self._publish_paths(pending["paths"], pending["problem_id"], complete=True)
                if result["status"] == "synced":
                    (self.local / "pending.json").unlink(missing_ok=True)
                    for sid in pending.get("session_ids", [pending["session_id"]]):
                        saved = self._read_local("completions/" + sid)
                        saved.update(published=True, message=result["message"])
                        atomic_json(self.local / "completions" / f"{sid}.json", saved)
                    atomic_json(
                        self.local / "last-completion.json",
                        self._read_local("completions/" + pending["session_id"]),
                    )
                return result
            session = core.load_session(self.root)
            if session:
                return self._publish_paths(
                    ["attempt", *session.get("learning_event_paths", [])], session["problem_id"]
                )
            self._pull()
            return self._read_local(
                "sync", {"status": "local", "message": "No pending publication."}
            )

    def publish(self, session_id, include_saved=False):
        with self.lock:
            if not isinstance(session_id, str) or not session_id.isalnum():
                raise RuntimeError("Invalid session ID.")
            receipt = self._read_local("completions/" + session_id)
            if not receipt:
                raise RuntimeError("No saved completion with this ID on this computer.")
            if receipt.get("published"):
                return receipt
            unsent = self._unpublished()
            if len(unsent) > 1:
                if not include_saved:
                    raise RuntimeError(
                        "Several sessions are saved locally. Review the saved-session "
                        "count and publish them together from Today."
                    )
                receipt = {
                    **receipt,
                    "session_ids": [r["session_id"] for r in unsent],
                    "paths": list(dict.fromkeys(p for r in unsent for p in r["paths"])),
                }
            if core.load_session(self.root):
                raise RuntimeError(
                    "Pause and finish the current activity before publishing an earlier completion."
                )
            for relative in receipt["paths"]:
                path = self.root / relative
                for file in path.rglob("*") if path.is_dir() else [path]:
                    if file.is_file() and core.public_learning_text_errors(
                        file.read_text(encoding="utf-8")
                    ):
                        raise RuntimeError(
                            "Public-content check found sensitive text. Keep these artifacts "
                            "local and edit them before publication."
                        )
            atomic_json(self.local / "pending.json", receipt)
            return self.sync()

    def keep_local(self):
        with self.lock:
            pending = self._read_local("pending")
            if pending:
                atomic_json(self.local / "deferred-publication.json", pending)
                (self.local / "pending.json").unlink()
            return self._set_sync(
                "local", "Completion kept locally; its archive and review are preserved."
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
            timer = self._read_local("repair-timer", {})
            if timer.get("error_id") != error_id:
                if timer:
                    raise RuntimeError("Finish the saved repair before opening a different one.")
                timer = {"error_id": error_id, "seconds": 0, "application": ""}
            if not timer.get("started_at"):
                timer["started_at"] = datetime.now(UTC).isoformat()
            atomic_json(self.local / "repair-timer.json", timer)
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
                atomic_json(self.local / "repair-timer.json", timer)
            return {"message": "Repair paused; its draft and time are saved."}

    def repair(
        self, error_id, application, passed, assistance="none", explanation="", minutes=None
    ):
        with self.lock:
            timer = self._read_local("repair-timer")
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
            )
            event = json.loads(path.read_text(encoding="utf-8"))
            event["timing"] = {"repair": round(elapsed, 3)}
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
            atomic_json(path, event)
            (self.local / "repair-timer.json").unlink(missing_ok=True)
            # Repair publication is deliberate through the same sync control.
            session = core.load_session(self.root)
            if session:
                session.setdefault("learning_event_paths", []).append(
                    path.relative_to(self.root).as_posix()
                )
                self._save(session)
                self.start(synchronize=False)
            else:
                receipt = {
                    "session_id": event["event_id"],
                    "event_id": event["event_id"],
                    "problem_id": event["problem_id"],
                    "published": False,
                    "paths": [path.relative_to(self.root).as_posix()],
                    "message": "Repair saved locally. Publish to synchronize this evidence.",
                }
                atomic_json(self.local / "completions" / f"{event['event_id']}.json", receipt)
                atomic_json(self.local / "last-completion.json", receipt)
            return {
                "event_path": path.relative_to(self.root).as_posix(),
                "event_id": event["event_id"],
                "passed": event["passed"],
                "message": "Repair cleared." if event["passed"] else "Repair remains open.",
                "minutes": round(elapsed / 60, 2),
            }
