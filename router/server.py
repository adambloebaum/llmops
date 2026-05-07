"""Minimal local-agent-router scaffold.

OpenAI-compatible facade on :8090 that:
  - selects a backend (exec :8080 or smart :8081) by `model` field
  - injects the right system prompt
  - applies route-specific sampling defaults
  - enforces AgentDecision schema for `route=exec|smart` requests
  - retries once on invalid JSON
  - logs token usage / latency / route / validation status

This is a scaffold, not a fully wired router. Use it as a forwarder during
phase 1; layer escalation rules and Codex-packet generation in phase 2.

Run with:
    cd ~/local-llmops
    uv venv router/.venv && source router/.venv/bin/activate
    uv pip install fastapi uvicorn httpx pydantic
    python -m router.server
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request

from .prompts import CHAT_SYSTEM, EXEC_SYSTEM, SMART_SYSTEM
from .schema import AGENT_DECISION_SCHEMA

LOG = logging.getLogger("router")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EXEC_URL = os.environ.get("ROUTER_EXEC_URL", "http://127.0.0.1:8080/v1")
SMART_URL = os.environ.get("ROUTER_SMART_URL", "http://127.0.0.1:8081/v1")

ROUTE_DEFAULTS: dict[str, dict[str, Any]] = {
    "exec": {
        "backend": EXEC_URL,
        "model": "local-qwen-exec",
        "system": EXEC_SYSTEM,
        "params": {"temperature": 0.2, "top_p": 0.8, "top_k": 20, "max_tokens": 1024},
        "thinking": False,
        "schema": AGENT_DECISION_SCHEMA,
    },
    "smart": {
        "backend": SMART_URL,
        "model": "local-qwen-smart",
        "system": SMART_SYSTEM,
        "params": {"temperature": 0.3, "top_p": 0.8, "top_k": 20, "max_tokens": 2048},
        "thinking": False,
        "schema": AGENT_DECISION_SCHEMA,
    },
    "smart_reasoning": {
        "backend": SMART_URL,
        "model": "local-qwen-smart",
        "system": SMART_SYSTEM,
        "params": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "max_tokens": 4096},
        "thinking": True,
        "schema": None,
    },
    "chat": {
        "backend": SMART_URL,
        "model": "local-qwen-smart",
        "system": CHAT_SYSTEM,
        "params": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "max_tokens": 2048},
        "thinking": False,
        "schema": None,
    },
}

app = FastAPI(title="local-agent-router")


def pick_route(requested_model: str) -> str:
    if requested_model == "local-qwen-exec":
        return "exec"
    if requested_model == "local-qwen-smart":
        return "smart"
    if requested_model == "local-qwen-smart-reasoning":
        return "smart_reasoning"
    if requested_model in ("chat", "local-chat"):
        return "chat"
    return "exec"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "local-qwen-exec", "object": "model", "owned_by": "local-llmops"},
            {"id": "local-qwen-smart", "object": "model", "owned_by": "local-llmops"},
            {"id": "local-qwen-smart-reasoning", "object": "model", "owned_by": "local-llmops"},
            {"id": "local-chat", "object": "model", "owned_by": "local-llmops"},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: Request) -> dict[str, Any]:
    body = await req.json()
    requested = body.get("model", "local-qwen-exec")
    route = pick_route(requested)
    cfg = ROUTE_DEFAULTS[route]

    messages = body.get("messages", [])
    if not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": cfg["system"]}] + messages

    upstream: dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "chat_template_kwargs": {"enable_thinking": cfg["thinking"]},
    }
    upstream.update(cfg["params"])
    for passthrough in ("stream", "tools", "tool_choice", "stop"):
        if passthrough in body:
            upstream[passthrough] = body[passthrough]

    if cfg["schema"] is not None and body.get("response_format") is None and route in ("exec", "smart"):
        upstream["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "AgentDecision",
                "strict": True,
                "schema": cfg["schema"],
            },
        }
    elif body.get("response_format") is not None:
        upstream["response_format"] = body["response_format"]

    started = time.perf_counter()
    valid_json = None
    async with httpx.AsyncClient(timeout=600.0) as client:
        for attempt in range(2):
            r = await client.post(f"{cfg['backend']}/chat/completions", json=upstream)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            data = r.json()
            if cfg["schema"] is None:
                break
            try:
                content = data["choices"][0]["message"]["content"]
                json.loads(content)
                valid_json = True
                break
            except (KeyError, json.JSONDecodeError):
                valid_json = False
                if attempt == 1:
                    break
                upstream["temperature"] = 0.0
        else:
            raise HTTPException(status_code=502, detail="invalid JSON after retry")
    elapsed = (time.perf_counter() - started) * 1000.0

    usage = data.get("usage", {})
    LOG.info(
        "route=%s model=%s prompt=%s completion=%s latency_ms=%.0f schema_valid=%s",
        route,
        cfg["model"],
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        elapsed,
        valid_json,
    )

    return data


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("ROUTER_PORT", "8090"))
    uvicorn.run(app, host=os.environ.get("ROUTER_HOST", "127.0.0.1"), port=port)
