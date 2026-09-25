"""Install the exact official CLI shipped with this adapter, outside user configuration."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from filelock import FileLock

from study.database import data_home
from study.storage import atomic_text

CODEX_VERSION = "0.157.0"


def runtime_directory() -> Path:
    return data_home() / "codex" / CODEX_VERSION


def installed_codex(directory: Path | None = None) -> str | None:
    directory = directory or runtime_directory()
    name = "codex.exe" if os.name == "nt" else "codex"
    candidates = [
        p
        for p in (directory / "node_modules/@openai").rglob(name)
        if p.is_file() and p.parent.name == "bin" and "vendor" in p.parts
    ]
    return str(candidates[0]) if len(candidates) == 1 else None


def ensure_codex() -> str:
    directory = runtime_directory()
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(str(directory / "install.lock"), timeout=120):
        executable = installed_codex(directory)
        if executable and (directory / "installed.json").exists():
            return executable
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        node = shutil.which("node")
        if not npm or not node:
            raise RuntimeError(
                "Install Node.js LTS, then reconnect the coach. Local practice remains available."
            )
        resolved = Path(npm).resolve()
        cli = (
            resolved
            if resolved.suffix == ".js"
            else resolved.parent / "node_modules/npm/bin/npm-cli.js"
        )
        if not cli.is_file():
            raise RuntimeError(
                "The Node.js installation could not be used to prepare coaching. "
                "Reinstall Node.js LTS and reconnect."
            )
        bundle = Path(__file__).with_name("codex_bundle")
        for name in ("package.json", "package-lock.json"):
            atomic_text(directory / name, (bundle / name).read_text(encoding="utf-8"))
        log = directory / "install.log"
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                [
                    node,
                    str(cli),
                    "ci",
                    "--prefix",
                    str(directory),
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    "--cache",
                    str(data_home() / "npm-cache"),
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        executable = installed_codex(directory)
        if result.returncode or not executable:
            raise RuntimeError(
                "The coach runtime could not be installed. Check the internet "
                "connection and retry. The private install log has details."
            )
        atomic_text(directory / "installed.json", '{"version":"' + CODEX_VERSION + '"}\n')
        return executable
