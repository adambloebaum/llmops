"""Shared helpers for endpoint smoke tests."""

from __future__ import annotations

import os
import re
from pathlib import Path


def load_env(path: Path | None = None) -> dict[str, str]:
    p = path or (Path(__file__).resolve().parent.parent / ".env")
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


def base_url(tier: str) -> str:
    env = {**load_env(), **os.environ}
    host = env.get("LLM_BIND_HOST", "127.0.0.1")
    if tier == "exec":
        port = env.get("EXEC_PORT", "8080")
    elif tier == "smart":
        port = env.get("SMART_PORT", "8081")
    else:
        raise ValueError(tier)
    return f"http://{host}:{port}"


def alias(tier: str) -> str:
    env = {**load_env(), **os.environ}
    return env.get("EXEC_ALIAS" if tier == "exec" else "SMART_ALIAS", f"local-qwen-{tier}")
