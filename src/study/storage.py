from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows can briefly deny replacement while another process reads the file.
        # Keep the complete old version until replacement succeeds; never truncate it.
        for retry in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if retry == 7:
                    raise
                time.sleep(0.01 * (retry + 1))
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value: dict) -> None:
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")
