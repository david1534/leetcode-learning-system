from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from filelock import Timeout
from pydantic import ValidationError

from study.build import API_VERSION, VERSION, build_id
from study.coach import Coach, CoachRequest, CoachStatus, RequestReceipt
from study.database import workspace_id
from study.interfaces import (
    ACTION_INPUTS,
    AdvancePractice,
    ApplyProposal,
    CoachPreferences,
    FinishPractice,
    RepairDraft,
    RepairReview,
    RetryReasoning,
    Revision,
    StartPractice,
)
from study.service import Conflict, StudyService


def create_app(root: Path, coach_factory=Coach) -> FastAPI:
    service = StudyService(root)
    coach = coach_factory(service)
    current_build = build_id()
    logger = logging.getLogger("study." + workspace_id(root))
    if not logger.handlers:
        handler = RotatingFileHandler(
            service.local / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    stopped = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        service.recover_timing()
        service.synchronizer.wake()

        def checkpoint():
            while not stopped.wait(5):
                service.timer_checkpoint()

        timer = threading.Thread(target=checkpoint, daemon=True)
        timer.start()
        yield
        stopped.set()
        try:
            service.timer_checkpoint(pause=True)
            coach.disconnect()
        except (RuntimeError, OSError, sqlite3.Error):
            logger.exception("Shutdown checkpoint failed")

    app = FastAPI(title="Practice Room", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.service = service
    app.state.coach = coach

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse({"detail": "Local access only."}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if request.headers.get("x-study-request") != "1" or (
                origin and origin != str(request.base_url).rstrip("/")
            ):
                return JSONResponse(
                    {"detail": "Open the local app to perform this action."}, status_code=403
                )
        client_build = request.headers.get("x-study-build")
        if request.method == "POST" and client_build and client_build != current_build:
            return JSONResponse(
                {
                    "code": "client_outdated",
                    "detail": (
                        "The app was updated. Reload this page to reconnect; your browser "
                        "draft remains available."
                    ),
                },
                status_code=409,
            )
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RuntimeError)
    async def recoverable(_request, exc):
        return JSONResponse(
            {
                "code": "conflict" if isinstance(exc, Conflict) else "invalid_action",
                "detail": str(exc),
            },
            status_code=409 if isinstance(exc, Conflict) else 400,
        )

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"code": "invalid_request", "detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid_fields(_request, exc):
        return JSONResponse(
            {"code": "invalid_request", "detail": "Check the entered fields and try again."},
            status_code=422,
        )

    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(Timeout)
    async def storage_error(_request, exc):
        reference = uuid.uuid4().hex[:12]
        logger.error("Storage error %s", reference, exc_info=exc)
        return JSONResponse(
            {
                "code": "storage_unavailable",
                "detail": (
                    "The local save could not be confirmed. Keep your draft open and "
                    "retry, or download your work."
                ),
                "diagnostic_id": reference,
                "saved_state": "unknown",
            },
            status_code=503,
        )

    @app.exception_handler(Exception)
    async def unexpected(_request, exc):
        reference = uuid.uuid4().hex[:12]
        logger.error("Unexpected error %s", reference, exc_info=exc)
        return JSONResponse(
            {
                "code": "internal_error",
                "detail": (
                    "The app could not confirm this action. Keep your draft open and reconnect."
                ),
                "diagnostic_id": reference,
                "saved_state": "unknown",
            },
            status_code=500,
        )

    @app.get("/api/state")
    def state():
        return {**service.state(), "api_version": API_VERSION, "build_id": current_build}

    @app.get("/api/health")
    def health():
        return {
            "app": "practice-room",
            "version": VERSION,
            "api_version": API_VERSION,
            "build_id": current_build,
            "workspace": workspace_id(root),
            "instance_id": getattr(app.state, "instance_id", None),
        }

    @app.post("/api/app/shutdown")
    def shutdown(request: Request, background: BackgroundTasks):
        if (
            not getattr(app.state, "owner", None)
            or request.headers.get("x-study-owner") != app.state.owner
        ):
            return JSONResponse(
                {"code": "not_owned", "detail": "This launcher does not own the running app."},
                status_code=403,
            )
        service.timer_checkpoint(pause=True)
        background.add_task(app.state.shutdown)
        return {"status": "stopping"}

    @app.post("/api/app/restart")
    def restart(background: BackgroundTasks):
        from study.launcher import request_restart

        if not getattr(app.state, "owner", None):
            raise RuntimeError("Open Start Study to restart this development server.")
        service.timer_checkpoint(pause=True)
        background.add_task(request_restart, root)
        return {"status": "restarting", "message": "Your saved work will reopen after restart."}

    @app.get("/api/completions/{session_id}")
    def completion_receipt(session_id: str):
        if not session_id.isalnum() or len(session_id) > 64:
            raise ValueError("Invalid completion ID.")
        receipt = service._read_local("completions/" + session_id)
        return (
            receipt
            if receipt
            else JSONResponse(
                {"code": "not_found", "detail": "No completed save with this ID."}, status_code=404
            )
        )

    @app.get("/api/diagnostics")
    def diagnostics():
        with service.store.connection() as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "version": VERSION,
            "build_id": current_build,
            "api_version": API_VERSION,
            "storage": integrity,
            "coach_version": coach.runtime.version,
            "coach_connection": coach.connection,
            "pending_sync": sum(
                j["status"] == "pending"
                for j in service.store.json_documents(".study-local/outbox/")
            ),
        }

    @app.get("/api/publication-preview")
    def publication_preview():
        from study import core

        with service.lock:
            receipts = service._unpublished()
            events = {event["event_id"]: event for event in core.load_events(root)}
            catalog = {p["id"]: p["title"] for p in core.load_problems(root)}
            return {
                "sessions": [
                    {
                        "session_id": receipt["session_id"],
                        "title": catalog.get(receipt["problem_id"], "Saved practice"),
                        "files": sorted(service.synchronizer.publication_snapshot([receipt])),
                        "rating": events.get(receipt["session_id"], {}).get("rating", "unknown"),
                    }
                    for receipt in receipts
                ],
                "files": sorted(service.synchronizer.publication_snapshot(receipts)),
                "destination": "github.com/david1534/leetcode-learning-system",
            }

    @app.get("/api/recovery/{conflict_id}")
    def recovery_versions(conflict_id: str):
        if not conflict_id.isalnum():
            raise ValueError("Invalid recovery ID.")
        item = service._read_local("conflicts/" + conflict_id)
        if not item:
            return JSONResponse(
                {"code": "not_found", "detail": "No saved recovery item."}, status_code=404
            )
        return {**item, "current": service.store.read_text(item["path"])}

    @app.get("/api/queue")
    def queue(include_new: bool = False, minutes: int = 60):
        if not 5 <= minutes <= 180:
            raise RuntimeError("Choose 5–180 minutes.")
        return service.plan(include_new, minutes)

    @app.get("/api/progress")
    def progress():
        return service.progress()

    @app.post("/api/practice/start")
    def practice_start(data: StartPractice):
        return service.practice_start(**data.model_dump())

    @app.post("/api/practice/advance")
    def practice_advance(data: AdvancePractice):
        return service.practice_advance(**data.model_dump())

    @app.post("/api/practice/convert")
    def practice_convert(data: Revision):
        return service.convert_to_practice(**data.model_dump())

    @app.post("/api/practice/retry")
    def practice_retry(data: RetryReasoning):
        return service.record_retry(**data.model_dump())

    @app.post("/api/practice/pause")
    def practice_pause():
        result = service.practice_pause()
        try:
            coach.interrupt()
        except RuntimeError:
            pass
        return result

    @app.post("/api/practice/finish")
    def practice_finish(data: FinishPractice, background: BackgroundTasks):
        receipt = service._read_local("completions/" + data.session_id)
        if receipt:
            return receipt
        result = service.practice_finish(**data.model_dump())
        # Finishing never waits on the coach or its network. Late replies cannot
        # mutate the now-closed session, and an old retry never interrupts a new one.
        background.add_task(coach.interrupt)
        return result

    @app.post("/api/practice/repair-draft")
    def repair_draft(data: RepairDraft):
        return service.repair_draft(**data.model_dump())

    @app.post("/api/practice/repair-review")
    def repair_review(data: RepairReview):
        service.repair_draft(data.answer, data.revision, data.session_id)
        context = service.coach_context()
        return coach.submit(
            CoachRequest(
                request_id=data.request_id,
                session_id=context["session_id"],
                revision=context["revision"],
                code_digest=context["code_digest"],
                message="Assess this fresh application of the corrected rule. "
                "Preserve unknown evidence.",
                kind="review",
            )
        )

    @app.post("/api/practice/repair-check")
    def repair_check(data: RepairDraft, background: BackgroundTasks):
        service.repair_draft(data.answer, data.revision, data.session_id)

        def run():
            try:
                service.check_repair()
            except (RuntimeError, SyntaxError) as exc:
                with service.lock:
                    timer = service._read_local("repair-timer")
                    if timer:
                        timer["check"] = {"status": "error", "message": str(exc)}
                        service._write_local("repair-timer", timer)

        background.add_task(run)
        return {"message": "Checking your fresh application…"}

    @app.post("/api/practice/repair-stop")
    def repair_stop():
        return service.stop_repair_check()

    @app.get("/api/coach/status", response_model=CoachStatus)
    def coach_status(session_id: str | None = None):
        return coach.status(session_id)

    @app.post("/api/coach/connect", response_model=CoachStatus)
    def coach_connect():
        return coach.begin_connect()

    @app.post("/api/coach/refresh", response_model=CoachStatus)
    def coach_refresh():
        return coach.refresh()

    @app.post("/api/coach/disconnect", response_model=CoachStatus)
    def coach_disconnect():
        return coach.disconnect()

    @app.post("/api/coach/preferences", response_model=CoachStatus)
    def coach_preferences(data: CoachPreferences):
        return coach.configure(**data.model_dump())

    @app.post("/api/coach/requests", status_code=202, response_model=RequestReceipt)
    def coach_request(data: CoachRequest):
        return coach.submit(data)

    @app.post("/api/coach/interrupt")
    def coach_interrupt():
        return coach.interrupt()

    @app.post("/api/coach/apply")
    def coach_apply(data: ApplyProposal):
        return coach.apply(**data.model_dump())

    @app.get("/api/coach/events")
    async def coach_events(request: Request, session_id: str | None = None):
        async def events():
            previous = None
            while not await request.is_disconnected():
                status = await asyncio.to_thread(coach.status, session_id)
                data = json.dumps(status)
                comparison = json.dumps(
                    {key: value for key, value in status.items() if key != "snapshot"}
                )
                if comparison != previous:
                    yield f"id: {status['sequence']}\ndata: {data}\n\n"
                    previous = comparison
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/api/action/{operation}")
    def action(operation: str, data: dict, background: BackgroundTasks):
        if operation in ACTION_INPUTS:
            data = ACTION_INPUTS[operation].model_validate(data).model_dump()
        actions = {
            "start": service.start,
            "worked-example": service.worked_example,
            "recover": service.recover,
            "choose-attempt": service.choose_attempt,
            "reasoning": service.reasoning,
            "evidence": service.evidence,
            "save": service.save_code,
            "assistance": service.assistance,
            "hint": service.hint,
            "phase": service.phase,
            "continue": service.continue_focus,
            "pause": service.pause,
            "finish": service.finish,
            "repair": service.repair,
            "begin-repair": service.begin_repair,
            "evaluate": service.evaluate,
            "publish": service.publish,
            "cancel-repair": service.cancel_repair,
            "sync": service.sync,
            "stop": service.stop_check,
            "keep-local": service.keep_local,
        }
        if operation == "check":
            # Validate before dispatch so stale callers receive a visible error.
            with service.lock:
                session = service._session(
                    None if data.get("code_digest") else data.get("revision"),
                    data.get("session_id"),
                )
                if data.get("code_digest") and data["code_digest"] != session["code_digest"]:
                    raise Conflict("The candidate changed. Save and check the current code.")

            def run():
                try:
                    service.check(**data)
                except RuntimeError as exc:
                    service._write_local("check", {"status": "error", "message": str(exc)})

            background.add_task(run)
            return {"message": "Checking saved code…"}
        if operation not in actions:
            return JSONResponse({"detail": "Unknown operation."}, status_code=404)
        try:
            return actions[operation](**data)
        except TypeError as exc:
            raise RuntimeError("Invalid or missing operation fields.") from exc

    web = Path(__file__).with_name("web")
    if (web / "index.html").exists():

        @app.get("/")
        @app.get("/index.html")
        def index():
            page = (web / "index.html").read_text(encoding="utf-8")
            identity = (
                "<script>window.__PRACTICE_ROOM_BUILD__=" + json.dumps(current_build) + ";</script>"
            )
            return HTMLResponse(
                page.replace("<head>", "<head>" + identity, 1),
                headers={"Cache-Control": "no-store"},
            )

        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:

        @app.get("/")
        def setup():
            return HTMLResponse(
                "<h1>Build the practice interface</h1><p>Run the included "
                "Start Study launcher, or run npm ci and npm run build in frontend.</p>"
            )

    return app


def launch(root: Path, port: int = 8765, open_browser=True, restart=False, serve=False):
    from study.launcher import launch as managed_launch
    from study.launcher import serve as serve_app

    if serve:
        return serve_app(root, port)
    return managed_launch(root, port, open_browser, restart=restart)
