import os
import shutil
import sys
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
PROTECTED = [
    SOURCE_ROOT / name
    for name in ("attempt", "progress", "solutions", "reflections", ".study-local")
]


def pytest_sessionstart(session):
    """Fail before a test can write to the actual learner's workspace."""

    def protect(event, args):
        paths = []
        if event == "open":
            path, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC
            ):
                paths = [path]
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.truncate"}:
            paths = [args[0]]
        elif event in {"os.rename", "os.link", "os.symlink"}:
            paths = list(args[:2])
        for value in paths:
            if isinstance(value, (str, bytes, os.PathLike)):
                target = Path(os.fsdecode(value)).resolve()
                if any(target == p or target.is_relative_to(p) for p in PROTECTED):
                    raise RuntimeError("Tests cannot mutate the real learning workspace.")

    sys.addaudithook(protect)


@pytest.fixture(autouse=True)
def isolated_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "PRACTICE_ROOM_PRIVATE_HOME", str(tmp_path.parent / (tmp_path.name + "-coach"))
    )


@pytest.fixture(scope="session")
def repo_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("catalog-snapshot")
    for name in ("curriculum", "progress", "solutions", "reflections"):
        if (SOURCE_ROOT / name).exists():
            shutil.copytree(SOURCE_ROOT / name, root / name)
    shutil.copy2(SOURCE_ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


@pytest.fixture
def guided(tmp_path, repo_root):
    from study.service import StudyService

    shutil.copytree(repo_root / "curriculum", tmp_path / "curriculum")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test-study'\n")
    return StudyService(tmp_path)
