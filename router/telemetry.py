"""Append-only JSONL request telemetry."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def log_path() -> Path:
    p = os.environ.get("ROUTER_LOG_PATH")
    if p:
        return Path(p)
    return Path(__file__).resolve().parent / "logs" / "router.jsonl"


def emit(record: dict[str, Any]) -> None:
    """Append one event as a single JSON line. Atomic per write on POSIX."""
    record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with _LOCK:
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
