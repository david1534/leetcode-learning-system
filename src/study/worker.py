"""Standalone child entry point: deliberately imports no study modules."""

from __future__ import annotations

import copy
import json
import sys
import types
from pathlib import Path


def evaluate(directory: Path, problem: dict) -> list[dict]:
    source = (directory / "candidate.py").read_text(encoding="utf-8-sig")
    module = types.ModuleType("candidate")
    failures = []
    try:
        exec(compile(source, "candidate.py", "exec"), module.__dict__)
        function = getattr(module, problem["function"])
        if problem.get("validator") == "codec":
            if not callable(module.decode_strings):
                raise TypeError("decode_strings must be callable")
    except BaseException as exc:
        return [{"index": 0, "expected": None, "error": f"{type(exc).__name__}: {exc}"}]
    for index, case in enumerate(problem["cases"], 1):
        try:
            actual = function(*copy.deepcopy(case["args"]))
            if problem.get("validator") == "codec":
                if not isinstance(actual, str):
                    raise TypeError("encode_strings must return a single string")
                # Decode in a fresh module: retained input in a global cannot fake a codec.
                fresh = types.ModuleType("decoder")
                exec(compile(source, "candidate.py", "exec"), fresh.__dict__)
                actual = fresh.decode_strings(actual)
            if type(actual) is not type(case["expected"]) or actual != case["expected"]:
                failures.append(
                    {"index": index, "expected": case["expected"], "actual": repr(actual)[:500]}
                )
        except BaseException as exc:
            failures.append(
                {
                    "index": index,
                    "expected": case["expected"],
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
    return failures


if __name__ == "__main__":
    request, response = map(Path, sys.argv[1:])
    result = evaluate(request.parent, json.loads(request.read_text(encoding="utf-8")))
    response.write_text(json.dumps(result), encoding="utf-8")
