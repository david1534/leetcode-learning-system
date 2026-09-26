"""Transactional local documents; Git files are imports and deliberate exports.

Keeping the existing artifact shapes makes historical evidence inspectable without
maintaining a second learning model. A completion writes all of its documents in
one SQLite transaction. Connections are short lived and nested service/core calls
share only the current thread's transaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from filelock import FileLock

SCHEMA_VERSION = 1
_transactions = threading.local()
PUBLIC_PREFIXES = (
    "progress/reviews/",
    "progress/corrections/",
    "progress/learning-events/",
    "progress/practice-sessions/",
    "progress/attempts/",
    "progress/orphan-drafts/",
    "solutions/",
    "reflections/",
)


def workspace_id(root: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(root.resolve())).encode()).hexdigest()[:24]


def data_home() -> Path:
    override = os.environ.get("PRACTICE_ROOM_DATA_HOME")
    if override:
        return Path(override).resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local/share") / "PracticeRoom"


def existing_store(root: Path):
    store = StudyStore(root)
    return store if store.path.is_file() else None


def encoded(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def same_document(left: str, right: str) -> bool:
    try:
        return json.loads(left) == json.loads(right)
    except (ValueError, TypeError):
        return left == right


class StudyStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = data_home() / "workspaces" / workspace_id(root)
        if self.directory.is_relative_to(self.root):
            raise RuntimeError("Practice Room's data directory must be outside the repository.")
        self.path = self.directory / "practice.sqlite3"

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.directory / "initialize.lock"), timeout=5):
            with self.connection() as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise RuntimeError(
                        "This data was saved by a newer Practice Room. Update the app."
                    )
                if version and version < SCHEMA_VERSION:
                    self.backup()
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS documents (
                        path TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS imports (
                        source TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL,
                        content TEXT NOT NULL, imported_at TEXT NOT NULL,
                        PRIMARY KEY (source, path, digest)
                    );
                    PRAGMA user_version=1;
                """)
        return self

    @contextmanager
    def connection(self):
        active = getattr(_transactions, "active", {})
        if str(self.path) in active:
            yield active[str(self.path)]
            return
        connection = sqlite3.connect(self.path, timeout=3, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        active = getattr(_transactions, "active", {})
        if str(self.path) in active:
            yield active[str(self.path)]
            return
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _transactions.active = {**active, str(self.path): connection}
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            finally:
                _transactions.active = active

    @staticmethod
    def valid_path(path: str) -> str:
        value = PurePosixPath(path)
        if not path or value.is_absolute() or ".." in value.parts or "\\" in path or ":" in path:
            raise ValueError("Invalid saved document path.")
        return value.as_posix()

    def read_text(self, path: str, default=None):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT content FROM documents WHERE path=?", (self.valid_path(path),)
            ).fetchone()
        return row[0] if row else default

    def read_json(self, path: str, default=None):
        value = self.read_text(path)
        return json.loads(value) if value is not None else default

    def write_text(self, path: str, text: str):
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO documents VALUES (?, ?, ?) ON CONFLICT(path) DO UPDATE SET "
                "content=excluded.content, updated_at=excluded.updated_at "
                "WHERE documents.content != excluded.content",
                (self.valid_path(path), text, datetime.now(UTC).isoformat()),
            )

    def write_json(self, path: str, value):
        self.write_text(path, encoded(value))

    def exists(self, path: str) -> bool:
        return self.read_text(path) is not None

    def delete(self, path: str):
        with self.connection() as connection:
            connection.execute("DELETE FROM documents WHERE path=?", (self.valid_path(path),))

    def paths(self, prefix="", suffix="") -> list[str]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT path FROM documents WHERE substr(path, 1, ?)=? ORDER BY path",
                (len(prefix), prefix),
            ).fetchall()
        return [row[0] for row in rows if row[0].endswith(suffix)]

    def documents(self, prefix="") -> dict[str, str]:
        with self.connection() as connection:
            return dict(
                connection.execute(
                    "SELECT path, content FROM documents WHERE substr(path, 1, ?)=? ORDER BY path",
                    (len(prefix), prefix),
                )
            )

    def json_documents(self, prefix: str) -> list[dict]:
        return [self.read_json(path) for path in self.paths(prefix, ".json")]

    def delete_tree(self, prefix: str):
        # Removes database documents only, never a directory in the source checkout.
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM documents WHERE substr(path, 1, ?)=?", (len(prefix), prefix)
            )

    def backup(self) -> Path:
        target = self.directory / "backups" / f"practice-{uuid.uuid4().hex}.sqlite3"
        target.parent.mkdir(exist_ok=True)
        with self.connection() as source:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("The practice backup could not be verified.")
            finally:
                destination.close()
        return target

    def import_documents(self, documents: dict[str, str], source: str) -> dict:
        """Idempotent import, retaining conflicting originals in an immutable ledger."""
        result = {"imported": 0, "conflicts": [], "source": source}
        with self.transaction() as connection:
            identities = {}
            for prefix, field in (
                ("progress/reviews/", "event_id"),
                ("progress/learning-events/", "event_id"),
                ("progress/corrections/", "correction_id"),
                ("progress/practice-sessions/", "practice_id"),
            ):
                for path in self.paths(prefix, ".json"):
                    event = self.read_json(path)
                    if event.get(field):
                        identities[(prefix, event[field])] = path
            for original_path, text in documents.items():
                original_path = self.valid_path(original_path)
                checksum = hashlib.sha256(text.encode()).hexdigest()
                recorded = connection.execute(
                    "SELECT 1 FROM imports WHERE source=? AND path=? AND digest=?",
                    (source, original_path, checksum),
                ).fetchone()
                if recorded:
                    continue
                path = original_path.replace(".practice/", "attempt/", 1)
                for prefix, field in (
                    ("progress/reviews/", "event_id"),
                    ("progress/learning-events/", "event_id"),
                    ("progress/corrections/", "correction_id"),
                    ("progress/practice-sessions/", "practice_id"),
                ):
                    if path.startswith(prefix) and path.endswith(".json"):
                        event = json.loads(text)
                        if event.get(field):
                            identity = (prefix, event[field])
                            path = identities.setdefault(identity, path)
                current = self.read_text(path)
                if current is None:
                    self.write_text(path, text)
                    result["imported"] += 1
                elif not same_document(current, text):
                    conflict_id = hashlib.sha256(
                        (source + original_path + checksum).encode()
                    ).hexdigest()[:24]
                    self.write_json(
                        f".study-local/conflicts/{conflict_id}.json",
                        {
                            "id": conflict_id,
                            "path": path,
                            "source": source,
                            "incoming": text,
                            "saved_digest": hashlib.sha256(current.encode()).hexdigest(),
                            "status": "unresolved",
                        },
                    )
                    result["conflicts"].append(conflict_id)
                connection.execute(
                    "INSERT INTO imports VALUES (?, ?, ?, ?, ?)",
                    (
                        source,
                        original_path,
                        checksum,
                        text,
                        datetime.now(UTC).isoformat(),
                    ),
                )
            self.write_json(".study-local/import-report.json", result)
        return result

    def import_workspace(self):
        documents = {}
        for directory in (
            "attempt",
            ".practice",
            "progress",
            "solutions",
            "reflections",
            ".study-local",
        ):
            for path in sorted((self.root / directory).rglob("*")):
                if not path.is_file() or any(
                    part in {"__pycache__", "runtime", "home"} for part in path.parts
                ):
                    continue
                if path.suffix not in {".py", ".json", ".md", ".txt"}:
                    continue
                relative = path.relative_to(self.root).as_posix()
                documents[relative] = path.read_text(encoding="utf-8-sig")
        return self.import_documents(documents, "legacy-workspace")


class TransactionLock:
    """The service's reentrant cross-process mutation boundary."""

    def __init__(self, store: StudyStore):
        self.store = store
        self.file_lock = FileLock(str(store.directory / "session.lock"), timeout=3)
        self.contexts = threading.local()

    def __enter__(self):
        stack = ExitStack()
        try:
            stack.enter_context(self.file_lock)
            stack.enter_context(self.store.transaction())
        except BaseException:
            stack.close()
            raise
        self.contexts.stack = [*getattr(self.contexts, "stack", []), stack]
        return self

    def __exit__(self, *exc):
        return self.contexts.stack.pop().__exit__(*exc)
