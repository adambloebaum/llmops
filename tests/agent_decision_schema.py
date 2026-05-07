"""Schema-constrained AgentDecision regression for both tiers.

Hits each tier 5 times with a JSON-schema-constrained chat completion and
asserts every response parses, validates against the schema, and uses an
allowed enum value for `kind`/`tool_name`/`risk`.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import alias, base_url
from router.schema import AGENT_DECISION_SCHEMA

PROMPT = (
    "The last test run failed with: AssertionError in tests/test_parser.py::test_empty_input. "
    "What should the harness do next?"
)


def one(base: str, model: str) -> dict:
    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": 512,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "AgentDecision",
                "strict": True,
                "schema": AGENT_DECISION_SCHEMA,
            },
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a local execution-planning model. Return only valid JSON "
                    "matching the provided schema. Prefer inspection before mutation. "
                    "Escalate when the task requires broad multi-file reasoning."
                ),
            },
            {"role": "user", "content": PROMPT},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def validate(d: dict) -> list[str]:
    """Lightweight schema check (avoids requiring jsonschema package)."""
    errs: list[str] = []
    for k in AGENT_DECISION_SCHEMA["required"]:
        if k not in d:
            errs.append(f"missing key: {k}")
    if "kind" in d and d["kind"] not in AGENT_DECISION_SCHEMA["properties"]["kind"]["enum"]:
        errs.append(f"bad kind: {d['kind']}")
    if "tool_name" in d and d["tool_name"] not in AGENT_DECISION_SCHEMA["properties"]["tool_name"]["enum"]:
        errs.append(f"bad tool_name: {d['tool_name']}")
    if "risk" in d and d["risk"] not in AGENT_DECISION_SCHEMA["properties"]["risk"]["enum"]:
        errs.append(f"bad risk: {d['risk']}")
    if "confidence" in d:
        try:
            c = float(d["confidence"])
            if not (0.0 <= c <= 1.0):
                errs.append(f"confidence out of range: {c}")
        except (TypeError, ValueError):
            errs.append("confidence not numeric")
    if "arguments" in d and not isinstance(d["arguments"], dict):
        errs.append("arguments not object")
    return errs


def run_tier(tier: str, n: int = 5) -> int:
    base = base_url(tier)
    model = alias(tier)
    print(f"== {tier} ({base}, model={model}) ==")
    fails = 0
    for i in range(n):
        try:
            obj = one(base, model)
            errs = validate(obj)
            if errs:
                fails += 1
                print(f"  [{i+1}/{n}] FAIL: {errs}; obj={obj}")
            else:
                print(f"  [{i+1}/{n}] ok: kind={obj['kind']} tool={obj['tool_name']} risk={obj['risk']} conf={obj['confidence']}")
        except Exception as e:
            fails += 1
            print(f"  [{i+1}/{n}] ERROR: {e}")
    print(f"  {tier} fails: {fails}/{n}")
    return fails


def main() -> int:
    total = 0
    for tier in ("exec", "smart"):
        try:
            total += run_tier(tier)
        except Exception as e:
            print(f"{tier}: tier unavailable — {e}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
