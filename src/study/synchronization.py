"""Durable, explicit Git synchronization, independent of successful local saves."""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
import threading
import uuid
from pathlib import Path

from filelock import FileLock, Timeout

from study import core, gitflow
from study.database import PUBLIC_PREFIXES, same_document
from study.storage import atomic_text


def sensitive(value):
    if isinstance(value, str):
        if core.public_learning_text_errors(value):
            return True
        if value.lstrip().startswith(("{", "[")):
            try:
                return sensitive(json.loads(value))
            except ValueError:
                pass
    if isinstance(value, dict):
        return any(sensitive(k) or sensitive(v) for k, v in value.items())
    if isinstance(value, list):
        return any(sensitive(v) for v in value)
    return False


def latest_review(reviews, problem_id, solution):
    return max(
        (
            (event["reviewed_at"], event["event_id"])
            for event in reviews
            if event["problem_id"] == problem_id
            and (
                not solution
                or event.get("tests_passed")
                and event.get("activity", "implement") in {"implement", "transfer"}
            )
        ),
        default=("", ""),
    )


class Synchronizer:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.root = self.store.directory / "git-export"
        self.worker = None
        self.guard = FileLock(str(self.store.directory / "sync.lock"), timeout=0)

    def git(self, *args):
        result = gitflow.run_git(self.root, *args)
        if result.code:
            raise gitflow.GitFlowError(result.output)
        return result.output

    def prepare(self):
        remote = gitflow.run_git(self.service.root, "remote", "get-url", "origin")
        if remote.code or not remote.output:
            raise gitflow.GitFlowError(
                "This workspace has no Git remote. Practice is saved locally."
            )
        if not (self.root / ".git").exists():
            result = gitflow.run_git(
                self.store.directory, "clone", "--no-checkout", remote.output, str(self.root)
            )
            if result.code:
                raise gitflow.GitFlowError(
                    "Could not prepare Git synchronization. " + result.output
                )
            for field, fallback in (
                ("name", "Practice Room"),
                ("email", "practice-room@users.noreply.github.com"),
            ):
                configured = gitflow.run_git(
                    self.service.root, "config", "--local", "user." + field
                )
                self.git(
                    "config",
                    "user." + field,
                    configured.output if not configured.code else fallback,
                )
        configured = self.git("remote", "get-url", "origin")
        if configured != remote.output:
            raise gitflow.GitFlowError(
                "The repository destination changed. Review it before synchronizing."
            )
        gitflow.fetch(self.root)

    def tree(self, ref, include_attempt=False):
        # Read a Git snapshot without checking out or extracting archive paths.
        result = subprocess.run(
            ["git", "archive", ref],
            cwd=self.root,
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise gitflow.GitFlowError("Could not read the saved Git snapshot.")
        documents = {}
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
            for member in archive:
                if not member.isfile():
                    continue
                name = self.store.valid_path(member.name)
                if not name.startswith(
                    PUBLIC_PREFIXES + (("attempt/",) if include_attempt else ())
                ):
                    continue
                if Path(name).suffix not in {".json", ".md", ".py", ".txt"}:
                    continue
                stream = archive.extractfile(member)
                if stream:
                    documents[name] = stream.read().decode("utf-8-sig")
        return documents

    def _set(self, status, message):
        with self.store.transaction():
            return self.service._set_sync(status, message)

    def pull(self, wait=True):
        if not (self.service.root / ".git").exists():
            return self._set("local", "Saved on this computer. No Git remote is configured.")
        if not wait:
            self.wake(pull=True)
            return self.service._read_local(
                "sync", {"status": "local", "message": "Saved on this computer."}
            )
        try:
            with self.guard:
                return self._pull()
        except Timeout:
            return self._set("checking", "GitHub synchronization is already running.")
        except (gitflow.GitFlowError, OSError, subprocess.SubprocessError) as exc:
            return self._set(
                "pending",
                "GitHub could not be checked. Continue locally or retry sync. " + str(exc),
            )

    def _pull(self):
        self.prepare()
        history = self.tree("origin/main")
        branches = gitflow.remote_attempts(self.root)
        closed = set()
        for path, text in history.items():
            if path.startswith("progress/attempts/") and path.endswith("/session.json"):
                saved = json.loads(text)
                if saved.get("sync_branch") and saved.get("sync_base"):
                    closed.add((saved["sync_branch"], saved["sync_base"]))
        heads = {branch: self.git("rev-parse", "origin/" + branch) for branch in branches}
        branches = [
            branch
            for branch in branches
            if (branch, heads[branch]) not in closed
            and gitflow.run_git(
                self.root, "merge-base", "--is-ancestor", "origin/" + branch, "origin/main"
            ).code
            != 0
        ]
        with self.service.lock:
            self.store.import_documents(history, "github-main")
            active = core.load_session(self.service.root)
            public_reviews = {
                json.loads(text)["event_id"]: (path, json.loads(text))
                for path, text in history.items()
                if path.startswith("progress/reviews/") and path.endswith(".json")
            }
            if (
                active
                and active["session_id"] in public_reviews
                and not active.get("phase_started_at")
                and active.get("sync_revision") == active["revision"]
            ):
                sid = active["session_id"]
                review_path, review = public_reviews[sid]
                self.service._write_local(
                    "recovery/retired-" + sid, {"session": active, "code": self.service._code()}
                )
                receipt = {
                    "session_id": sid,
                    "event_id": sid,
                    "problem_id": active["problem_id"],
                    "status": "saved",
                    "published": True,
                    "saved_at": review["reviewed_at"],
                    "paths": [review_path, f"progress/attempts/{sid}"],
                    "message": "This session was completed and published from another computer.",
                }
                self.service._write_local("completions/" + sid, receipt)
                self.service._close_attempt(receipt)
                active = None
            active = active or self.service._read_local("repair-timer")
            self.service._write_local("remote-attempts", branches if not active else [])
        if not active and len(branches) == 1:
            return self._choose(branches[0])
        if not active and len(branches) > 1:
            return self._set("choice", "Several saved attempts exist. Choose the one to resume.")
        return self._set(
            "local" if active else "synced",
            "GitHub checked. Pause or Sync to back up this draft."
            if active
            else "Up to date with GitHub.",
        )

    def choose_attempt(self, branch):
        if branch not in self.service._read_local("remote-attempts", []):
            raise RuntimeError("Select a listed saved attempt.")
        with self.guard:
            self.prepare()
            self._choose(branch)
        return self.service.practice_start(synchronize=False)

    def _choose(self, branch):
        snapshot = self.tree("origin/" + branch, include_attempt=True)
        head = self.git("rev-parse", "origin/" + branch)
        with self.service.lock:
            if core.load_session(self.service.root) or self.service._read_local("repair-timer"):
                raise RuntimeError(
                    "Preserve and finish the current activity before switching drafts."
                )
            self.store.import_documents(
                {p: text for p, text in snapshot.items() if not p.startswith("attempt/")},
                "github-" + branch,
            )
            for path, text in snapshot.items():
                if path.startswith("attempt/"):
                    self.store.write_text(path, text)
            if "attempt/repair.json" in snapshot:
                timer = json.loads(snapshot["attempt/repair.json"])
                timer.update(started_at=None, sync_branch=branch, sync_base=head)
                self.service._write_local("repair-timer", timer)
                self.store.delete("attempt/repair.json")
            from study.migration import migrate_saved_work

            migrate_saved_work(self.store)
            session = core.load_session(self.service.root)
            if session:
                session.update(
                    phase_started_at=None,
                    active_started_at=None,
                    sync_branch=branch,
                    sync_base=head,
                    sync_revision=session["revision"],
                )
                core.save_session(self.service.root, session)
            if not session and not self.service._read_local("repair-timer"):
                raise RuntimeError(
                    "That branch has no unfinished activity. Its history was imported."
                )
            self.service._write_local("remote-attempts", [])
        return self._set("synced", "Saved attempt restored from GitHub.")

    def snapshot(self, paths):
        result = {}
        for path in paths:
            if self.store.exists(path):
                result[path] = self.store.read_text(path)
            else:
                result.update(self.store.documents(path.rstrip("/") + "/"))
        return result

    def publication_snapshot(self, receipts):
        paths = list(
            dict.fromkeys(
                path
                for receipt in receipts
                for path in receipt["paths"]
                if path != "attempt" and not path.startswith(("solutions/", "reflections/"))
            )
        )
        artifacts = self.snapshot(paths)
        newest = {}
        for path, text in list(artifacts.items()):
            if not path.startswith("progress/reviews/") or not path.endswith(".json"):
                continue
            event = json.loads(text)
            archive = f"progress/attempts/{event['event_id']}"
            order = (event["reviewed_at"], event["event_id"])
            reflection = self.store.read_text(archive + "/reflection.md")
            target = f"reflections/{event['problem_id']}.md"
            if reflection is not None and order > newest.get(target, ("", "")):
                artifacts[target], newest[target] = reflection, order
            candidate = self.store.read_text(archive + "/candidate.py")
            target = f"solutions/{event['problem_id']}.py"
            if (
                candidate is not None
                and event.get("tests_passed")
                and event.get("activity", "implement") in {"implement", "transfer"}
                and order > newest.get(target, ("", ""))
            ):
                artifacts[target], newest[target] = candidate, order
        return artifacts

    def enqueue(self, paths, problem_id, complete=False):
        with self.service.lock:
            return self._enqueue(
                self.snapshot(paths), problem_id, "publish" if complete else "draft"
            )

    def _enqueue(
        self, artifacts, problem_id, kind, session_ids=None, branch=None, base=None, revision=None
    ):
        for path, text in artifacts.items():
            self.store.valid_path(path)
            if not path.startswith(PUBLIC_PREFIXES + ("attempt/",)):
                raise RuntimeError("Only scoped learning artifacts can be synchronized.")
            if sensitive(text):
                return self.service._set_sync(
                    "pending",
                    f"Public-content check found sensitive text in {path}. "
                    "Your work is saved locally; review it before publishing.",
                )
        job_id = uuid.uuid4().hex
        self.service._write_local(
            "outbox/" + job_id,
            {
                "id": job_id,
                "kind": kind,
                "status": "pending",
                "problem_id": problem_id,
                "artifacts": artifacts,
                "session_ids": session_ids or [],
                "branch": branch,
                "base": base,
                "revision": revision,
            },
        )
        result = self.service._set_sync(
            "pending", "Saved locally; GitHub synchronization is pending."
        )
        self.wake()
        return result

    def enqueue_draft(self):
        with self.service.lock:
            session = core.load_session(self.service.root)
            timer = self.service._read_local("repair-timer")
            if not session and not timer:
                return self.service._read_local(
                    "sync", {"status": "local", "message": "No active draft."}
                )
            if session:
                session = json.loads(json.dumps(session))
                self.service._tick(session)
                session.update(active_started_at=None, phase_started_at=None)
                artifacts = self.snapshot(["attempt", *session.get("learning_event_paths", [])])
                artifacts["attempt/session.json"] = json.dumps(session, indent=2) + "\n"
                source, pid = session, session["problem_id"]
            else:
                source, pid = timer, "repair"
                portable = {k: v for k, v in timer.items() if k not in {"coach_review", "check"}}
                portable["started_at"] = None
                artifacts = {"attempt/repair.json": json.dumps(portable, indent=2) + "\n"}
                artifacts.update(
                    {
                        p: text
                        for p, text in self.store.documents("progress/learning-events/").items()
                        if json.loads(text).get("event_id") == timer["error_id"]
                    }
                )
            return self._enqueue(
                artifacts,
                pid,
                "draft",
                [source.get("session_id", source.get("error_id"))],
                source.get("sync_branch") or gitflow.attempt_branch(pid),
                source.get("sync_base"),
                source.get("revision", 0),
            )

    def publish(
        self,
        session_id,
        include_saved=False,
        wait=False,
        expected_session_ids=None,
        session_ids=None,
    ):
        with self.service.lock:
            receipt = self.service._read_local("completions/" + session_id)
            if not receipt:
                raise RuntimeError("No saved completion with this ID on this computer.")
            if receipt.get("published") and session_ids is None:
                return receipt
            saved = self.service._unpublished()
            if session_ids is not None:
                chosen = [r for r in saved if r["session_id"] in session_ids]
                if not chosen or {r["session_id"] for r in chosen} != set(session_ids):
                    raise RuntimeError(
                        "The selected saved sessions changed. Refresh the publication preview."
                    )
            else:
                chosen = saved if include_saved else [receipt]
            ids = [r["session_id"] for r in chosen]
            if expected_session_ids is not None and set(ids) != set(expected_session_ids):
                from study.service import Conflict

                raise Conflict(
                    "The saved-session list changed. Review the publication preview again."
                )
            pending = [
                j
                for j in self.store.json_documents(".study-local/outbox/")
                if j["kind"] == "publish"
                and j["session_ids"] == ids
                and j["status"] in {"pending", "running"}
            ]
            if not pending:
                before = len(self.store.paths(".study-local/outbox/", ".json"))
                result = self._enqueue(
                    self.publication_snapshot(chosen), receipt["problem_id"], "publish", ids
                )
                if len(self.store.paths(".study-local/outbox/", ".json")) == before:
                    return result
        if wait:
            return self.sync(wait=True)
        self.wake()
        return self.service._read_local("sync")

    def sync(self, wait=False):
        with self.service.lock:
            legacy = self.service._read_local("legacy-pending")
            if legacy and not legacy.get("queued"):
                before = len(self.store.paths(".study-local/outbox/", ".json"))
                self._enqueue(
                    legacy["artifacts"],
                    legacy["problem_id"],
                    "publish",
                    legacy.get("session_ids", [legacy["session_id"]]),
                )
                if len(self.store.paths(".study-local/outbox/", ".json")) > before:
                    legacy["queued"] = True
                    self.service._write_local("legacy-pending", legacy)
                else:
                    return self.service._read_local("sync")
        jobs = self.store.json_documents(".study-local/outbox/")
        if not any(j["status"] in {"pending", "running"} for j in jobs):
            if core.load_session(self.service.root) or self.service._read_local("repair-timer"):
                self.enqueue_draft()
            else:
                return self.pull(wait=wait)
        if wait:
            if self.worker and self.worker.is_alive():
                self.worker.join(timeout=55)
            self.run_jobs()
        else:
            self.wake()
        return self.service._read_local("sync")

    def wake(self, pull=False):
        if self.worker and self.worker.is_alive():
            return
        self.worker = threading.Thread(target=self._background, args=(pull,), daemon=True)
        self.worker.start()

    def _background(self, pull):
        try:
            if pull:
                self.pull()
            self.run_jobs()
        except Exception:
            # The local completion already committed; diagnostics middleware also
            # handles foreground errors. A retry reconstructs this job from SQLite.
            self._set("pending", "Saved locally; sync was interrupted. Retry synchronization.")

    def run_jobs(self):
        try:
            with self.guard:
                jobs = [
                    j
                    for j in self.store.json_documents(".study-local/outbox/")
                    if j["status"] in {"pending", "running"}
                ]
                for job in jobs:
                    try:
                        self.prepare()
                        self._push(job)
                    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                        with self.store.transaction():
                            job.update(status="pending", error=str(exc))
                            self.service._write_local("outbox/" + job["id"], job)
                            self.service._set_sync(
                                "pending", "Saved locally; sync pending. " + str(exc)
                            )
                        break
        except Timeout:
            return

    def _push(self, job):
        with self.store.transaction():
            latest = self.service._read_local("outbox/" + job["id"], {})
            if latest.get("status") not in {"pending", "running"}:
                return
            job["status"] = "running"
            self.service._write_local("outbox/" + job["id"], job)
        publish = job["kind"] == "publish"
        branch = (
            "publication/" + job["id"]
            if publish
            else job["branch"] or gitflow.attempt_branch(job["problem_id"])
        )
        ref = "origin/main" if publish else "origin/" + branch
        exists = gitflow.run_git(self.root, "rev-parse", "--verify", ref).code == 0
        remote = self.tree(ref, include_attempt=not publish) if exists else {}
        artifacts = dict(job["artifacts"])
        if publish:
            incoming_reviews = [
                json.loads(text)
                for path, text in artifacts.items()
                if path.startswith("progress/reviews/") and path.endswith(".json")
            ]
            remote_reviews = [
                json.loads(text)
                for path, text in remote.items()
                if path.startswith("progress/reviews/") and path.endswith(".json")
            ]
            for path in list(artifacts):
                if not path.startswith(("solutions/", "reflections/")):
                    continue
                problem_id = Path(path).stem

                if latest_review(
                    remote_reviews, problem_id, path.startswith("solutions/")
                ) > latest_review(incoming_reviews, problem_id, path.startswith("solutions/")):
                    artifacts.pop(path)
        immutable = {
            p: t for p, t in artifacts.items() if not p.startswith(("solutions/", "reflections/"))
        }
        already_saved = bool(immutable) and all(
            p in remote and same_document(remote[p], text) for p, text in immutable.items()
        )
        head = self.git("rev-parse", ref) if exists else None
        if not already_saved:
            if not publish and exists and head != job.get("base"):
                raise gitflow.GitFlowError(
                    "This draft changed on another computer. Both copies are preserved; "
                    "recover a separate draft before syncing."
                )
            for path, text in immutable.items():
                if publish and path in remote and not same_document(remote[path], text):
                    raise gitflow.GitFlowError(
                        f"Published evidence differs at {path}. "
                        "Both copies are preserved for review."
                    )
            # Retry only generated paths from this job. Source learner files are never touched.
            tracked = self.git("ls-files", "--", *artifacts) if artifacts else ""
            if tracked:
                self.git(
                    "restore",
                    "--source=HEAD",
                    "--staged",
                    "--worktree",
                    "--",
                    *tracked.splitlines(),
                )
            self.git("switch", "--detach", ref if exists else "origin/main")
            if publish:
                self.git("switch", "-c", branch + "-" + uuid.uuid4().hex[:8])
            else:
                existing_branch = gitflow.run_git(
                    self.root, "show-ref", "--verify", "--quiet", "refs/heads/" + branch
                )
                if existing_branch.code:
                    self.git("switch", "-c", branch)
                else:
                    self.git("switch", branch)
                    if exists:
                        self.git("merge", "--ff-only", ref)
            for path, text in artifacts.items():
                target = (self.root / path).resolve()
                if not target.is_relative_to(self.root):
                    raise RuntimeError("Invalid export destination.")
                atomic_text(target, text)
            gitflow.commit_paths(
                self.root,
                "study: " + ("complete " if publish else "pause ") + job["problem_id"],
                list(artifacts),
            )
            if publish:
                self.git("push", "origin", "HEAD:main")
            else:
                gitflow.push_current(self.root, set_upstream=True)
            head = self.git("rev-parse", "HEAD")
        with self.service.lock:
            job["status"] = "synced"
            job.pop("error", None)
            self.service._write_local("outbox/" + job["id"], job)
            if publish:
                for sid in job["session_ids"]:
                    saved = self.service._read_local("completions/" + sid)
                    if saved:
                        saved.update(
                            published=True, message="Saved locally and published to GitHub."
                        )
                        self.service._write_local("completions/" + sid, saved)
                        latest = self.service._read_local("last-completion", {})
                        if latest.get("session_id") == sid:
                            self.service._write_local("last-completion", saved)
            else:
                session = core.load_session(self.service.root)
                if session and session["session_id"] in job["session_ids"]:
                    session.update(
                        sync_branch=branch, sync_base=head, sync_revision=job.get("revision")
                    )
                    core.save_session(self.service.root, session)
            self.service._set_sync(
                "synced",
                "Published and synchronized with GitHub."
                if publish
                else "Draft synchronized with GitHub.",
            )
