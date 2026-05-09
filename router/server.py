"""local-agent-router — OpenAI-compatible facade for the two-tier stack.

Stdlib-only (no fastapi/uvicorn/httpx). ThreadingHTTPServer + urllib.

What this owns:
  - model alias → backend selection (exec :8080, smart :8081)
  - per-route system prompt injection
  - per-route sampling defaults
  - schema-constrained AgentDecision JSON for `exec` and `smart` (with one
    retry at temperature=0 if the response doesn't parse as JSON)
  - streaming passthrough (SSE) for IDE plugins
  - JSONL telemetry per request (route, model, tokens, latency, schema_valid)
  - optional shared-secret auth via ROUTER_API_KEY

What this does NOT do:
  - automatic mode-switching of containers (use-exec.sh / use-smart.sh)
  - cloud Codex escalation (codex_packet.py builds packets but no flow
    currently dispatches to a remote provider)

Run:
    cd ~/local-llmops
    ./scripts/run-router.sh
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router.prompts import CHAT_SYSTEM, EXEC_SYSTEM, SMART_SYSTEM  # noqa: E402
from router.schema import AGENT_DECISION_SCHEMA  # noqa: E402
from router.telemetry import emit as telemetry_emit  # noqa: E402

LOG = logging.getLogger("router")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EXEC_URL = os.environ.get("ROUTER_EXEC_URL", "http://127.0.0.1:8080/v1")
SMART_URL = os.environ.get("ROUTER_SMART_URL", "http://127.0.0.1:8081/v1")
API_KEY = os.environ.get("ROUTER_API_KEY")  # if set, require Bearer match

ROUTE_DEFAULTS: dict[str, dict[str, Any]] = {
    "exec": {
        "backend": EXEC_URL,
        "upstream_model": "local-qwen-exec",
        "system": EXEC_SYSTEM,
        "params": {"temperature": 0.2, "top_p": 0.8, "top_k": 20, "max_tokens": 1024},
        "thinking": False,
        "schema": AGENT_DECISION_SCHEMA,
    },
    "smart": {
        "backend": SMART_URL,
        "upstream_model": "local-qwen-smart",
        "system": SMART_SYSTEM,
        "params": {"temperature": 0.3, "top_p": 0.8, "top_k": 20, "max_tokens": 2048},
        "thinking": False,
        "schema": AGENT_DECISION_SCHEMA,
    },
    "smart_reasoning": {
        "backend": SMART_URL,
        "upstream_model": "local-qwen-smart",
        "system": SMART_SYSTEM,
        "params": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "max_tokens": 4096},
        "thinking": True,
        "schema": None,
    },
    "chat": {
        "backend": SMART_URL,
        "upstream_model": "local-qwen-smart",
        "system": CHAT_SYSTEM,
        "params": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "max_tokens": 2048},
        "thinking": False,
        "schema": None,
    },
}

MODEL_ALIASES: dict[str, str] = {
    "local-qwen-exec": "exec",
    "local-qwen-smart": "smart",
    "local-qwen-smart-reasoning": "smart_reasoning",
    "local-chat": "chat",
    "chat": "chat",
}


def pick_route(requested_model: str) -> str:
    return MODEL_ALIASES.get(requested_model, "exec")


def _http_post(url: str, body: dict, *, stream: bool = False, timeout: float = 600.0):
    """Return (status, headers, body_or_response). For stream=True the caller
    must read response.read() / iterate."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)  # caller handles


def _build_upstream_body(body: dict, cfg: dict, route: str) -> dict:
    messages = body.get("messages", [])
    if not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": cfg["system"]}] + messages

    upstream: dict[str, Any] = {
        "model": cfg["upstream_model"],
        "messages": messages,
        "chat_template_kwargs": {"enable_thinking": cfg["thinking"]},
    }
    upstream.update(cfg["params"])

    for k in ("temperature", "top_p", "top_k", "max_tokens", "stop", "tools", "tool_choice"):
        if k in body:
            upstream[k] = body[k]

    if cfg["schema"] is not None and body.get("response_format") is None and route in ("exec", "smart"):
        upstream["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "AgentDecision", "strict": True, "schema": cfg["schema"]},
        }
    elif body.get("response_format") is not None:
        upstream["response_format"] = body["response_format"]

    return upstream


class RouterHandler(BaseHTTPRequestHandler):
    server_version = "local-agent-router/0.1"

    # silence default access logging (we emit our own structured events)
    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("%s - %s", self.address_string(), fmt % args)

    # ----- helpers -----
    def _json_response(self, status: int, payload: dict, extra_headers: dict | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json_response(status, {"error": {"message": message, "type": "router_error"}})

    def _check_auth(self) -> bool:
        if not API_KEY:
            return True
        if self.headers.get("Authorization", "") == f"Bearer {API_KEY}":
            return True
        self._error(401, "unauthorized")
        return False

    # ----- routes -----
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._handle_health()
        elif path == "/v1/models":
            self._handle_models()
        else:
            self._error(404, f"unknown path {path}")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/v1/chat/completions":
            self._handle_chat()
        else:
            self._error(404, f"unknown path {path}")

    def _handle_health(self) -> None:
        out: dict[str, Any] = {"router": "ok", "tiers": {}}
        for name, base in (("exec", EXEC_URL), ("smart", SMART_URL)):
            health_url = base[:-3] + "/health" if base.endswith("/v1") else base.rstrip("/") + "/health"
            try:
                with urllib.request.urlopen(health_url, timeout=2) as r:
                    out["tiers"][name] = "ok" if r.status == 200 else f"http {r.status}"
            except Exception as e:
                out["tiers"][name] = f"down ({type(e).__name__})"
        self._json_response(200, out)

    def _handle_models(self) -> None:
        self._json_response(200, {
            "object": "list",
            "data": [{"id": k, "object": "model", "owned_by": "local-llmops"} for k in MODEL_ALIASES],
        })

    def _handle_chat(self) -> None:
        if not self._check_auth():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw)
        except (ValueError, json.JSONDecodeError) as e:
            self._error(400, f"bad request body: {e}")
            return

        requested = body.get("model", "local-qwen-exec")
        route = pick_route(requested)
        cfg = ROUTE_DEFAULTS[route]
        upstream = _build_upstream_body(body, cfg, route)
        log_base: dict[str, Any] = {
            "route": route,
            "model": cfg["upstream_model"],
            "client_model": requested,
            "ip": self.client_address[0],
        }

        if body.get("stream"):
            upstream["stream"] = True
            self._proxy_stream(cfg["backend"], upstream, log_base)
        else:
            self._proxy_blocking(cfg, upstream, log_base, route)

    def _proxy_blocking(self, cfg: dict, upstream: dict, log_base: dict, route: str) -> None:
        started = time.perf_counter()
        schema_valid: bool | None = None
        data: dict = {}
        attempts = 2 if cfg["schema"] is not None else 1
        for attempt in range(attempts):
            try:
                data_bytes = json.dumps(upstream).encode("utf-8")
                req = urllib.request.Request(
                    f"{cfg['backend']}/chat/completions",
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=600) as r:
                    raw = r.read()
                data = json.loads(raw)
            except urllib.error.HTTPError as e:
                self._error(e.code, e.read().decode("utf-8", errors="replace"))
                return
            except Exception as e:
                self._error(502, f"upstream {type(e).__name__}: {e}")
                return

            if cfg["schema"] is None:
                break
            try:
                json.loads(data["choices"][0]["message"]["content"])
                schema_valid = True
                break
            except (KeyError, IndexError, json.JSONDecodeError):
                schema_valid = False
                if attempt == attempts - 1:
                    break
                upstream["temperature"] = 0.0  # tighten and retry once

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        usage = (data.get("usage") or {})
        telemetry_emit({
            **log_base,
            "latency_ms": round(elapsed_ms, 1),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "stream": False,
            "schema_valid": schema_valid,
        })
        self._json_response(200, data)

    def _proxy_stream(self, backend: str, upstream: dict, log_base: dict) -> None:
        started = time.perf_counter()
        last_usage: dict = {}
        try:
            data_bytes = json.dumps(upstream).encode("utf-8")
            req = urllib.request.Request(
                f"{backend}/chat/completions",
                data=data_bytes,
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            )
            r = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            self._error(e.code, e.read().decode("utf-8", errors="replace"))
            return
        except Exception as e:
            self._error(502, f"upstream {type(e).__name__}: {e}")
            return

        # Begin SSE response to client
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        # Relay byte-by-line so we can sniff usage in the final chunk
        buf = b""
        try:
            while True:
                chunk = r.read(4096)
                if not chunk:
                    break
                buf += chunk
                # split on lines but keep partials
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    out = line + b"\n"
                    self.wfile.write(out)
                    self.wfile.flush()
                    text = line.decode("utf-8", errors="ignore").strip()
                    if text.startswith("data:"):
                        payload = text[5:].strip()
                        if payload and payload != "[DONE]":
                            try:
                                evt = json.loads(payload)
                                if isinstance(evt, dict) and isinstance(evt.get("usage"), dict):
                                    last_usage = evt["usage"]
                            except json.JSONDecodeError:
                                pass
            if buf:
                self.wfile.write(buf)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        telemetry_emit({
            **log_base,
            "latency_ms": round(elapsed_ms, 1),
            "prompt_tokens": last_usage.get("prompt_tokens"),
            "completion_tokens": last_usage.get("completion_tokens"),
            "total_tokens": last_usage.get("total_tokens"),
            "stream": True,
            "schema_valid": None,
        })


def main() -> int:
    host = os.environ.get("ROUTER_HOST", "127.0.0.1")
    port = int(os.environ.get("ROUTER_PORT", "8090"))
    LOG.info(
        "starting local-agent-router on %s:%s  (exec=%s  smart=%s  api_key=%s)",
        host, port, EXEC_URL, SMART_URL, "set" if API_KEY else "none",
    )
    server = ThreadingHTTPServer((host, port), RouterHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
