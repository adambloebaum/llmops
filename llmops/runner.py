"""Docker runner — starts/stops/inspects llama.cpp containers tagged with labels."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .host import Host
from .registry import Model

LABEL_NS = "llmops"
LABEL_MODEL = f"{LABEL_NS}.model"
LABEL_GPU = f"{LABEL_NS}.gpu"
LABEL_PORT = f"{LABEL_NS}.port"
LABEL_DRAFT = f"{LABEL_NS}.draft"


def container_name(model: Model, gpu_index: int) -> str:
    return f"llmops-{model.name}-gpu{gpu_index}"


@dataclass
class RunningInstance:
    container: str
    model: str
    gpu: int
    port: int
    state: str
    health: str
    draft: str | None = None


def _docker(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        capture_output=capture,
    )


def list_instances() -> list[RunningInstance]:
    proc = _docker(
        "ps",
        "-a",
        "--filter",
        f"label={LABEL_NS}.model",
        "--format",
        "{{.Names}}",
        check=False,
    )
    names = [n for n in proc.stdout.strip().splitlines() if n]
    if not names:
        return []
    inspect = _docker("inspect", *names, check=False).stdout
    try:
        records = json.loads(inspect) if inspect.strip() else []
    except json.JSONDecodeError:
        return []

    out = []
    for rec in records:
        labels = rec.get("Config", {}).get("Labels") or {}
        state = rec.get("State", {})
        out.append(
            RunningInstance(
                container=rec.get("Name", "").lstrip("/"),
                model=labels.get(LABEL_MODEL, "?"),
                gpu=int(labels.get(LABEL_GPU, -1)),
                port=int(labels.get(LABEL_PORT, 0)),
                state=state.get("Status", "?"),
                health=(state.get("Health") or {}).get("Status", "n/a"),
                draft=labels.get(LABEL_DRAFT) or None,
            )
        )
    return out


def find_instance(model_name: str) -> RunningInstance | None:
    for inst in list_instances():
        if inst.model == model_name:
            return inst
    return None


def start(
    model: Model,
    host: Host,
    gpu_index: int,
    draft: Model | None = None,
    draft_max: int = 16,
) -> RunningInstance:
    gguf_path = host.gguf_dir / model.file
    if not gguf_path.exists():
        raise FileNotFoundError(
            f"GGUF not found: {gguf_path}\n"
            f"Download it into {host.gguf_dir} first."
        )
    if draft is not None:
        draft_path = host.gguf_dir / draft.file
        if not draft_path.exists():
            raise FileNotFoundError(
                f"Draft GGUF not found: {draft_path}\n"
                f"Download it into {host.gguf_dir} first."
            )

    name = container_name(model, gpu_index)
    existing = find_instance(model.name)
    if existing and existing.state == "running":
        return existing

    _docker("rm", "-f", name, check=False)

    cmd = [
        "run",
        "-d",
        "--name", name,
        "--restart", "unless-stopped",
        "--gpus", f"device={gpu_index}",
        "--ipc", "host",
        "--shm-size", "4gb",
        "-l", f"{LABEL_MODEL}={model.name}",
        "-l", f"{LABEL_GPU}={gpu_index}",
        "-l", f"{LABEL_PORT}={model.port}",
    ]
    if draft is not None:
        cmd += ["-l", f"{LABEL_DRAFT}={draft.name}"]
    cmd += [
        "-v", f"{host.gguf_dir}:/models:ro",
        "-v", "llamacpp-cache:/root/.cache/llama.cpp",
        "-p", f"{host.bind_ip}:{model.port}:8080",
        "--security-opt", "no-new-privileges:true",
        "--ulimit", "memlock=-1",
        "--ulimit", "stack=67108864",
        "--log-driver", "local",
        "--log-opt", "max-size=50m",
        "--log-opt", "max-file=5",
        host.image,
        "-m", f"/models/{model.file}",
        "--alias", model.alias,
        "--host", "0.0.0.0",
        "--port", "8080",
        "--ctx-size", str(model.ctx_size),
        "--n-gpu-layers", "999",
        "--cache-type-k", model.kv_type,
        "--cache-type-v", model.kv_type,
        "--flash-attn", "auto",
        "--parallel", "1",
        "--jinja",
        "--no-mmproj",
    ]
    if draft is not None:
        cmd += [
            "--spec-draft-model", f"/models/{draft.file}",
            "--spec-draft-ctx-size", str(min(draft.ctx_size, model.ctx_size)),
            "--spec-draft-ngl", "999",
            "--spec-draft-n-max", str(draft_max),
            "--spec-draft-n-min", "0",
        ]
    _docker(*cmd)

    inst = find_instance(model.name)
    if inst is None:
        raise RuntimeError(f"Failed to locate {name} after docker run")
    return inst


def stop(model_name: str) -> bool:
    inst = find_instance(model_name)
    if inst is None:
        return False
    _docker("rm", "-f", inst.container, check=False)
    return True


def stop_all() -> int:
    insts = list_instances()
    for inst in insts:
        _docker("rm", "-f", inst.container, check=False)
    return len(insts)


def wait_healthy(bind_ip: str, port: int, timeout_s: float = 600.0) -> bool:
    """Poll /health on the bound endpoint until it returns 200 or timeout."""
    deadline = time.time() + timeout_s
    url = f"http://{bind_ip}:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError):
            pass
        time.sleep(2)
    return False


def logs(model_name: str, tail: int = 50, follow: bool = False) -> int:
    inst = find_instance(model_name)
    if inst is None:
        print(f"No running container for {model_name}")
        return 1
    args = ["logs", "--tail", str(tail)]
    if follow:
        args.append("-f")
    args.append(inst.container)
    return subprocess.call(["docker", *args])


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
