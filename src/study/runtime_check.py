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
from unittest.mock import patch

from study.coach import Coach, CoachRequest, runtime_home
from study.codex_runtime import CodexRuntime
from study.connections import CompanyConnection, ConnectionUpdate
from study.database import StudyStore
from study.managed_codex import CODEX_VERSION, ensure_codex
from study.service import StudyService


def check(
    root: Path | None = None,
    live=False,
    connection="personal",
    company: CompanyConnection | None = None,
):
    if live and os.environ.get("CI"):
        raise RuntimeError("Live account checks are disabled in CI.")
    if live and root is None:
        raise RuntimeError("Pass --root for your Practice Room source checkout.")
    if live and connection == "company" and company is None:
        store = StudyStore(root)
        saved = (
            store.read_json(".study-local/coach/connection.json", {})
            if store.path.is_file()
            else {}
        )
        if not saved.get("company"):
            raise RuntimeError(
                "Save Company settings in Practice Room first, or pass --company-settings."
            )
        company = CompanyConnection.model_validate(saved["company"])
    personal_home = runtime_home(root) if root else None
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
        profiles = {}
        fixture = CompanyConnection(
            base_url="https://provider.invalid/v1",
            model="gpt-6-sol",
            api_key_env="PRACTICE_NATIVE_TEST_KEY",
            organization="test-org",
        )
        with patch.dict(os.environ, {"PRACTICE_NATIVE_TEST_KEY": "unused-protocol-test-key"}):
            for mode, settings in (("personal", None), ("company", fixture)):
                runtime = CodexRuntime(temporary / mode, company=settings, executable=executable)
                try:
                    runtime.start()
                    account = runtime.call("account/read", {"refreshToken": False})
                    if account.get("account") is not None:
                        raise RuntimeError(
                            "The anonymous compatibility check inherited an account."
                        )
                    if mode == "company" and account.get("requiresOpenaiAuth") is not False:
                        raise RuntimeError(
                            "Company configuration unexpectedly requires personal authentication."
                        )
                    profiles[mode] = {"restricted_configuration": True, "inherited_account": False}
                finally:
                    runtime.close()
        result = {
            "version": CODEX_VERSION,
            "native_initialization": True,
            "restricted_configuration": True,
            "protocol_fields": True,
            "inherited_account": False,
            "model_turns_started": 0,
            "connections": profiles,
        }
        if not live:
            return result
        # All learning writes belong to the disposable store. Personal OAuth stays
        # in its existing native home; company authentication is environment-only.
        with patch.dict(os.environ, {"PRACTICE_ROOM_DATA_HOME": str(temporary / "private")}):
            learning = temporary / "learning"
            shutil.copytree(root / "curriculum", learning / "curriculum")
            service = StudyService(learning)
            service.start("arrays-001-pair-sum", include_new=True, synchronize=False)
            service.reasoning("Track earlier values and look up the complement before insertion.")
            runtime_directory = (
                personal_home if connection == "personal" else temporary / "company-live"
            )
            coach = Coach(
                service, lambda _unused: CodexRuntime(runtime_directory, executable=executable)
            )
            coach.save_connection(ConnectionUpdate(selected=connection, company=company))
            try:
                if connection == "personal":
                    coach.runtime.start()
                    account = coach.runtime.call("account/read", {"refreshToken": False}).get(
                        "account"
                    )
                    if not account or account.get("type") != "chatgpt":
                        raise RuntimeError("Sign in with personal ChatGPT in Practice Room first.")
                status = coach.connect()
                if status["connection"] != "connected" or status["usage"]["blocked"]:
                    raise RuntimeError("Coaching is not ready: " + status["message"])
                context = service.coach_context()
                coach.submit(
                    CoachRequest(
                        request_id=uuid.uuid4().hex,
                        session_id=context["session_id"],
                        revision=context["revision"],
                        code_digest=context["code_digest"],
                        message="This is a connection check. Ask me to trace the public example "
                        "in one short sentence. Do not provide code.",
                    )
                )
                result["model_turns_started"] = 1
                coach.worker.join(timeout=180)
                if coach.worker.is_alive():
                    coach.interrupt()
                    raise RuntimeError(
                        "The live reply did not finish. It was not automatically retried."
                    )
                requests = coach.status(context["session_id"])["requests"]
                if len(requests) != 1 or requests[0]["status"] != "completed":
                    detail = requests[0].get("error") if requests else "No request receipt."
                    record = (
                        coach._load("requests/" + requests[0]["request_id"], {}) if requests else {}
                    )
                    diagnostic = {
                        k: record.get(k) for k in ("reply_characters", "validation_errors")
                    }
                    raise RuntimeError(
                        "The live coach reply failed: "
                        + (detail or "Invalid reply.")
                        + " Diagnostics: "
                        + json.dumps(diagnostic)
                    )
                result[connection + "_coach_reply"] = True
            finally:
                coach.disconnect()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--connection", choices=("personal", "company"), default="personal")
    parser.add_argument(
        "--company-settings",
        type=Path,
        help="Private JSON connection settings for an explicit company live check",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the selected connection for exactly one explicit test turn",
    )
    args = parser.parse_args()
    company = None
    if args.company_settings:
        if not args.live or args.connection != "company":
            parser.error("--company-settings requires --live --connection company")
        try:
            company = CompanyConnection.model_validate_json(
                args.company_settings.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            parser.error(
                "The company settings file is missing or invalid; never include credential values."
            )
    print(
        json.dumps(
            check(args.root.resolve() if args.root else None, args.live, args.connection, company),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
