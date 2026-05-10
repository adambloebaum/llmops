"""Shared helpers for endpoint smoke tests.

Endpoints come from the llmops registry + host detection. Pass a model
name (e.g. "qwen3.5-4b") to base_url() and alias().
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from llmops import host as _host  # noqa: E402
from llmops import registry as _registry  # noqa: E402

_MODELS = _registry.load(_REPO_ROOT / "models.toml")
_HOST = _host.load(_REPO_ROOT)


def base_url(model_name: str) -> str:
    if model_name not in _MODELS:
        raise ValueError(f"unknown model: {model_name}")
    m = _MODELS[model_name]
    bind = os.environ.get("LLMOPS_BIND", _HOST.bind_ip)
    return f"http://{bind}:{m.port}"


def alias(model_name: str) -> str:
    if model_name not in _MODELS:
        raise ValueError(f"unknown model: {model_name}")
    return _MODELS[model_name].alias
