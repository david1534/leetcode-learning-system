import json
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from study.app import create_app
from study.coach import Coach, CoachRequest, allowance
from study.codex_runtime import CONFIG, CodexRuntime
from study.service import Conflict

FAKE = Path(__file__).with_name("fake_codex.py")


def factory(service):
    return Coach(service, lambda directory: CodexRuntime(directory, [sys.executable, str(FAKE)]))


@pytest.fixture
def coach(guided):
    value = factory(guided)
    guided.practice_start(include_new=True, synchronize=False)
    guided.reasoning("Check earlier values before adding the current one.")
    yield value
    value.disconnect()


def request(coach, message="Help me reason about my code.", **kwargs):
    s = coach.service.state()["session"]
    return CoachRequest(
        request_id=uuid.uuid4().hex,
        session_id=s["session_id"],
        revision=s["revision"],
        code_digest=s["code_digest"],
        message=message,
        **kwargs,
    )


def wait(coach):
    deadline = time.monotonic() + 8
    while coach.active and time.monotonic() < deadline:
        time.sleep(0.02)
    assert coach.active is None
    return coach.status()["requests"][-1]


def test_assessment_does_not_call_model_or_reveal_help(coach):
    result = coach.submit(request(coach))
    assert result["status"] == "conversion_required"
    assert coach.runtime.process is None
    assert not coach.service.state()["session"].get("assistance_log")


def test_jsonl_auth_reply_and_duplicate_request(coach):
    assert coach.connect()["connection"] == "connected"
    coach.service.convert_to_practice()
    sent = request(coach)
    coach.submit(sent)
    result = wait(coach)
    assert result["status"] == "completed"
    assert result["assistance"] == "minor"
    assert "unchecked partial" not in json.dumps(coach.status())
    coach.submit(sent)
    session = coach.service.state()["session"]
    assert len(session["assistance_log"]) == 1
    assert coach.service.evaluate()["recall_outcome"] == "success"
    assert "context" not in result


def test_code_proposal_requires_explicit_apply_and_rejects_stale_draft(coach):
    coach.connect()
    coach.service.convert_to_practice()
    before = coach.service.state()["session"]["code"]
    sent = request(coach, allow_code=True)
    coach.submit(sent)
    result = wait(coach)
    assert result["diff"] and result["assistance"] == "substantial"
    s = coach.service.state()["session"]
    assert s["code"] == before
    coach.service.save_code(before + "\n# learner edit\n", s["revision"])
    with pytest.raises(Conflict):
        coach.apply(sent.request_id, coach.service.state()["session"]["revision"])


def test_interruption_does_not_stop_code_runner_or_lose_question(coach):
    coach.connect()
    coach.service.convert_to_practice()
    coach.submit(request(coach, "slow response please"))
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        record = coach._load("requests/" + coach.active)
        if record.get("turn_id"):
            break
        time.sleep(0.02)
    coach.interrupt()
    assert wait(coach)["status"] == "interrupted"
    assert not (coach.service.local / "stop-check").exists()
    assert (coach.service.root / "attempt/current.py").exists()


def test_malformed_reply_is_not_displayed_or_recorded_as_assistance(coach):
    coach.connect()
    coach.service.convert_to_practice()
    coach.submit(request(coach, "malformed reply"))
    assert wait(coach)["status"] == "interrupted"
    assert not coach.service.state()["session"].get("assistance_log")


def test_stale_response_cannot_change_evidence(coach):
    coach.connect()
    coach.service.convert_to_practice()
    coach.submit(request(coach, "slow reply"))
    s = coach.service.state()["session"]
    coach.service.save_code(s["code"] + "\n# changed\n", s["revision"])
    assert wait(coach)["status"] == "stale"
    assert not coach.service.state()["session"].get("assistance_log")


@pytest.mark.parametrize(
    "used,blocked,conserving", [(0, False, False), (80, False, True), (100, True, True)]
)
def test_allowance_uses_remaining_percent(used, blocked, conserving):
    result = allowance({"rateLimits": {"primary": {"usedPercent": used}}})
    assert result["blocked"] == blocked
    assert result["conserving"] == conserving
    assert allowance({})["blocked"]


def test_config_does_not_expose_execution_or_api_fallback():
    import tomllib

    config = tomllib.loads(CONFIG)
    assert config["forced_login_method"] == "chatgpt"
    assert config["web_search"] == "disabled"
    assert config["sandbox_mode"] == "read-only"
    assert config["features"]["shell_tool"] is False
    assert config["features"]["multi_agent"] is False
    assert config["apps"]["_default"]["enabled"] is False


def test_typed_api_and_origin_guards(guided):
    client = TestClient(create_app(guided.root, coach_factory=factory), base_url="http://127.0.0.1")
    headers = {"x-study-request": "1"}
    assert (
        client.post("/api/practice/start", json={"minutes": -1}, headers=headers).status_code == 422
    )
    assert client.post("/api/coach/connect", json={}).status_code == 403
    assert (
        client.post(
            "/api/coach/apply", json={"request_id": "../../secret", "revision": 1}, headers=headers
        ).status_code
        == 422
    )
    assert client.get("/api/coach/status").json()["connection"] == "disconnected"


def test_missing_and_incompatible_cli_disable_coaching(guided, monkeypatch):
    from types import SimpleNamespace

    import study.codex_runtime as runtime

    monkeypatch.setattr(runtime.shutil, "which", lambda _: None)
    value = Coach(guided)
    assert not value.runtime.directory.is_relative_to(guided.root)
    assert value.connect()["connection"] == "unavailable"
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "codex")
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="codex-cli 0.999.0")
    )
    assert "not been validated" in value.connect()["message"]
    assert value.runtime.process is None


def test_unknown_and_exhausted_allowance_never_start_a_turn(coach, monkeypatch):
    coach.connect()
    coach.service.convert_to_practice()
    monkeypatch.setattr(coach, "refresh", lambda: None)
    for result in ({}, {"rateLimits": {"primary": {"usedPercent": 100}}}):
        coach.usage = allowance(result)
        with pytest.raises(RuntimeError, match="allowance"):
            coach.submit(request(coach))
    assert coach.active is None


def test_duplicate_id_with_different_content_is_rejected(coach):
    sent = request(coach)
    coach.submit(sent)
    altered = sent.model_copy(update={"message": "A different question"})
    with pytest.raises(Conflict, match="different question"):
        coach.submit(altered)


def test_immediate_interrupt_and_reconnect_preserve_request(coach):
    coach.connect()
    coach.service.convert_to_practice()
    sent = request(coach, "slow response")
    coach.submit(sent)
    coach.interrupt()
    assert wait(coach)["status"] == "interrupted"
    coach.disconnect()
    coach.connect()
    assert coach.status()["requests"][-1]["message"] == "slow response"


def test_completed_reply_is_reconciled_without_resending(coach):
    coach.connect()
    coach.service.convert_to_practice()
    sent = request(coach)
    coach.submit(sent)
    wait(coach)
    record = coach._load("requests/" + sent.request_id)
    record["status"] = "uncertain"
    coach._save("requests/" + sent.request_id, record)
    coach.reconcile()
    assert len(coach.service.state()["session"]["assistance_log"]) == 1


def test_more_substantive_help_needs_a_saved_retry(coach):
    coach.connect()
    coach.service.convert_to_practice()
    coach.submit(request(coach))
    wait(coach)
    coach.submit(request(coach, allow_code=True))
    assert wait(coach)["status"] == "retry_required"
    assert len(coach.service.state()["session"]["assistance_log"]) == 1
    coach.service.record_retry(
        "On the values 2 and 5, I check whether the earlier value completes 7."
    )
    coach.submit(request(coach, allow_code=True))
    assert wait(coach)["status"] == "completed"
    assert len(coach.service.state()["session"]["assistance_log"]) == 2


def test_login_cancel_and_api_key_session_remain_optional(coach, monkeypatch):
    coach._event("account/login/completed", {"success": False})
    assert coach.status()["connection"] == "signed_out"
    monkeypatch.setattr(coach.runtime, "start", lambda: None)
    monkeypatch.setattr(coach.runtime, "call", lambda *a, **k: {"account": {"type": "apiKey"}})
    assert coach.connect()["connection"] == "unavailable"
    assert "API billing is disabled" in coach.status()["message"]
    assert coach.service.state()["session"]["code"]


def test_checkpoint_preferences_are_independent(coach):
    coach.connect()
    coach.service.convert_to_practice()
    coach.configure(approach=False, check=True)
    assert coach.submit(request(coach, kind="approach"))["status"] == "skipped"
    assert coach.active is None
    assert coach.submit(request(coach, kind="check"))["status"] == "queued"
    assert wait(coach)["status"] == "completed"


def test_launcher_reuses_only_the_same_workspace(guided, monkeypatch):
    import io

    import study.app as app

    client = TestClient(create_app(guided.root, coach_factory=factory), base_url="http://127.0.0.1")
    health = client.get("/api/health").json()
    monkeypatch.setattr(
        app.urllib.request, "urlopen", lambda *a, **k: io.StringIO(json.dumps(health))
    )
    opened = []
    monkeypatch.setattr(app.webbrowser, "open", opened.append)
    app.launch(guided.root)
    assert opened == ["http://127.0.0.1:8765"]
    with pytest.raises(RuntimeError, match="Another workspace"):
        app.launch(guided.root.parent)
