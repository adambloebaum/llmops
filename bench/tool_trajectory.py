#!/usr/bin/env python3
import concurrent.futures
import json
import os
import statistics
import time
import urllib.request


BASE_URL = os.environ.get("LLM_BASE_URL", "http://100.114.124.62:8000/v1")
MODEL = os.environ.get("SERVED_MODEL_NAME", "qwen2.5-coder-7b")
CONCURRENCIES = (1, 4, 8, 16)
REQUESTS_PER_WORKER = int(os.environ.get("TOOL_REQUESTS_PER_WORKER", "4"))


TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_issue",
        "description": "Look up an issue by repository and number.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
            },
            "required": ["repo", "number"],
            "additionalProperties": False,
        },
    },
}


def call_once(i: int) -> tuple[bool, float, str]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Use tools when requested. Return only the tool call."},
            {"role": "user", "content": f"Look up issue {100 + i} in repo adam/local-llm."},
        ],
        "tools": [TOOL],
        "tool_choice": {"type": "function", "function": {"name": "lookup_issue"}},
        "temperature": 0,
        "max_tokens": 96,
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        return False, time.perf_counter() - start, repr(exc)

    elapsed = time.perf_counter() - start
    tool_calls = data["choices"][0]["message"].get("tool_calls") or []
    if not tool_calls:
        return False, elapsed, "missing tool_calls"
    function = tool_calls[0].get("function") or {}
    if function.get("name") != "lookup_issue":
        return False, elapsed, f"wrong function: {function.get('name')}"
    try:
        args = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        return False, elapsed, f"bad json args: {exc}"
    if args.get("repo") != "adam/local-llm" or not isinstance(args.get("number"), int):
        return False, elapsed, f"bad args: {args}"
    return True, elapsed, ""


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def main() -> int:
    results = []
    for concurrency in CONCURRENCIES:
        total = concurrency * REQUESTS_PER_WORKER
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            batch = list(pool.map(call_once, range(total)))
        duration = time.perf_counter() - start
        ok = [elapsed for passed, elapsed, _ in batch if passed]
        failures = [err for passed, _, err in batch if not passed]
        row = {
            "concurrency": concurrency,
            "requests": total,
            "passed": len(ok),
            "failed": len(failures),
            "duration_s": duration,
            "req_s": len(ok) / duration if duration else 0.0,
            "mean_latency_s": statistics.mean(ok) if ok else 0.0,
            "p95_latency_s": percentile(ok, 95),
            "first_failure": failures[0] if failures else "",
        }
        results.append(row)
        print(json.dumps(row, sort_keys=True))

    out = os.path.join(os.path.dirname(__file__), "artifacts", "tool_trajectory.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)
        f.write("\n")
    return 0 if all(row["failed"] == 0 for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
