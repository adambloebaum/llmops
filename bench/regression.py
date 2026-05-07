#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request


BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://100.114.124.62:8000/v1").rstrip("/")
MODEL = os.environ.get("MODEL", "qwen2.5-coder-7b")
FAILURES = []


def chat(messages, **extra):
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": extra.pop("temperature", 0),
        "max_tokens": extra.pop("max_tokens", 512),
    }
    payload.update(extra)
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def assert_true(name, condition, detail):
    if condition:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: {detail}")
        FAILURES.append(name)


def main():
    tool_msg = chat(
        [{"role": "user", "content": "Use the tool to look up order A123."}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup_order",
                    "description": "Look up an order.",
                    "parameters": {
                        "type": "object",
                        "properties": {"order_id": {"type": "string"}},
                        "required": ["order_id"],
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "lookup_order"}},
    )
    assert_true("bfcl_style_tool_call", bool(tool_msg.get("tool_calls")), tool_msg)

    json_msg = chat(
        [{"role": "user", "content": "Return JSON with keys answer and confidence. answer must be 42."}],
        response_format={"type": "json_object"},
        max_tokens=128,
    )
    parsed = json.loads(json_msg.get("content") or "{}")
    assert_true("json_mode", parsed.get("answer") == 42, parsed)

    edit_msg = chat(
        [
            {
                "role": "user",
                "content": "Given file app.py containing `print('helo')`, provide a unified diff fixing the typo to hello.",
            }
        ],
        max_tokens=256,
    )
    content = edit_msg.get("content") or ""
    assert_true("aider_style_diff", "---" in content and "+++" in content and "hello" in content, content[:400])

    math_msg = chat(
        [{"role": "user", "content": "A train has 3 cars with 12 seats each. 5 seats are broken. How many usable seats? Respond with just the number."}],
        max_tokens=128,
    )
    assert_true("gsm8k_tiny", "31" in (math_msg.get("content") or ""), math_msg)

    needle = "NEEDLE_VALUE_7f3a9c"
    filler = " ".join([f"token{i}" for i in range(2500)])
    recall_msg = chat(
        [{"role": "user", "content": f"{filler}\nRemember this exact code: {needle}\n{filler}\nWhat exact code did I ask you to remember?"}],
        max_tokens=32,
    )
    assert_true("long_context_recall", needle in (recall_msg.get("content") or ""), recall_msg)

    if FAILURES:
        raise SystemExit(f"failed checks: {', '.join(FAILURES)}")


if __name__ == "__main__":
    main()
