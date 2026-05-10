"""llmops CLI — manage local LLM containers from one repo, portable across hosts.

Commands:
    llmops status                          # all running instances + GPU state
    llmops models                          # registry, filtered to fit current host
    llmops use <model> [--gpu N]           # start a model (auto-picks GPU if omitted)
    llmops stop <model> | --all
    llmops logs <model> [--tail N] [-f]
    llmops endpoint <model>                # print base URL for clients
    llmops host                            # show detected host + GPU state
    llmops up                              # interactive picker (TUI-lite)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import host as host_mod
from . import registry, runner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_all():
    root = _repo_root()
    models = registry.load(root / "models.toml")
    host = host_mod.load(root)
    gpus = host_mod.detect_gpus()
    return root, models, host, gpus


def _pick_gpu(gpus: list, need_gib: float, prefer_index: int | None = None) -> int | None:
    if prefer_index is not None:
        for g in gpus:
            if g.index == prefer_index:
                return g.index if g.free_gib >= need_gib else None
        return None
    # auto-pick: most free VRAM among GPUs that fit
    fitting = [g for g in gpus if g.free_gib >= need_gib]
    if not fitting:
        return None
    return max(fitting, key=lambda g: g.free_mib).index


def _fmt_endpoint(host, port: int) -> str:
    return f"http://{host.bind_ip}:{port}/v1"


def cmd_status(_args) -> int:
    _, _, host, gpus = _load_all()
    print(f"host: {host.hostname}    bind: {host.bind_ip}")
    if host.config_path:
        print(f"config: {host.config_path}")
    print()
    print("GPUs:")
    if not gpus:
        print("  (no NVIDIA GPUs detected)")
    for g in gpus:
        print(f"  [{g.index}] {g.name:32s}  {g.free_gib:5.1f} / {g.total_gib:5.1f} GiB free")
    print()
    print("Running:")
    insts = runner.list_instances()
    if not insts:
        print("  (none)")
        return 0
    for i in insts:
        ep = _fmt_endpoint(host, i.port)
        draft_str = f"  draft={i.draft}" if i.draft else ""
        print(f"  {i.model:14s} gpu={i.gpu}  port={i.port}  {i.state}/{i.health}{draft_str}  -> {ep}")
    return 0


def cmd_models(_args) -> int:
    _, models, _, gpus = _load_all()
    max_free = max((g.free_gib for g in gpus), default=0.0)
    max_total = max((g.total_gib for g in gpus), default=0.0)
    print(f"Registry: {len(models)} model(s). Largest GPU: {max_total:.1f} GiB total, {max_free:.1f} GiB free.\n")
    name_w = max((len(n) for n in models), default=10)
    for name, m in models.items():
        fits_total = m.min_vram_gb <= max_total
        fits_now = m.min_vram_gb <= max_free
        marker = "  " if fits_now else ("!!" if not fits_total else "..")
        print(
            f"{marker} {name:{name_w}}  port={m.port}  vram>={m.min_vram_gb:>4.1f}G  "
            f"ctx={m.ctx_size:>6}  kv={m.kv_type}  {m.description}"
        )
    print()
    print("  legend:    = fits on free VRAM right now")
    print("          .. = fits on this host total but VRAM busy")
    print("          !! = won't fit on any GPU here")
    return 0


def cmd_use(args) -> int:
    _, models, host, gpus = _load_all()
    if args.model not in models:
        print(f"unknown model: {args.model}", file=sys.stderr)
        print(f"available: {', '.join(models)}", file=sys.stderr)
        return 2
    m = models[args.model]

    draft = None
    if getattr(args, "draft", None):
        if args.draft not in models:
            print(f"unknown draft model: {args.draft}", file=sys.stderr)
            print(f"available: {', '.join(models)}", file=sys.stderr)
            return 2
        if args.draft == args.model:
            print("--draft must differ from the target model", file=sys.stderr)
            return 2
        draft = models[args.draft]

    if not gpus:
        print("no NVIDIA GPUs detected — refusing to start", file=sys.stderr)
        return 3

    # Speculative decoding loads both models into the same container, on the
    # same GPU. Budget = target + ~70% of draft's standalone VRAM floor (draft
    # KV is small in practice).
    need = m.min_vram_gb + (draft.min_vram_gb * 0.7 if draft else 0)
    gpu_idx = _pick_gpu(gpus, need, prefer_index=args.gpu)
    if gpu_idx is None:
        if args.gpu is not None:
            print(
                f"GPU {args.gpu} does not have {need:.1f} GiB free "
                f"(or does not exist).",
                file=sys.stderr,
            )
        else:
            print(
                f"no GPU on this host has {need:.1f} GiB free. "
                f"Stop another model first or pick a smaller model"
                + (" / smaller draft." if draft else "."),
                file=sys.stderr,
            )
        return 4

    if draft:
        print(f"starting {m.name} on gpu={gpu_idx} (port {m.port}) with draft={draft.name}...")
    else:
        print(f"starting {m.name} on gpu={gpu_idx} (port {m.port})...")
    try:
        runner.start(m, host, gpu_idx, draft=draft, draft_max=args.draft_max)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 5

    if args.no_wait:
        print(f"endpoint: {_fmt_endpoint(host, m.port)}  (not waited for /health)")
        return 0

    print("waiting for /health...")
    ok = runner.wait_healthy(host.bind_ip, m.port, timeout_s=args.timeout)
    if not ok:
        print(
            f"container started but /health did not respond within {args.timeout}s. "
            f"check: docker logs llmops-{m.name}-gpu{gpu_idx}",
            file=sys.stderr,
        )
        return 6

    ep = _fmt_endpoint(host, m.port)
    print()
    print(f"  endpoint:  {ep}")
    print(f"  model:     {m.alias}")
    if draft:
        print(f"  draft:     {draft.alias}  (speculative decoding, --draft-max {args.draft_max})")
    print(f"  api key:   any non-empty string")
    return 0


def cmd_stop(args) -> int:
    if args.all:
        n = runner.stop_all()
        print(f"stopped {n} container(s)")
        return 0
    if not args.model:
        print("usage: llmops stop <model> | --all", file=sys.stderr)
        return 2
    if runner.stop(args.model):
        print(f"stopped {args.model}")
        return 0
    print(f"no running container for {args.model}", file=sys.stderr)
    return 1


def cmd_logs(args) -> int:
    return runner.logs(args.model, tail=args.tail, follow=args.follow)


def cmd_endpoint(args) -> int:
    _, models, host, _ = _load_all()
    if args.model not in models:
        print(f"unknown model: {args.model}", file=sys.stderr)
        return 2
    m = models[args.model]
    print(_fmt_endpoint(host, m.port))
    return 0


def cmd_host(_args) -> int:
    _, _, host, gpus = _load_all()
    print(f"hostname:    {host.hostname}")
    print(f"bind ip:     {host.bind_ip}")
    print(f"gguf dir:    {host.gguf_dir}")
    print(f"image:       {host.image}")
    print(f"autostart:   {host.autostart or 'none'}")
    print(f"config:      {host.config_path or '(none — using defaults)'}")
    print(f"gpus:        {len(gpus)}")
    for g in gpus:
        print(f"  [{g.index}] {g.name}  {g.total_gib:.1f} GiB")
    return 0


def cmd_up(_args) -> int:
    _, models, host, gpus = _load_all()
    if not gpus:
        print("no NVIDIA GPUs detected", file=sys.stderr)
        return 3

    print(f"host: {host.hostname}    bind: {host.bind_ip}\n")
    print("GPUs:")
    for g in gpus:
        print(f"  [{g.index}] {g.name}  {g.free_gib:.1f} / {g.total_gib:.1f} GiB free")

    if len(gpus) == 1:
        gpu_idx = gpus[0].index
        print(f"\nUsing GPU {gpu_idx} (only one available).")
    else:
        choice = input("\nGPU index: ").strip()
        try:
            gpu_idx = int(choice)
        except ValueError:
            print("invalid GPU index", file=sys.stderr)
            return 2
        if not any(g.index == gpu_idx for g in gpus):
            print(f"GPU {gpu_idx} not present", file=sys.stderr)
            return 2

    free = next(g.free_gib for g in gpus if g.index == gpu_idx)
    fitting = [(n, m) for n, m in models.items() if m.min_vram_gb <= free]
    if not fitting:
        print(f"\nNo registered models fit in {free:.1f} GiB free.", file=sys.stderr)
        return 4

    print(f"\nModels that fit ({free:.1f} GiB free):")
    for i, (n, m) in enumerate(fitting, 1):
        print(f"  [{i}] {n:14s} vram>={m.min_vram_gb:.1f}G  {m.description}")

    pick = input("\nModel number: ").strip()
    try:
        idx = int(pick) - 1
        name, m = fitting[idx]
    except (ValueError, IndexError):
        print("invalid model selection", file=sys.stderr)
        return 2

    args = argparse.Namespace(
        model=name, gpu=gpu_idx, draft=None, draft_max=16,
        no_wait=False, timeout=600.0,
    )
    return cmd_use(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llmops", description="Local LLM ops — portable across GPU hosts.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show running instances + GPU state").set_defaults(func=cmd_status)
    sub.add_parser("models", help="list registered models + fit check").set_defaults(func=cmd_models)
    sub.add_parser("host", help="show detected host + GPU inventory").set_defaults(func=cmd_host)
    sub.add_parser("up", help="interactive GPU + model picker").set_defaults(func=cmd_up)

    p_use = sub.add_parser("use", help="start a model")
    p_use.add_argument("model", help="model name (see `llmops models`)")
    p_use.add_argument("--gpu", type=int, default=None, help="GPU index (default: auto-pick)")
    p_use.add_argument(
        "--draft",
        default=None,
        help="draft model name for speculative decoding (must share vocab with target)",
    )
    p_use.add_argument(
        "--draft-max",
        type=int,
        default=16,
        help="max tokens to speculate per step (default: 16)",
    )
    p_use.add_argument("--no-wait", action="store_true", help="don't wait for /health")
    p_use.add_argument("--timeout", type=float, default=600.0, help="seconds to wait for /health")
    p_use.set_defaults(func=cmd_use)

    p_stop = sub.add_parser("stop", help="stop a model")
    p_stop.add_argument("model", nargs="?", help="model name to stop")
    p_stop.add_argument("--all", action="store_true", help="stop all llmops containers")
    p_stop.set_defaults(func=cmd_stop)

    p_logs = sub.add_parser("logs", help="show container logs for a model")
    p_logs.add_argument("model")
    p_logs.add_argument("--tail", type=int, default=50)
    p_logs.add_argument("-f", "--follow", action="store_true")
    p_logs.set_defaults(func=cmd_logs)

    p_ep = sub.add_parser("endpoint", help="print base URL for a model")
    p_ep.add_argument("model")
    p_ep.set_defaults(func=cmd_endpoint)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
