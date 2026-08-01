from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from .evaluation_v2 import EvaluationCase, grade_run, load_cases, release_gate, validate_dataset


def parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        event = re.search(r"^event: (.+)$", block, re.MULTILINE)
        data = re.search(r"^data: (.+)$", block, re.MULTILINE)
        if event and data:
            events.append({"event": event.group(1), "data": json.loads(data.group(1))})
    return events


def summarize_turn(events: list[dict[str, Any]], elapsed_ms: int) -> dict[str, Any]:
    done = next((item["data"] for item in reversed(events) if item["event"] == "done"), {})
    model = next((item["data"] for item in events if item["event"] == "model_selected"), {})
    metrics = next((item["data"] for item in events if item["event"] == "metrics"), {})
    token_text = "".join(str(item["data"].get("token", "")) for item in events if item["event"] == "token")
    answer = str(done.get("answer", ""))
    stream_match = token_text.strip() == answer.strip()
    resolved = done.get("resolved_context") or {}
    return {
        "answer": answer,
        "intent": done.get("intent"),
        "requiresHuman": done.get("requires_human"),
        "toolCalls": done.get("tool_calls", []),
        "citations": done.get("citations", []),
        "ui": done.get("ui", []),
        "resolvedOrderId": resolved.get("orderId"),
        "modelProfile": model.get("profile"),
        "modelReasons": model.get("reasons", []),
        "metrics": metrics,
        "latencyMs": elapsed_ms,
        "streamMatch": stream_match,
        "events": [item["event"] for item in events],
    }


def summarize_response(done: dict[str, Any], elapsed_ms: int) -> dict[str, Any]:
    resolved = done.get("resolved_context") or {}
    return {
        "answer": str(done.get("answer", "")), "intent": done.get("intent"),
        "requiresHuman": done.get("requires_human"), "toolCalls": done.get("tool_calls", []),
        "citations": done.get("citations", []), "ui": done.get("ui", []),
        "resolvedOrderId": resolved.get("orderId"), "modelProfile": None,
        "modelReasons": [], "metrics": {}, "latencyMs": elapsed_ms,
        "streamMatch": True, "events": ["interaction", "done"],
    }


async def run_case(client: httpx.AsyncClient, case: EvaluationCase, base_url: str) -> dict[str, Any]:
    conversation_id = case.conversation_id or str(uuid4())
    turns: list[dict[str, Any]] = []
    for turn in case.turns:
        started = time.perf_counter()
        try:
            if turn.select_option_index is not None:
                previous_ui = next((item for item in reversed(turns[-1].get("ui", [])) if item.get("continuation_token")), None)
                if previous_ui is None:
                    raise ValueError("INTERACTION_UI_MISSING")
                options = previous_ui.get("options", [])
                option = options[turn.select_option_index]
                response = await client.post(f"{base_url}/agent/interactions", json={
                    "interaction_id": str(uuid4()), "component_id": previous_ui["id"],
                    "action": "SELECT", "values": option.get("value", {}),
                    "continuation_token": previous_ui["continuation_token"],
                    "customer_id": case.customer_id, "conversation_id": conversation_id,
                }, timeout=40)
                response.raise_for_status()
                summary = summarize_response(response.json(), round((time.perf_counter() - started) * 1000))
            else:
                payload = {
                    "message_id": str(uuid4()), "content": turn.message,
                    "customer_id": case.customer_id, "actor_role": "CUSTOMER",
                    "channel": "WEB", "conversation_id": conversation_id,
                    "page_context": turn.page_context,
                }
                response = await client.post(f"{base_url}/agent/stream", json=payload, timeout=40)
                response.raise_for_status()
                summary = summarize_turn(parse_sse(response.text), round((time.perf_counter() - started) * 1000))
        except Exception as error:
            summary = {"answer": "", "error": type(error).__name__, "latencyMs": round((time.perf_counter() - started) * 1000)}
        turns.append(summary)
    grade = grade_run(case, turns)
    if any(turn.get("streamMatch") is False for turn in turns):
        grade["errors"] = sorted(set([*grade["errors"], "STREAM_MISMATCH"]))
        grade["passed"] = False
    return {"id": case.id, "clusterId": case.cluster_id, "split": case.split, "category": case.category, **grade, "results": turns}


async def main_async(args: argparse.Namespace) -> None:
    cases = load_cases(Path(args.dataset))
    integrity = validate_dataset(cases)
    if not integrity["valid"] and not args.allow_invalid_dataset:
        raise ValueError(f"Invalid evaluation dataset: {integrity['errors']}")
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:
        async def bounded(case: EvaluationCase) -> dict[str, Any]:
            async with semaphore:
                return await run_case(client, case, args.base_url)
        results = await asyncio.gather(*(bounded(case) for case in cases))
    gate = release_gate(results)
    latencies = [turn["latencyMs"] for result in results for turn in result["results"] if turn.get("latencyMs") is not None]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "datasetIntegrity": integrity,
        "releaseGate": gate,
        "latency": {
            "p50": statistics.median(latencies) if latencies else None,
            "p95": sorted(latencies)[max(0, round(len(latencies) * 0.95) - 1)] if latencies else None,
        },
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"releaseGate": gate, "output": str(output)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="/datasets/evaluation-v2.sample.json")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", default="/datasets/artifacts/evaluation-v2-report.json")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--allow-invalid-dataset", action="store_true")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
