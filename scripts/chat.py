#!/usr/bin/env python3
"""Tiny CLI chat against either tier. Streams tokens.

Usage:
    python3 scripts/chat.py            # exec tier
    python3 scripts/chat.py --smart    # smart tier
    python3 scripts/chat.py --think    # smart with enable_thinking=true
    python3 scripts/chat.py --once "tell me a short joke"

Reads LLM_BIND_HOST and EXEC_PORT/SMART_PORT from .env.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
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


def stream_chat(base: str, model: str, messages: list[dict], thinking: bool, max_tokens: int) -> str:
    body = json.dumps({
        "model": model,
        "stream": True,
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": thinking},
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    out: list[str] = []
    with urllib.request.urlopen(req, timeout=600) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                evt = json.loads(payload)
            except json.JSONDecodeError:
                continue
            try:
                delta = evt["choices"][0]["delta"].get("content", "")
            except (KeyError, IndexError):
                delta = ""
            if delta:
                sys.stdout.write(delta)
                sys.stdout.flush()
                out.append(delta)
    sys.stdout.write("\n")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smart", action="store_true", help="use smart tier (9B) instead of exec (4B)")
    ap.add_argument("--think", action="store_true", help="enable_thinking=true (smart only)")
    ap.add_argument("--once", metavar="MSG", help="send one prompt and exit")
    ap.add_argument("--max-tokens", type=int, default=1024)
    args = ap.parse_args()

    env = {**load_env(), **os.environ}
    host = env.get("LLM_BIND_HOST", "127.0.0.1")
    if args.smart:
        port = env.get("SMART_PORT", "8081")
        model = env.get("SMART_ALIAS", "local-qwen-smart")
    else:
        port = env.get("EXEC_PORT", "8080")
        model = env.get("EXEC_ALIAS", "local-qwen-exec")
    base = f"http://{host}:{port}"

    sys_msg = {
        "role": "system",
        "content": "You are a concise local coding assistant. Keep replies tight.",
    }
    history: list[dict] = [sys_msg]

    if args.once:
        history.append({"role": "user", "content": args.once})
        stream_chat(base, model, history, args.think, args.max_tokens)
        return 0

    print(f"chat: {model} @ {base}  (Ctrl-D / 'exit' to quit)")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user:
            continue
        if user in ("exit", "quit", ":q"):
            return 0
        history.append({"role": "user", "content": user})
        sys.stdout.write("ai > ")
        sys.stdout.flush()
        reply = stream_chat(base, model, history, args.think, args.max_tokens)
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    sys.exit(main())
