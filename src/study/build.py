"""Shared release and runtime identity."""

import hashlib
from functools import lru_cache
from pathlib import Path

VERSION = "0.4.0"
API_VERSION = 2


@lru_cache(maxsize=1)
def build_id():
    root = Path(__file__).parent
    checksum = hashlib.sha256(VERSION.encode())
    paths = [*root.glob("*.py"), *root.joinpath("web").rglob("*")]
    for path in sorted(paths):
        if path.is_file():
            checksum.update(path.relative_to(root).as_posix().encode())
            checksum.update(path.read_bytes())
    return checksum.hexdigest()[:24]
