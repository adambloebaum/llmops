#!/usr/bin/env python3
"""Aggregate router/logs/router.jsonl into a daily spend report.

Reports:
  - requests / tokens by route per day
  - actual local cost (≈ $0)
  - inferred cost if every request had gone to a cloud baseline
  - inferred savings = baseline - actual

Usage:
    python3 bench/spend_report.py                       # all-time summary
    python3 bench/spend_report.py --since 2026-05-01    # since date
    python3 bench/spend_report.py --baseline gpt-5-codex
    python3 bench/spend_report.py --baseline claude-opus-4-7
    python3 bench/spend_report.py --by day              # default: all-time
    python3 bench/spend_report.py --json                # raw JSON instead of text

The router writes one JSON object per request to router/logs/router.jsonl.
Each line includes prompt_tokens, completion_tokens, route, model, ts.
This script does no live API calls — it operates only on the local log.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOG = REPO / "router" / "logs" / "router.jsonl"
RATES_PATH = REPO / "router" / "rates.json"


def load_rates() -> tuple[dict[str, dict[str, float]], str]:
    cfg = json.loads(RATES_PATH.read_text())
    return cfg.get("rates", {}), cfg.get("default_cloud_baseline", "gpt-5-codex")


def cost_usd(prompt: int, completion: int, rate: dict[str, float]) -> float:
    return (prompt / 1_000_000.0) * rate.get("input", 0.0) + \
           (completion / 1_000_000.0) * rate.get("output", 0.0)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=str, default=str(DEFAULT_LOG))
    ap.add_argument("--since", type=str, default=None, help="YYYY-MM-DD lower bound (inclusive)")
    ap.add_argument("--until", type=str, default=None, help="YYYY-MM-DD upper bound (exclusive)")
    ap.add_argument("--baseline", type=str, default=None, help="cloud model id from rates.json (default: rates.json default_cloud_baseline)")
    ap.add_argument("--by", choices=["all", "day", "route"], default="all")
    ap.add_argument("--json", action="store_true", dest="as_json")
    return ap.parse_args()


def parse_iso_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc) if "T" in s else \
           datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def iter_records(path: Path, since: datetime | None, until: datetime | None):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = rec.get("ts")
        if ts and (since or until):
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if since and t < since:
                continue
            if until and t >= until:
                continue
        yield rec


def main() -> int:
    args = parse_args()
    rates, default_baseline = load_rates()
    baseline = args.baseline or default_baseline
    if baseline not in rates:
        print(f"ERROR: baseline {baseline!r} not in rates.json (have: {sorted(rates)})", file=sys.stderr)
        return 2

    since = parse_iso_date(args.since) if args.since else None
    until = parse_iso_date(args.until) if args.until else None

    # Bucket key fn
    def bucket(rec: dict) -> str:
        if args.by == "day":
            return rec.get("ts", "")[:10] or "unknown"
        if args.by == "route":
            return rec.get("route", "unknown")
        return "all"

    agg: dict[str, dict] = defaultdict(lambda: {
        "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "actual_usd": 0.0, "baseline_usd": 0.0,
        "schema_fail": 0, "by_route": defaultdict(int),
    })

    seen = 0
    for rec in iter_records(Path(args.log), since, until):
        seen += 1
        key = bucket(rec)
        b = agg[key]
        p = int(rec.get("prompt_tokens") or 0)
        c = int(rec.get("completion_tokens") or 0)
        local_model = rec.get("model", "")
        b["requests"] += 1
        b["prompt_tokens"] += p
        b["completion_tokens"] += c
        b["actual_usd"] += cost_usd(p, c, rates.get(local_model, {"input": 0.0, "output": 0.0}))
        b["baseline_usd"] += cost_usd(p, c, rates[baseline])
        b["by_route"][rec.get("route", "?")] += 1
        if rec.get("schema_valid") is False:
            b["schema_fail"] += 1

    if not seen:
        print(f"no records in {args.log}", file=sys.stderr)
        return 0

    # Render
    if args.as_json:
        out = {
            "baseline_model": baseline,
            "buckets": {
                k: {
                    **{kk: vv for kk, vv in v.items() if kk != "by_route"},
                    "by_route": dict(v["by_route"]),
                    "savings_usd": round(v["baseline_usd"] - v["actual_usd"], 4),
                }
                for k, v in sorted(agg.items())
            },
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"# spend report  baseline={baseline}  records={seen}")
    print(f"# log: {args.log}")
    print()
    header = f"{'bucket':<12} {'reqs':>6} {'prompt_tok':>11} {'compl_tok':>11} {'actual$':>9} {'baseline$':>11} {'saved$':>9}  routes"
    print(header)
    print("-" * len(header))
    total_actual = 0.0
    total_baseline = 0.0
    for k, v in sorted(agg.items()):
        savings = v["baseline_usd"] - v["actual_usd"]
        total_actual += v["actual_usd"]
        total_baseline += v["baseline_usd"]
        routes = ", ".join(f"{r}={n}" for r, n in sorted(v["by_route"].items()))
        print(f"{k:<12} {v['requests']:>6} {v['prompt_tokens']:>11} {v['completion_tokens']:>11} "
              f"{v['actual_usd']:>9.4f} {v['baseline_usd']:>11.4f} {savings:>9.4f}  {routes}")
    if len(agg) > 1:
        print("-" * len(header))
        print(f"{'TOTAL':<12} {'':>6} {'':>11} {'':>11} "
              f"{total_actual:>9.4f} {total_baseline:>11.4f} {total_baseline - total_actual:>9.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
