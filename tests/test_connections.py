import json
import os
import sys
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_coach import FAKE, request, wait

from study.app import create_app
from study.coach import Coach
from study.codex_runtime import CONFIG, CodexRuntime
from study.connections import CompanyConnection, ConnectionUpdate, detect_company
from study.service import Conflict


def company(**changes):
    return CompanyConnection(
        base_url="https://gateway.example/v1",
        model="test-model",
        effort="medium",
        api_key_env="TEST_COMPANY_KEY",
        **changes,
    )


def factory(service):
    return Coach(service, lambda directory: CodexRuntime(directory, [sys.executable, str(FAKE)]))


@pytest.fixture
def connected(guided, monkeypatch):
    monkeypatch.setenv("TEST_COMPANY_KEY", "private-test-credential")
    value = factory(guided)
    value.save_connection(ConnectionUpdate(selected="company", company=company()))
    guided.start("arrays-001-pair-sum", include_new=True, synchronize=False)
    guided.reasoning("Track earlier values and look up the complement before insertion.")
    assert value.connect()["connection"] == "connected"
    yield value
    value.disconnect()


def test_detection_is_only_a_suggestion_and_saved_settings_are_independent(guided, monkeypatch):
    path = Path(os.environ["CODEX_HOME"]) / "config.toml"
    path.parent.mkdir()
    path.write_text(
        'model="test-model"\nmodel_provider="work"\n'
        '[model_providers.work]\nbase_url="https://detected.example/v1"\n'
        'env_key="TEST_COMPANY_KEY"\nwire_api="responses"\n'
        '[model_providers.work.http_headers]\nopenai-organization="detected-org"\n'
    )
    value = factory(guided)
    detected = value.connection_settings()
    assert detected["recommendation"] == "company"
    assert detected["selected"] is None
    assert value.runtime.process is None
    assert value.connect()["connection"] == "unavailable"
    config = CompanyConnection.model_validate(detected["detected"])
    value.save_connection(ConnectionUpdate(selected="company", company=config))
    path.write_text('model_provider="openai"\n')
    restarted = factory(guided)
    assert restarted.connection_settings()["company"]["base_url"] == config.base_url
    assert restarted.settings.selected == "company"
    assert restarted.connection_settings()["recommendation"] == "personal"
    assert restarted.runtime.process is None


@pytest.mark.parametrize(
    "value",
    [
        "http://gateway.example/v1",
        "https://user:key@gateway.example/v1",
        "https://gateway.example/v1?key=secret",
        "https://gateway.example/#x",
    ],
)
def test_invalid_endpoints_are_rejected(value):
    with pytest.raises(ValidationError):
        CompanyConnection(base_url=value, model="test-model")


def test_detection_handles_invalid_config_without_returning_credentials(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model_provider = ["private-credential"')
    detected, reason = detect_company(path)
    assert detected is None
    assert "private-credential" not in reason


def test_company_environment_and_config_keep_secrets_out_of_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_COMPANY_KEY", "private-test-credential")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-personal-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "unrelated-aws-key")
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.example")
    monkeypatch.setenv("SSL_CERT_FILE", "corporate-ca.pem")
    runtime = CodexRuntime(tmp_path, company=company(organization="private-org"))
    config = tomllib.loads(runtime.configuration())
    env = runtime.environment(tmp_path / "home")
    assert env["PRACTICE_ROOM_COMPANY_KEY"] == "private-test-credential"
    assert env["PRACTICE_ROOM_COMPANY_ORGANIZATION"] == "private-org"
    assert env["HTTPS_PROXY"] == "https://proxy.example"
    assert env["SSL_CERT_FILE"] == "corporate-ca.pem"
    assert not any(
        k in env for k in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "TEST_COMPANY_KEY")
    )
    assert "private-test-credential" not in runtime.configuration()
    assert "private-org" not in runtime.configuration()
    assert not config.get("forced_login_method")
    for key, value in tomllib.loads(CONFIG)["features"].items():
        assert config["features"][key] == value
    assert "private-test-credential" not in runtime.safe_message("error private-test-credential")
    personal = CodexRuntime(tmp_path)
    assert personal.configuration() == CONFIG
    assert "OPENAI_API_KEY" not in personal.environment(tmp_path / "home")


def test_company_does_not_require_personal_account_or_allowance(connected, monkeypatch):
    value = connected
    sent = []
    original_call = value.runtime.call

    def observe(method, params=None, **kwargs):
        if method == "turn/start":
            sent.append(params)
        return original_call(method, params, **kwargs)

    monkeypatch.setattr(value.runtime, "call", observe)
    assert value.status()["account"] is None
    assert value.usage == {
        "source": "company",
        "known": False,
        "remaining": None,
        "windows": [],
        "blocked": False,
        "conserving": False,
    }
    value.submit(request(value))
    assert wait(value)["status"] == "completed"
    methods = json.loads((value.runtime.directory / "workspace/fake-methods.json").read_text())
    assert "outputSchema" not in sent[0]
    assert json.loads(sent[0]["input"][0]["text"])["response_schema"]["required"]
    assert "account/login/start" not in methods
    assert "account/rateLimits/read" not in methods
    assert value.service._session()["assistance_log"]
    assert "private-test-credential" not in json.dumps(value.status())
    assert "private-test-credential" not in json.dumps(value.service.store.documents())


def test_missing_credential_never_falls_back_to_personal(guided, monkeypatch):
    monkeypatch.delenv("TEST_COMPANY_KEY", raising=False)
    value = factory(guided)
    value.save_connection(ConnectionUpdate(selected="company", company=company()))
    result = value.connect()
    assert result["connection"] == "unavailable"
    assert result["selected_connection"] == "company"
    assert "TEST_COMPANY_KEY" in result["message"]
    assert value.runtime.process is None
    assert result["auth_url"] is None


def test_switching_preserves_code_evidence_preferences_and_conversation_boundaries(connected):
    value = connected
    value.submit(request(value))
    first = wait(value)
    value.worker.join()
    code = value.service._code()
    assistance = list(value.service._session()["assistance_log"])
    company_runtime = value.runtime
    value.configure(automatic=True, approach=True, check=False, model="test-model", effort="medium")
    value.save_connection(ConnectionUpdate(selected="personal"))
    assert value.preferences["automatic"] is False
    assert value.runtime.directory == value.base_runtime_directory
    personal_env = value.runtime.environment(value.runtime.directory / "home")
    assert "TEST_COMPANY_KEY" not in personal_env
    assert "PRACTICE_ROOM_COMPANY_KEY" not in personal_env
    company_runtime.on_event("coach/disconnected", {})
    assert value.connection == "disconnected"
    assert value.connect()["connection"] == "connected"
    company_runtime.on_event("coach/disconnected", {})
    assert value.connection == "connected"
    value.submit(request(value, allow_code=True))
    second = wait(value)
    value.worker.join()
    assert second["status"] == "retry_required"
    assert second["connection_id"] == "personal"
    assert (
        value._load("requests/" + first["request_id"])["thread_id"]
        != value._load("requests/" + second["request_id"])["thread_id"]
    )
    assert value.service._code() == code
    assert value.service._session()["assistance_log"] == assistance
    value.save_connection(ConnectionUpdate(selected="company", company=company()))
    assert value.preferences["automatic"] is True
    assert value.preferences["check"] is False
    assert value.runtime.directory == company_runtime.directory


def test_busy_connection_change_is_rejected_and_old_turns_are_not_reconciled_elsewhere(connected):
    value = connected
    value.submit(request(value, "slow reply"))
    with pytest.raises(Conflict):
        value.save_connection(ConnectionUpdate(selected="personal"))
    value.interrupt()
    record = wait(value)
    value.worker.join()
    saved = value._load("requests/" + record["request_id"])
    saved["status"] = "uncertain"
    value._save("requests/" + saved["request_id"], saved)
    value.save_connection(ConnectionUpdate(selected="personal"))
    value.connect()
    assert value._load("requests/" + saved["request_id"])["status"] == "uncertain"
    assert "thread/read" not in json.loads(
        (value.runtime.directory / "workspace/fake-methods.json").read_text()
    )


def test_endpoint_and_organization_changes_have_distinct_conversations(connected):
    value = connected
    original = value.runtime.directory
    value.save_connection(
        ConnectionUpdate(selected="company", company=company(organization="second-org"))
    )
    assert value.runtime.directory != original
    assert value.preferences["automatic"] is False


def test_legacy_personal_preferences_and_authentication_stay_in_place(guided):
    value = factory(guided)
    original = value.runtime.directory
    (original / "home").mkdir(parents=True)
    auth = original / "home/auth.json"
    auth.write_text("preserved-native-signin")
    preferences = {
        "automatic": True,
        "approach": True,
        "check": False,
        "model": "test-model",
        "effort": "medium",
    }
    value._save("preferences", preferences)
    restarted = factory(guided)
    assert restarted.settings.selected == "personal"
    assert restarted.runtime.directory == original
    assert restarted.preferences == preferences
    assert auth.read_text() == "preserved-native-signin"


def test_connection_api_validates_settings_and_never_returns_a_key(guided, monkeypatch):
    monkeypatch.setenv("TEST_COMPANY_KEY", "private-test-credential")
    client = TestClient(create_app(guided.root, coach_factory=factory), base_url="http://127.0.0.1")
    headers = {"x-study-request": "1"}
    assert client.get("/api/coach/connection").json()["selected"] is None
    assert (
        client.post(
            "/api/coach/connection", json={"selected": "company"}, headers=headers
        ).status_code
        == 422
    )
    result = client.post(
        "/api/coach/connection",
        json={"selected": "company", "company": company().model_dump()},
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["credential_available"] is True
    assert "private-test-credential" not in result.text
    assert "private-test-credential" not in client.get("/api/diagnostics").text
    assert client.post("/api/coach/connection", json={"selected": "personal"}).status_code == 403


def test_draft_export_keeps_connection_settings_and_conversations_private(connected, monkeypatch):
    value = connected
    value.submit(request(value))
    wait(value)
    value.worker.join()
    monkeypatch.setattr(value.service.synchronizer, "wake", lambda: None)
    value.service.synchronizer.enqueue_draft()
    jobs = value.service.store.json_documents(".study-local/outbox/")
    assert jobs
    exported = json.dumps(jobs)
    for private in (
        "gateway.example",
        "TEST_COMPANY_KEY",
        "private-test-credential",
        "Help me reason about my code.",
        "connection_id",
    ):
        assert private not in exported
    assert "attempt/current.py" in jobs[-1]["artifacts"]
    assert value.service._session()["assistance_log"]


def test_failed_native_initialization_closes_process_before_another_start(tmp_path, monkeypatch):
    runtime = CodexRuntime(tmp_path / "runtime", [sys.executable, str(FAKE)])
    original = runtime.call
    monkeypatch.setattr(
        runtime,
        "call",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("initialization failed")),
    )
    with pytest.raises(RuntimeError, match="initialization failed"):
        runtime.start()
    assert runtime.process is None
    monkeypatch.setattr(runtime, "call", original)
    try:
        runtime.start()
        assert runtime.call("account/read")["account"]["type"] == "chatgpt"
    finally:
        runtime.close()


def test_delayed_login_refresh_from_retired_runtime_is_ignored(connected):
    value = connected
    retired = value.runtime
    value.save_connection(ConnectionUpdate(selected="personal"))
    value._refresh_safely(retired)
    assert value.connection == "disconnected"
    assert value.runtime.process is None
