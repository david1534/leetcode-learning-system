"""Disposable browser fixture. Never serves a learner repository or consumes allowance."""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import uvicorn

from study.app import create_app
from study.coach import Coach
from study.codex_runtime import CodexRuntime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="practice-browser-") as directory:
        root = Path(directory).resolve() / "repository"
        root.mkdir()
        os.environ["PRACTICE_ROOM_DATA_HOME"] = str(Path(directory) / "private")

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
        def reset():
            app.state.coach.disconnect()
            with app.state.service.lock:
                app.state.service.store.delete_tree("")
                app.state.coach.preferences = {
                    "automatic": False,
                    "approach": False,
                    "check": False,
                    "model": None,
                    "effort": None,
                }
            return {"reset": True}

        @app.get("/__test__/records")
        def records():
            from study import core, policy

            with app.state.service.lock:
                return {
                    "reviews": core.load_events(root),
                    "parents": policy.practice_sessions(root),
                }

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

        @app.post("/__test__/assessment")
        def assessment():
            with app.state.service.lock:
                session = app.state.service._session()
                session["assessment_mode"] = "independent"
                app.state.service._save(session)
            return {"assessment": True}

        @app.post("/__test__/return-after-days")
        def return_after_days():
            from datetime import UTC, datetime, timedelta

            from study import core

            with app.state.service.lock:
                session = app.state.service._session()
                session["phase_started_at"] = (datetime.now(UTC) - timedelta(days=7)).isoformat()
                session["saved_at"] = session["phase_started_at"]
                core.save_session(root, session)
                app.state.service.timer_checkpoint()
            return {"paused": True}

        @app.post("/__test__/recall")
        def recall():
            from datetime import UTC, datetime, timedelta

            from study import core

            problem = core.problem_by_id(root, "arrays-001-pair-sum")
            core.record_review(
                root,
                problem,
                "good",
                20,
                True,
                0,
                True,
                reviewed_at=datetime.now(UTC) - timedelta(days=8),
            )
            app.state.service.start(problem["id"], "recall", include_new=True, synchronize=False)
            return {"recall": True}

        @app.post("/__test__/coach-expired")
        def coach_expired():
            app.state.coach.connection = "signed_out"
            app.state.coach.message = "Your coaching sign-in expired. Reconnect to sign in again."
            app.state.coach.sequence += 1
            return {"expired": True}

        # The app's static UI catch-all must stay after these fixture-only routes.
        from starlette.routing import Mount

        app.router.routes.sort(key=lambda route: isinstance(route, Mount))
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
