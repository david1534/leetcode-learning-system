from __future__ import annotations

import webbrowser
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from study import policy
from study.service import Conflict, StudyService


def create_app(root: Path) -> FastAPI:
    app = FastAPI(title="Practice Room", docs_url=None, redoc_url=None)
    service = StudyService(root)
    app.state.service = service

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

    @app.post("/api/action/{operation}")
    def action(operation: str, data: dict, background: BackgroundTasks):
        actions = {
            "start": service.start,
            "worked-example": service.worked_example,
            "recover": service.recover,
            "choose-attempt": service.choose_attempt,
            "reasoning": service.reasoning,
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
