#!/usr/bin/env python3
"""End-to-end OpenAI-compat benchmark for the llama.cpp tiers.

Sends N non-streaming chat completions at concurrency C, measures wall latency,
extracts prompt/completion tokens from the `usage` object, and reports:

    requests:    N (success) / N (total)
    p50 / p95 latency, mean
    decode tok/s (per-request mean)
    aggregate decode tok/s (total completion tokens / total wall)
    aggregate prompt tok/s (total prompt tokens / total wall)

Usage:
    python3 bench/llamacpp_bench.py --tier exec  --concurrency 1,4,8 --requests 24
    python3 bench/llamacpp_bench.py --tier smart --concurrency 1,4    --requests 16

Output is JSON-per-scenario plus a human summary on stderr. Stdlib only
(no httpx / no vLLM bench dependency).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_env() -> dict[str, str]:
    p = Path(__file__).resolve().parent.parent / ".env"
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def base_for(tier: str) -> tuple[str, str]:
    env = {**load_env(), **os.environ}
    host = env.get("LLM_BIND_HOST", "127.0.0.1")
    if tier == "exec":
        return f"http://{host}:{env.get('EXEC_PORT', '8080')}", env.get("EXEC_ALIAS", "local-qwen-exec")
    if tier == "smart":
        return f"http://{host}:{env.get('SMART_PORT', '8081')}", env.get("SMART_ALIAS", "local-qwen-smart")
    raise ValueError(tier)


PROMPT = (
    "Summarize the following commit message in one sentence, then list any TODOs you see:\n\n"
    "feat(parser): add streaming JSON support and remove deprecated wrap()\n"
    "- adds new `stream_parse(stream)` API\n"
    "- removes `parse_chunk()` (deprecated 6mo)\n"
    "- TODO: backport tests for the legacy adapter\n"
)


def one_request(base: str, model: str, max_tokens: int) -> dict:
    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": "You are a terse code assistant."},
            {"role": "user", "content": PROMPT},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {"ok": False, "error": str(e), "elapsed_ms": (time.perf_counter() - started) * 1000.0}
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    usage = data.get("usage", {}) or {}
    return {
        "ok": True,
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


def run_scenario(base: str, model: str, requests: int, concurrency: int, max_tokens: int) -> dict:
    started = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one_request, base, model, max_tokens) for _ in range(requests)]
        results = [f.result() for f in cf.as_completed(futures)]
    wall_s = time.perf_counter() - started

    ok = [r for r in results if r["ok"]]
    fail = len(results) - len(ok)
    if not ok:
        return {
            "concurrency": concurrency, "requests": requests, "fail": fail,
            "wall_s": wall_s,
        }

    elapsed = sorted(r["elapsed_ms"] for r in ok)
    per_req_decode_tps = [
        r["completion_tokens"] / (r["elapsed_ms"] / 1000.0)
        for r in ok if r["completion_tokens"] > 0
    ]
    total_completion = sum(r["completion_tokens"] for r in ok)
    total_prompt = sum(r["prompt_tokens"] for r in ok)
    return {
        "concurrency": concurrency,
        "requests": requests,
        "ok": len(ok),
        "fail": fail,
        "wall_s": round(wall_s, 3),
        "latency_ms": {
            "mean": round(statistics.mean(elapsed), 1),
            "p50": round(statistics.median(elapsed), 1),
            "p95": round(elapsed[int(len(elapsed) * 0.95) - 1] if len(elapsed) >= 20 else elapsed[-1], 1),
            "min": round(elapsed[0], 1),
            "max": round(elapsed[-1], 1),
        },
        "per_req_decode_tps_mean": round(statistics.mean(per_req_decode_tps), 1) if per_req_decode_tps else 0,
        "agg_decode_tps": round(total_completion / wall_s, 1),
        "agg_prompt_tps": round(total_prompt / wall_s, 1),
        "total_completion_tokens": total_completion,
        "total_prompt_tokens": total_prompt,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["exec", "smart"], default="exec")
    ap.add_argument("--concurrency", default="1,4,8", help="comma-separated levels, e.g. 1,4,8,16")
    ap.add_argument("--requests", type=int, default=16, help="requests per scenario")
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--out", type=str, default="", help="optional JSON path to write all scenarios")
    args = ap.parse_args()

    base, model = base_for(args.tier)
    print(f"# tier={args.tier}  base={base}  model={model}", file=sys.stderr)
    print(f"# requests/scenario={args.requests}  max_tokens={args.max_tokens}", file=sys.stderr)

    scenarios = []
    for c in (int(x) for x in args.concurrency.split(",")):
        print(f"\n## concurrency={c}", file=sys.stderr)
        s = run_scenario(base, model, args.requests, c, args.max_tokens)
        scenarios.append(s)
        if "latency_ms" in s:
            print(
                f"  ok={s['ok']}/{s['requests']}  wall={s['wall_s']}s  "
                f"lat p50={s['latency_ms']['p50']}ms p95={s['latency_ms']['p95']}ms  "
                f"per-req tps={s['per_req_decode_tps_mean']}  "
                f"agg decode={s['agg_decode_tps']} tok/s  agg prompt={s['agg_prompt_tps']} tok/s",
                file=sys.stderr,
            )
        else:
            print(f"  all failed: {s}", file=sys.stderr)
    if args.out:
        Path(args.out).write_text(json.dumps({"tier": args.tier, "model": model, "scenarios": scenarios}, indent=2))
        print(f"\nwrote {args.out}", file=sys.stderr)
    print(json.dumps(scenarios, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
