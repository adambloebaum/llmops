"""Health + basic completion smoke for the smart tier (Qwen3.5-9B)."""

from __future__ import annotations

import json
import sys
import urllib.request

from _common import alias, base_url


def main() -> int:
    base = base_url("smart")
    expected = alias("smart")

    with urllib.request.urlopen(f"{base}/health", timeout=5) as r:
        assert r.status == 200, f"/health returned {r.status}"
        print(f"[ok] {base}/health 200")

    with urllib.request.urlopen(f"{base}/v1/models", timeout=5) as r:
        data = json.loads(r.read())
    ids = [m["id"] for m in data.get("data", [])]
    assert expected in ids, f"alias {expected} not in /v1/models: {ids}"
    print(f"[ok] /v1/models lists {expected}")

    body = json.dumps({
        "model": expected,
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": 64,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": "You are a terse code assistant. Answer in one short sentence."},
            {"role": "user", "content": "What does Python's `enumerate` return?"},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    msg = data["choices"][0]["message"]["content"].strip()
    print(f"[ok] chat completion: {msg[:200]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
