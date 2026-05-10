# llmops CLI

Portable local-LLM management. One repo, runs on any GPU host. Nothing
auto-starts; you bring models up explicitly. Endpoints are static
per-model (see `models.toml`), so client config in Hermes / Claude Code /
Codex never has to change.

## Install / first run on a new host

1. Clone the repo, `cd` into it.
2. Make sure `python3` (3.11+), `docker`, and `nvidia-smi` are on PATH,
   plus `tailscale` if you want the auto-detected Tailscale bind.
3. (Optional) `cp hosts/example.toml hosts/$(hostname -s).toml` and edit.
   Without this file, everything auto-detects.
4. Download GGUF files into the host's `gguf_dir` (default
   `~/llm-models/gguf`). The names in `models.toml` must match what's on disk.
5. Add `bin/` to PATH or alias `llmops`:
   ```bash
   alias llmops="$PWD/bin/llmops"
   ```

## Commands

```
llmops host                       # what was detected on this box
llmops models                     # registry, with fit-on-this-host indicators
llmops status                     # GPUs + running instances + endpoints
llmops up                         # interactive: pick GPU, pick model
llmops use <model> [--gpu N]      # non-interactive start
llmops stop <model> | --all
llmops logs <model> [--tail N] [-f]
llmops endpoint <model>           # just print the URL, for shell scripting
```

## How it works

- **Registry** (`models.toml`): one entry per vetted model. Ports are static.
  Adding a model = one entry here + a downloaded GGUF.
- **Per-host config** (`hosts/<hostname>.toml`): overrides for things that
  can't be auto-detected (preferred autostart, custom gguf_dir).
- **Containers**: `docker run` with labels (`llmops.model`, `llmops.gpu`,
  `llmops.port`). No `docker-compose` for the dynamic path — compose's
  hardcoded service names fight the N-model × M-GPU world.
- **Endpoints**: bound to the host's Tailscale IP by default. Format:
  `http://<bind_ip>:<port>/v1`. Stable forever for a given model.

## Multi-GPU

When the host has more than one GPU, `llmops use <model> --gpu N` pins to
a specific card. With no `--gpu` flag, the CLI auto-picks the GPU with the
most free VRAM that still fits `min_vram_gb`. You can run several models
simultaneously across different GPUs — each becomes its own container.

## Adding a vetted model

1. Download the GGUF into `gguf_dir`.
2. Add an entry to `models.toml`. Pick an unused port (8080+).
3. `llmops models` to confirm it shows up.
4. `llmops use <name>` to start it.

## Auto-start on boot (optional)

Default behavior is **no auto-start**. If you want a specific model to come
up on boot (e.g. for an always-on exec tier):

1. Set `autostart = "qwen3.5-4b"` in `hosts/<hostname>.toml`.
2. Install a systemd unit that runs `llmops use <model>` after
   `tailscaled.service` is up. (TODO: a generic installer script.)

## Client config

Once a model is up, any OpenAI-compatible client works:

- Base URL: output of `llmops endpoint <model>`
- Model name: the `alias` from `models.toml` (e.g. `qwen3.5-4b`)
- API key: any non-empty string (llama.cpp doesn't require one)
