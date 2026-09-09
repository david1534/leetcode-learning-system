"""Deterministic JSONL process for adapter and browser tests. No model/network calls."""

import json
import sys
import threading
import time
import uuid
from pathlib import Path

write_lock = threading.Lock()
threads = {}
cancelled = set()


def emit(value):
    with write_lock:
        print(json.dumps(value), flush=True)


def reply(request_id, result):
    emit({"id": request_id, "result": result})


def complete(thread_id, turn_id, request):
    time.sleep(2 if "slow" in request["message"] else 0.15)
    if turn_id in cancelled:
        return
    context = request["session"]
    evidence = (context.get("reasoning") or {}).get("approach", "")
    payload = {
        "reply": "Trace one small example and explain what your stored state represents.",
        "assistance": "minor",
        "supplied_missing_recall": False,
        "findings": [
            {
                "dimension": "explanation",
                "value": "success",
                "evidence": evidence,
                "explanation": "The learner explained the invariant.",
            },
            {
                "dimension": "constraints",
                "value": "unknown",
                "evidence": "",
                "explanation": "Not recorded.",
            },
        ],
        "proposed_code": (context.get("code") or "") + "\n# Reviewed draft\n"
        if request["allow_code"]
        else None,
        "takeaway": None,
    }
    if request["kind"] == "review":
        payload.update(reply="", assistance="none", proposed_code=None)
    if "unsafe markup" in request["message"]:
        payload["reply"] = (
            "Markup fixture. <script>window.__unsafe = true</script> "
            '<img src=x onerror="window.__unsafe=true"> [unsafe](javascript:alert(1))'
        )
    text = "invalid json" if "malformed" in request["message"] else json.dumps(payload)
    item = {"id": uuid.uuid4().hex, "type": "agentMessage", "phase": "final_answer", "text": text}
    turn = {
        "id": turn_id,
        "status": "completed",
        "items": [
            {"type": "userMessage", "content": [{"type": "text", "text": json.dumps(request)}]},
            item,
        ],
    }
    threads[thread_id]["turns"].append(turn)
    Path("fake-history.json").write_text(json.dumps(threads))
    emit(
        {
            "method": "item/agentMessage/delta",
            "params": {"turnId": turn_id, "delta": "unchecked partial text"},
        }
    )
    emit(
        {
            "method": "item/completed",
            "params": {"threadId": thread_id, "turnId": turn_id, "item": item},
        }
    )
    emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": turn}})


if Path("fake-history.json").exists():
    threads = json.loads(Path("fake-history.json").read_text())
for line in sys.stdin:
    message = json.loads(line)
    method, params, rid = message.get("method"), message.get("params", {}), message.get("id")
    if rid is None:
        continue
    if method == "initialize":
        reply(rid, {"userAgent": "fake-codex"})
    elif method == "account/read":
        reply(rid, {"account": {"type": "chatgpt", "planType": "plus"}})
    elif method == "account/rateLimits/read":
        reply(rid, {"rateLimits": {"primary": {"usedPercent": 12, "resetsAt": 2000000000}}})
    elif method == "model/list":
        reply(
            rid,
            {
                "data": [
                    {
                        "id": "test-model",
                        "displayName": "Test coach",
                        "isDefault": True,
                        "defaultReasoningEffort": "medium",
                        "supportedReasoningEfforts": [{"reasoningEffort": "medium"}],
                    }
                ]
            },
        )
    elif method == "thread/start":
        tid = uuid.uuid4().hex
        threads[tid] = {"id": tid, "turns": []}
        reply(rid, {"thread": threads[tid]})
    elif method in {"thread/resume", "thread/read"}:
        reply(rid, {"thread": threads[params["threadId"]]})
    elif method == "turn/start":
        tid = uuid.uuid4().hex
        request = json.loads(params["input"][0]["text"])
        reply(rid, {"turn": {"id": tid, "status": "inProgress"}})
        threading.Thread(
            target=complete, args=(params["threadId"], tid, request), daemon=True
        ).start()
    elif method == "turn/interrupt":
        cancelled.add(params["turnId"])
        reply(rid, {})
        emit(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": params["threadId"],
                    "turn": {"id": params["turnId"], "status": "interrupted"},
                },
            }
        )
    else:
        reply(rid, {})
