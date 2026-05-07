"""Health + basic completion smoke for the exec tier (Qwen3.5-4B)."""

from __future__ import annotations

import json
import sys
import urllib.request

from _common import alias, base_url


def main() -> int:
    base = base_url("exec")
    expected = alias("exec")

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
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": 16,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": "Reply with exactly the single token: pong"},
            {"role": "user", "content": "ping"},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    msg = data["choices"][0]["message"]["content"].strip().lower()
    print(f"[ok] chat completion: {msg!r}")
    if "pong" not in msg:
        print(f"[warn] expected 'pong' substring, got {msg!r}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
