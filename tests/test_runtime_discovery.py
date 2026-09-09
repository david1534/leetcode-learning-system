import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import study.codex_runtime as runtime


def test_supported_candidate_is_used_after_incompatible_path(tmp_path, monkeypatch):
    old, supported = tmp_path / "old.exe", tmp_path / "supported.exe"
    monkeypatch.setattr(runtime, "codex_candidates", lambda: [old, supported])
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            stdout="codex-cli " + ("0.999.0" if command[0] == str(old) else "0.153.4"),
            returncode=0,
        ),
    )
    assert runtime.find_codex() == ([str(supported)], "0.153.4")


@pytest.mark.skipif(os.name != "nt", reason="Windows desktop installation")
def test_desktop_binary_is_found_without_path(tmp_path, monkeypatch):
    binary = tmp_path / "OpenAI/Codex/bin/version-hash/codex.exe"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.delenv("PRACTICE_ROOM_CODEX", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setattr(runtime.shutil, "which", lambda _: None)
    assert runtime.codex_candidates() == [binary]


def test_explicit_path_is_literal_and_does_not_fall_back(tmp_path, monkeypatch):
    binary = tmp_path / "Codex & tools" / "codex.exe"
    binary.parent.mkdir()
    binary.touch()
    monkeypatch.setenv("PRACTICE_ROOM_CODEX", str(binary))
    assert runtime.codex_candidates() == [binary]
    assert runtime.codex_command(binary) == [str(binary)]
    monkeypatch.setenv("PRACTICE_ROOM_CODEX", "missing/codex.exe")
    with pytest.raises(RuntimeError, match="absolute"):
        runtime.codex_candidates()


def test_npm_windows_shim_runs_without_a_shell(tmp_path, monkeypatch):
    shim = tmp_path / "npm & tools/codex.cmd"
    entry = shim.parent / "node_modules/@openai/codex/bin/codex.js"
    entry.parent.mkdir(parents=True)
    entry.touch()
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "node.exe")
    assert runtime.codex_command(shim) == ["node.exe", str(entry)]
    entry.unlink()
    with pytest.raises(RuntimeError, match="incomplete"):
        runtime.codex_command(shim)


def test_failed_handshake_closes_process_and_can_reconnect(tmp_path, monkeypatch):
    adapter = runtime.CodexRuntime(
        tmp_path, [sys.executable, str(Path(__file__).with_name("fake_codex.py"))]
    )
    initialize = adapter._initialize
    processes = []

    def fail():
        processes.append(adapter.process)
        raise RuntimeError("Handshake rejected")

    monkeypatch.setattr(adapter, "_initialize", fail)
    with pytest.raises(RuntimeError, match="rejected"):
        adapter.start()
    assert adapter.process is None
    assert processes[0].poll() is not None
    monkeypatch.setattr(adapter, "_initialize", initialize)
    try:
        adapter.start()
        assert adapter.call("account/read")["account"]["type"] == "chatgpt"
    finally:
        adapter.close()


def test_same_version_with_failed_version_command_is_not_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "codex_candidates", lambda: [tmp_path / "codex"])
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="codex-cli 0.153.4", returncode=1),
    )
    with pytest.raises(RuntimeError, match="not been validated"):
        runtime.find_codex()
