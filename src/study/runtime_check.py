"""Account-free native compatibility check; --live explicitly permits one coach turn."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from study.coach import Coach, CoachRequest, runtime_home
from study.codex_runtime import CodexRuntime
from study.managed_codex import CODEX_VERSION, ensure_codex
from study.service import StudyService


def check(root: Path | None = None, live=False):
    if live and os.environ.get("CI"):
        raise RuntimeError("Live account checks are disabled in CI.")
    if live and root is None:
        raise RuntimeError("Pass --root for the app where you signed in with personal ChatGPT.")
    executable = ensure_codex()
    with tempfile.TemporaryDirectory(prefix="practice-native-check-") as temporary:
        temporary = Path(temporary)
        schemas = temporary / "schemas"
        subprocess.run(
            [executable, "app-server", "generate-json-schema", "--out", str(schemas)],
            check=True,
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        expected = {
            "v1/InitializeParams.json": {"clientInfo", "capabilities"},
            "v2/ThreadStartParams.json": {
                "cwd",
                "sandbox",
                "approvalPolicy",
                "baseInstructions",
                "model",
                "serviceName",
            },
            "v2/TurnStartParams.json": {"threadId", "input", "outputSchema", "effort", "model"},
        }
        for name, fields in expected.items():
            actual = json.loads((schemas / name).read_text(encoding="utf-8"))
            if not fields <= actual.get("properties", {}).keys():
                raise RuntimeError("The pinned native protocol does not match the adapter: " + name)
        runtime = CodexRuntime(temporary / "anonymous")
        try:
            runtime.start()
            account = runtime.call("account/read", {"refreshToken": False})
            if account.get("account") is not None:
                raise RuntimeError(
                    "The anonymous compatibility check unexpectedly inherited an account."
                )
        finally:
            runtime.close()
        result = {
            "version": CODEX_VERSION,
            "native_initialization": True,
            "restricted_configuration": True,
            "protocol_fields": True,
            "inherited_account": False,
            "model_turns_started": 0,
        }
        if not live:
            return result
        # A disposable learning workspace uses the app's existing Codex-managed
        # sign-in directly. Credentials are never read, copied, or printed here.
        learning = temporary / "learning"
        shutil.copytree(root / "curriculum", learning / "curriculum")
        service = StudyService(learning)
        service.start("arrays-001-pair-sum", include_new=True, synchronize=False)
        service.reasoning("Track earlier values and look up the complement before insertion.")
        coach = Coach(service, lambda _unused: CodexRuntime(runtime_home(root)))
        try:
            coach.runtime.start()
            account = coach.runtime.call("account/read", {"refreshToken": False}).get("account")
            if not account or account.get("type") != "chatgpt":
                raise RuntimeError(
                    "Sign in with personal ChatGPT in Practice Room first, then rerun this check."
                )
            status = coach.connect()
            if status["connection"] != "connected" or status["usage"]["blocked"]:
                raise RuntimeError(
                    "Refresh your included allowance in Practice Room before the live check."
                )
            context = service.coach_context()
            coach.submit(
                CoachRequest(
                    request_id=uuid.uuid4().hex,
                    session_id=context["session_id"],
                    revision=context["revision"],
                    code_digest=context["code_digest"],
                    message=(
                        "This is a connection check. In one short sentence, ask me to trace "
                        "the public example. Do not provide code."
                    ),
                )
            )
            result["model_turns_started"] = 1
            coach.worker.join(timeout=180)
            if coach.worker.is_alive():
                coach.interrupt()
                raise RuntimeError(
                    "The live reply did not finish. Its request was not automatically retried."
                )
            requests = coach.status(context["session_id"])["requests"]
            if len(requests) != 1 or requests[0]["status"] != "completed":
                raise RuntimeError(
                    "The live coach reply could not be validated. Inspect the private app "
                    "diagnostics."
                )
            result["personal_coach_reply"] = True
        finally:
            coach.disconnect()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use personal ChatGPT for exactly one explicit test turn",
    )
    args = parser.parse_args()
    print(json.dumps(check(args.root.resolve() if args.root else None, args.live), indent=2))


if __name__ == "__main__":
    main()
