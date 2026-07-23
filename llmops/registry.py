"""Model registry — loads models.toml into a dict of Model dataclasses."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Model:
    name: str
    file: str
    alias: str
    port: int
    min_vram_gb: float
    ctx_size: int
    kv_type: str
    description: str
    sampling: dict = field(default_factory=dict)
    # MoE expert offload to CPU RAM (frees VRAM for KV cache on A3B-style models).
    # n_cpu_moe > 0 offloads the first N layers' experts (--n-cpu-moe N); otherwise
    # cpu_moe offloads all experts (--cpu-moe). n_cpu_moe wins if both are set.
    cpu_moe: bool = False
    n_cpu_moe: int = 0
    # JSON string passed to llama.cpp --chat-template-kwargs (e.g. to default
    # thinking off: '{"enable_thinking": false}'). Clients can still override
    # per-request. Empty = leave the template's own defaults.
    chat_template_kwargs: str = ""


def load(registry_path: Path) -> dict[str, Model]:
    if not registry_path.exists():
        raise FileNotFoundError(f"Model registry not found: {registry_path}")
    with registry_path.open("rb") as f:
        data = tomllib.load(f)

    models = {}
    for name, spec in (data.get("models") or {}).items():
        models[name] = Model(
            name=name,
            file=spec["file"],
            alias=spec["alias"],
            port=int(spec["port"]),
            min_vram_gb=float(spec["min_vram_gb"]),
            ctx_size=int(spec["ctx_size"]),
            kv_type=spec.get("kv_type", "q8_0"),
            description=spec.get("description", ""),
            sampling=spec.get("sampling", {}),
            cpu_moe=bool(spec.get("cpu_moe", False)),
            n_cpu_moe=int(spec.get("n_cpu_moe", 0)),
            chat_template_kwargs=spec.get("chat_template_kwargs", ""),
        )
    return models
