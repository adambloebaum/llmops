# Cheat sheet

All commands assume `cd ~/llmops` unless noted. Endpoints bind to the
host's Tailscale IPv4 only (auto-detected via `tailscale ip -4`).

Alias the CLI once:
```bash
alias llmops="$PWD/bin/llmops"
```

---

## Daily ops

```bash
llmops host                                  # detected hostname, bind IP, GPUs
llmops models                                # registry + fit-on-this-host
llmops status                                # GPUs + running instances + endpoints
llmops up                                    # interactive picker (GPU + model)
llmops use qwen3.5-4b                           # start (auto-picks GPU)
llmops use qwen3.5-9b --gpu 0                   # pin to a specific GPU
llmops use qwen3.5-9b --draft qwen3.5-0.8b      # speculative decoding (target + draft)
llmops use qwen3.5-9b --draft qwen3.5-0.8b --draft-max 8   # tune speculation depth
llmops stop qwen3.5-4b
llmops stop --all
llmops logs qwen3.5-4b -f
llmops endpoint qwen3.5-9b                      # just print the URL
nvidia-smi                                   # raw GPU state on host
```

## Speculative decoding

llama.cpp speculation: a small "draft" model proposes tokens, the larger
"target" model verifies them in parallel. On compatible prefixes this can
1.5-2x decode throughput. Both must share the same tokenizer/vocab (all
Qwen3.5 sizes do).

```bash
llmops use qwen3.5-9b --draft qwen3.5-0.8b
llmops status                                # shows draft=qwen3.5-0.8b
docker logs llmops-qwen3.5-9b-gpu0 2>&1 | grep "acceptance rate"
```

Tune with `--draft-max N` (default 16). Higher = more speculation per
step, faster on repetitive output, worse on novel output. The container
runs both models in one process; stop with the usual `llmops stop qwen3.5-9b`.

> Cosmetic llama.cpp warning `--gpu-layers-draft option will be ignored`
> can appear in the logs but the draft IS on GPU. VRAM and acceptance
> stats confirm.

## Direct docker (for debugging)

```bash
docker ps --filter label=llmops.model        # only llmops-managed containers
docker logs --tail 50 llmops-qwen3.5-9b-gpu0
docker exec -it llmops-qwen3.5-9b-gpu0 /bin/bash
docker exec llmops-qwen3.5-9b-gpu0 curl -fsS http://127.0.0.1:8080/health
```

## Direct API (curl)

Get the per-model base URL: `llmops endpoint qwen3.5-4b`. Example assumes
`http://100.114.124.62:8080/v1`.

```bash
# Health
curl -fsS http://100.114.124.62:8080/health

# Models
curl -fsS http://100.114.124.62:8080/v1/models | python3 -m json.tool

# Non-streaming chat
curl -sS http://100.114.124.62:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local' \
  -d '{
    "model": "qwen3.5-4b",
    "max_tokens": 64,
    "chat_template_kwargs": {"enable_thinking": false},
    "messages": [{"role": "user", "content": "ping"}]
  }' | python3 -m json.tool

# Schema-constrained (double-nested json_schema envelope is required —
# {"type":"json_schema","schema":{...}} is silently ignored by llama.cpp)
curl -sS http://100.114.124.62:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3.5-4b",
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "Reply",
        "strict": true,
        "schema": {
          "type": "object",
          "additionalProperties": false,
          "required": ["sentiment"],
          "properties": {"sentiment": {"type": "string", "enum": ["pos","neg","neu"]}}
        }
      }
    },
    "messages": [{"role": "user", "content": "I love this!"}]
  }' | python3 -m json.tool
```

## Tests

```bash
python3 tests/smoke_exec.py                  # /health, /v1/models, basic chat (qwen3.5-4b)
python3 tests/smoke_smart.py                 # same against qwen3.5-9b
python3 tests/agent_decision_schema.py       # 5x schema regression per model
```

## Benchmarks

```bash
python3 bench/llamacpp_bench.py --model qwen3.5-4b --concurrency 1,4,8 --requests 24
python3 bench/llamacpp_bench.py --model qwen3.5-9b --concurrency 1,4   --requests 16 \
  --max-tokens 256 --out bench/results/qwen3.5-9b_$(date +%Y%m%d).json
```

## Router (OpenAI-compat proxy on :8090)

The router selects qwen3.5-4b vs qwen3.5-9b by `model:` field, injects per-route
system prompts + sampling, enforces the AgentDecision schema for the
exec/smart routes, retries once on invalid JSON, and writes a JSONL
telemetry event per request to `router/logs/router.jsonl`. Stdlib only —
no venv to manage. Bind/upstream URLs are derived from `models.toml` +
`hosts/<hostname>.toml`.

```bash
./scripts/run-router.sh                      # foreground
nohup ./scripts/run-router.sh > /tmp/router.log 2>&1 & disown   # detached

# Health (probes both upstreams):
curl -fsS http://100.114.124.62:8090/health

# Models:
curl -fsS http://100.114.124.62:8090/v1/models

# Streaming chat through router:
curl -sS -N -X POST http://100.114.124.62:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.5-4b","stream":true,"messages":[{"role":"user","content":"hi"}]}'
```

Model IDs through the router:
- `qwen3.5-4b` → qwen3.5-4b, AgentDecision schema-constrained
- `qwen3.5-9b` → qwen3.5-9b, AgentDecision schema-constrained
- `qwen3.5-9b-reasoning` → qwen3.5-9b with `enable_thinking=true`, no schema
- `qwen3.5-9b-chat` (or `chat`) → qwen3.5-9b with chat system prompt, no schema

Optional auth: `export ROUTER_API_KEY=secret`, then clients must send
`Authorization: Bearer secret`.

## Hooking up agentic tools

```bash
# Through the router (recommended — handles schema + telemetry)
export OPENAI_BASE_URL=http://100.114.124.62:8090/v1
export OPENAI_API_KEY=local
codex --model qwen3.5-4b

# Continue / Cursor / Zed / opencode: any "OpenAI base URL" field
#   apiBase: http://100.114.124.62:8090/v1
#   model:   qwen3.5-4b   (or qwen3.5-9b, qwen3.5-9b-chat)
#   apiKey:  local

# Direct (bypassing router; no schema injection / telemetry):
#   apiBase: http://100.114.124.62:8080/v1
#   model:   qwen3.5-4b
```

Claude Code does **not** speak OpenAI-compat. To use a local model with
Claude Code, run LiteLLM in front of the router and set
`ANTHROPIC_BASE_URL=http://localhost:4000`.

## Telemetry + spend tracking

```bash
tail -f router/logs/router.jsonl

# Aggregate against a cloud baseline (default: gpt-5-codex):
python3 bench/spend_report.py
python3 bench/spend_report.py --baseline claude-opus-4-7
python3 bench/spend_report.py --by day
python3 bench/spend_report.py --by route --json
python3 bench/spend_report.py --since 2026-05-09

# Edit the rate table:
$EDITOR router/rates.json
```

## Editing config

```bash
$EDITOR models.toml                          # add models, change ctx/kv, retune sampling
$EDITOR hosts/$(hostname -s).toml            # gguf dir, bind, autostart

# After a config change to a running model, recycle it:
llmops stop qwen3.5-9b && llmops use qwen3.5-9b
```

## Adding a new vetted model

```bash
# 1. Download the GGUF
curl -L --retry-all-errors -o ~/llm-models/gguf/<filename>.gguf \
  "https://huggingface.co/<repo>/resolve/main/<filename>.gguf"

# 2. Add an entry to models.toml (pick an unused port: 8082+)
$EDITOR models.toml

# 3. Bring it up
llmops models                                # confirm it shows
llmops use <name>
```

> Don't use llama.cpp's `-hf user/repo:quant` shorthand — it expects a
> `gguf-manifests/...` file that Unsloth's repos don't ship and 404s.
> Pre-download + mount is the working path. Always pass
> `--retry-all-errors` to curl; without it a connection broken mid-stream
> can silently produce a truncated file.

## Troubleshooting

```bash
# Tailscale clients can't reach the endpoint?
# 1. Verify bind IP matches Tailscale's:
llmops host
tailscale ip -4
# 2. Verify the container's port mapping is non-empty:
docker inspect llmops-qwen3.5-4b-gpu0 --format '{{json .NetworkSettings.Ports}}'
ss -tln | grep -E '808[0-9]'
# If the port map is empty, Tailscale wasn't up when the container started.
# Stop and re-launch via the CLI:
llmops stop qwen3.5-4b && llmops use qwen3.5-4b

# Container OOMs / segfaults (exit 139)
nvidia-smi
llmops logs qwen3.5-9b
# Fix: lower ctx_size in models.toml, or drop kv_type to q4_0, then recycle.

# Schema-constrained outputs ignored (model returns freeform JSON)
# Make sure response_format uses the OpenAI envelope:
#   {"type":"json_schema","json_schema":{"name":"X","strict":true,"schema":{...}}}
# NOT {"type":"json_schema","schema":{...}} -- llama.cpp silently ignores that.

# llama.cpp image won't see the GPU
docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
# If that works but server-cuda doesn't, check llmops logs <model> for
# "no usable GPU found"; usually means the GGUF path is wrong.

# Driver dies after kernel upgrade (no DKMS)
sudo apt install --reinstall nvidia-driver-580-open
sudo reboot
```

## Volumes / disk

```bash
docker volume ls
docker volume inspect llamacpp-cache         # /var/lib/docker/volumes/llamacpp-cache/_data
du -sh ~/llm-models/gguf/*                   # GGUFs on disk
df -hT /                                     # free space on root
```

## Repo + git

```bash
git status
git log --oneline -10
git diff
git push
gh repo view --web
```
