"""Disposable browser fixture. Never serves a learner repository or consumes allowance."""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import uvicorn
from fastapi import Request

from study.app import create_app
from study.coach import Coach
from study.codex_runtime import CodexRuntime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="practice-browser-") as directory:
        root = Path(directory).resolve()

        def seed():
            shutil.copytree(source / "curriculum", root / "curriculum")
            (root / "pyproject.toml").write_text("[project]\nname='browser-fixture'\n")

        seed()

        def factory(service):
            return Coach(
                service,
                lambda private: CodexRuntime(
                    private, [sys.executable, str(source / "tests/fake_codex.py")]
                ),
            )

        app = create_app(root, coach_factory=factory)

        @app.post("/__test__/reset")
        async def reset(request: Request):
            app.state.coach.disconnect()
            with app.state.service.lock:
                for name in ("attempt", "progress", "solutions", "reflections"):
                    target = (root / name).resolve()
                    assert target.is_relative_to(root) and target != root
                    if target.exists():
                        shutil.rmtree(target)
                for path in (root / ".study-local").glob("*"):
                    if path.name == "session.lock":
                        continue
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                app.state.coach.directory.mkdir(exist_ok=True)
            return {"reset": True}

        @app.get("/__test__/records")
        def records():
            from study import core, policy

            return {"reviews": core.load_events(root), "parents": policy.practice_sessions(root)}

        @app.post("/__test__/repair")
        def seed_repair():
            from datetime import UTC, datetime, timedelta

            from study import core

            service = app.state.service
            session = service.start("arrays-001-pair-sum", include_new=True, synchronize=False)[
                "session"
            ]
            core.record_learning_error(
                root,
                "hashmap-bucket-lifecycle",
                "implementation",
                "execution-slip",
                "blocking",
                "Overwrote earlier values.",
                "An existing key is present.",
                "Append without replacing earlier values.",
                "Append a third value and check all three remain.",
                datetime.now(UTC) - timedelta(days=2),
            )
            service.finish(
                session["session_id"],
                "unknown",
                "Practice preserving earlier values.",
                stopped=True,
            )
            return {"seeded": True}

        # The app's static UI catch-all must stay after these fixture-only routes.
        from starlette.routing import Mount

        app.router.routes.sort(key=lambda route: isinstance(route, Mount))
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
