from __future__ import annotations

import asyncio
import json
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from study import policy
from study.coach import Coach, CoachRequest, CoachStatus, RequestReceipt
from study.interfaces import (
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
    stopped = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        service.recover_timing()

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
        except RuntimeError:
            pass

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
        return await call_next(request)

    @app.exception_handler(RuntimeError)
    async def recoverable(_request, exc):
        return JSONResponse(
            {"detail": str(exc)}, status_code=409 if isinstance(exc, Conflict) else 400
        )

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/state")
    def state():
        return service.state()

    @app.get("/api/queue")
    def queue(include_new: bool = False, minutes: int = 60):
        if not 5 <= minutes <= 180:
            raise RuntimeError("Choose 5–180 minutes.")
        return service.plan(include_new, minutes)

    @app.get("/api/progress")
    def progress():
        return policy.metrics(root)

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
    def practice_finish(data: FinishPractice):
        try:
            coach.interrupt()
            if coach.worker:
                coach.worker.join(timeout=3)
        except RuntimeError:
            pass
        return service.practice_finish(**data.model_dump())

    @app.post("/api/practice/repair-draft")
    def repair_draft(data: RepairDraft):
        return service.repair_draft(**data.model_dump())

    @app.post("/api/practice/repair-review")
    def repair_review(data: RepairReview):
        service.repair_draft(data.answer, data.revision)
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
        service.repair_draft(data.answer, data.revision)

        def run():
            try:
                service.check_repair()
            except (RuntimeError, SyntaxError) as exc:
                from study.storage import atomic_json

                with service.lock:
                    timer = service._read_local("repair-timer")
                    if timer:
                        timer["check"] = {"status": "error", "message": str(exc)}
                        atomic_json(service.local / "repair-timer.json", timer)

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
        return coach.connect()

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
                status = coach.status(session_id)
                data = json.dumps(status)
                if data != previous:
                    yield f"id: {status['sequence']}\ndata: {data}\n\n"
                    previous = data
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/api/action/{operation}")
    def action(operation: str, data: dict, background: BackgroundTasks):
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
                service._session(data.get("revision"))

            def run():
                try:
                    service.check(**data)
                except RuntimeError as exc:
                    from study.storage import atomic_json

                    atomic_json(
                        service.local / "check.json", {"status": "error", "message": str(exc)}
                    )

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
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:

        @app.get("/")
        def setup():
            return HTMLResponse(
                "<h1>Build the practice interface</h1><p>Run the included "
                "Start Study launcher, or run npm ci and npm run build in frontend.</p>"
            )

    return app


def launch(root: Path, port: int = 8765, open_browser=True):
    import uvicorn

    if open_browser:
        import threading

        threading.Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(create_app(root), host="127.0.0.1", port=port)
