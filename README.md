# llmops

Portable local-LLM ops. One repo, runs on any GPU host. OpenAI-compatible
endpoints for agentic tools (Hermes, Claude Code, Codex), Tailscale-bound,
nothing auto-starts.

## Quick start

```bash
# from inside the repo
alias llmops="$PWD/bin/llmops"

llmops host           # what was detected on this box (GPUs, bind IP, etc.)
llmops models         # vetted registry, with fit-on-this-host indicators
llmops up             # interactive: pick GPU, pick model
# or:
llmops use qwen3.5-9b    # non-interactive; auto-picks a GPU with enough VRAM
llmops status         # what's running + endpoints
llmops stop qwen3.5-9b
```

`llmops use` prints the endpoint URL once `/health` is green. That URL is
the static base for any OpenAI-compatible client.

## Layout

```
.
├── models.toml                 model registry — single source of truth
├── hosts/                      per-host config (gguf dir, bind, autostart)
│   ├── home-compute.toml
│   └── example.toml
├── llmops/                     CLI Python package (stdlib only)
│   ├── cli.py
│   ├── registry.py
│   ├── host.py
│   └── runner.py
├── bin/llmops                  CLI shim (alias this onto PATH)
├── router/                     optional OpenAI-compat facade :8090
├── skills/                     in-repo Claude Code skills
│   └── add-model/              "set up X model" → resolve + download + register
├── scripts/install-skills.sh   symlink skills/ into ~/.claude/skills/
├── scripts/run-router.sh       start the router
├── docs/                       cli + architecture + hardware + ops log
├── bench/                      concurrency sweep + spend report
└── tests/                      endpoint smoke + schema regression
```

## Design in one paragraph

`models.toml` is the registry; each model has a static port and a VRAM
floor. `hosts/<hostname>.toml` overrides per-host bits (gguf dir, bind IP,
autostart) — anything omitted is auto-detected (Tailscale IP via
`tailscale ip -4`, GPUs via `nvidia-smi`). `llmops use <model>` does a
`docker run` with labels (`llmops.model`, `llmops.gpu`, `llmops.port`), so
`llmops status` and `llmops stop` work regardless of how the container was
named. Endpoints bind to the host's Tailscale IPv4 — stable across reboots,
hidden from LAN.

## Boot behavior

Default is **no auto-start** — bring up what you want, when you want. To
opt in on a host, set `autostart = "<model-name>"` in
`hosts/<hostname>.toml` and install a systemd unit (TODO: generic
installer). Any boot-time unit must order itself
`After=tailscaled.service` to avoid Docker binding the Tailscale IP before
Tailscale is up.

## Multi-GPU + multi-host

The CLI auto-detects all NVIDIA GPUs via `nvidia-smi` and picks one with
enough free VRAM. To pin: `llmops use <model> --gpu N`. To run multiple
models simultaneously across different GPUs, just `llmops use` each — they
get their own containers and ports.

For multi-host: clone the repo on each box. Each box advertises its
endpoints over Tailscale. Cross-host routing is intentionally out of scope
— point your client at whichever box has the model loaded.

## Router (optional)

`router/` is a stdlib HTTP server (`:8090`) that fronts the model endpoints
with one URL, doing schema-constrained JSON, per-route prompt injection,
and telemetry. Useful when you want one client config that's robust to
which model happens to be loaded. Not required — most clients hit the
per-model endpoints directly.

Run with `./scripts/run-router.sh`. The script derives bind IP and upstream
URLs from `models.toml` + `hosts/<hostname>.toml`.

## Adding a model

1. Download the GGUF into the host's `gguf_dir`.
2. Add an entry to `models.toml`. Pick an unused port (8080+).
3. `llmops models` to confirm it shows.
4. `llmops use <name>` to start it.

## Client config

Once a model is up, any OpenAI-compatible client works:

- Base URL: output of `llmops endpoint <model>`
- Model name: the `alias` from `models.toml`
- API key: any non-empty string (llama.cpp doesn't require one)

See `docs/cli.md` for full CLI reference, `docs/architecture.md` for the
two-tier routing rationale, and `docs/DEPLOYMENT_LOG.md` for migration
history.
