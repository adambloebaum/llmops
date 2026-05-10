"""Host detection — GPUs, Tailscale IP, and per-host config overrides."""

from __future__ import annotations

import os
import socket
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GPU:
    index: int
    name: str
    total_mib: int
    free_mib: int

    @property
    def total_gib(self) -> float:
        return self.total_mib / 1024

    @property
    def free_gib(self) -> float:
        return self.free_mib / 1024


@dataclass
class Host:
    hostname: str
    gguf_dir: Path
    bind_ip: str
    autostart: str | None
    image: str
    config_path: Path | None


def hostname() -> str:
    return socket.gethostname().split(".")[0]


def detect_gpus() -> list[GPU]:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            gpus.append(
                GPU(
                    index=int(parts[0]),
                    name=parts[1],
                    total_mib=int(parts[2]),
                    free_mib=int(parts[3]),
                )
            )
        except ValueError:
            continue
    return gpus


def detect_tailscale_ip() -> str | None:
    try:
        out = subprocess.check_output(
            ["tailscale", "ip", "-4"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        ip = out.strip().splitlines()[0].strip() if out.strip() else ""
        return ip or None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def load(repo_root: Path) -> Host:
    name = hostname()
    config_path = repo_root / "hosts" / f"{name}.toml"
    data: dict = {}
    if config_path.exists():
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    else:
        config_path = None

    gguf_dir = Path(
        os.path.expanduser(data.get("gguf_dir") or "~/llm-models/gguf")
    )

    bind_setting = data.get("bind", "tailscale")
    if bind_setting == "tailscale":
        bind_ip = detect_tailscale_ip() or "127.0.0.1"
    elif bind_setting == "localhost":
        bind_ip = "127.0.0.1"
    else:
        bind_ip = bind_setting

    return Host(
        hostname=name,
        gguf_dir=gguf_dir,
        bind_ip=bind_ip,
        autostart=data.get("autostart") or None,
        image=data.get("image") or "ghcr.io/ggml-org/llama.cpp:server-cuda",
        config_path=config_path,
    )
