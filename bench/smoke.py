#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://100.114.124.62:8000/v1").rstrip("/")
MODEL = os.environ.get("MODEL", "qwen2.5-coder-7b")


def request(path, payload=None, stream=False, timeout=120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer local",
        },
        method="GET" if payload is None else "POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def chat(payload):
    started = time.time()
    with request("/chat/completions", payload) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body, time.time() - started


def main():
    print(f"base_url={BASE_URL}")
    with request("/models", timeout=10) as resp:
        models = json.loads(resp.read().decode("utf-8"))
    print("models=", [m.get("id") for m in models.get("data", [])])

    body, elapsed = chat(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
            "temperature": 0,
            "max_tokens": 8,
        }
    )
    content = body["choices"][0]["message"].get("content", "")
    print(f"basic_chat elapsed={elapsed:.3f}s content={content!r}")

    tool_payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "What is the weather in Seattle? Use the tool."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a city.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        "temperature": 0,
        "max_tokens": 128,
    }
    body, elapsed = chat(tool_payload)
    msg = body["choices"][0]["message"]
    print(f"tool_call elapsed={elapsed:.3f}s tool_calls={json.dumps(msg.get('tool_calls'), sort_keys=True)}")
    if not msg.get("tool_calls"):
        raise SystemExit("missing tool_calls")

    stream_req = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Count from 1 to 5, comma separated."}],
        "temperature": 0,
        "max_tokens": 32,
        "stream": True,
    }
    with request("/chat/completions", stream_req, timeout=120) as resp:
        chunks = 0
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("data: "):
                chunks += 1
            if line == "data: [DONE]":
                break
    print(f"stream_chunks={chunks}")
    if chunks < 2:
        raise SystemExit("streaming produced too few chunks")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        raise
