# Cheat sheet

All commands assume `cd ~/local-llmops` unless noted. Endpoints are bound to
`100.114.124.62` (Tailscale) only.

---

## Daily ops

```bash
./status.sh                                  # health + GPU + recent logs (both tiers)
docker compose ps                            # which containers exist + their state
docker compose logs -f exec                  # tail exec logs
docker compose logs -f smart                 # tail smart logs
nvidia-smi                                   # GPU state on host
```

## Mode switching (10 GiB can't run both at default ctx)

```bash
./scripts/use-exec.sh                        # 4B on :8080 (always-on default)
./scripts/use-smart.sh                       # 9B on :8081 (stops exec)
./scripts/use-both.sh                        # EXPERIMENTAL: 8K q8 + 8K q4
docker compose --project-directory ~/local-llmops ps  # confirm which is active
```

## First-time setup (already done; reference only)

```bash
cp .env.example .env
docker volume create llamacpp-cache          # only if not present
docker compose --profile default up -d exec  # always-on tier
sudo ./scripts/install-boot-fix.sh           # systemd unit so exec auto-starts after Tailscale
```

## Reboot recovery

```bash
# After every reboot, until install-boot-fix.sh has been run:
./scripts/recover-after-boot.sh              # docker compose down + up exec

# Quick check whether the boot race bit you (look for empty Ports map):
docker inspect qwen35-4b-exec --format '{{json .NetworkSettings.Ports}}'
ss -tln | grep -E '808[01]'                  # should show your bound IP

# After install-boot-fix.sh:
sudo systemctl status local-llmops.service
sudo systemctl restart local-llmops.service
```

## Container manipulation

```bash
docker compose --profile default up -d exec  # bring up exec
docker compose --profile smart   up -d smart # bring up smart
docker compose stop  exec                    # stop (won't auto-start on reboot)
docker compose start exec                    # restart a previously-stopped container
docker compose restart exec                  # in-place restart (same container)
docker compose down                          # remove all containers (volumes kept)
docker compose down --volumes                # also wipe llamacpp-cache (NUKES weights)
docker compose pull                          # fetch latest llama.cpp:server-cuda image

# Force-recreate a single service (most useful after .env or compose edits):
docker compose up -d --force-recreate exec

# Inside the container (debugging):
docker exec -it qwen35-4b-exec /bin/bash
docker exec qwen35-4b-exec curl -fsS http://127.0.0.1:8080/health
docker exec qwen35-4b-exec ls /models /root/.cache/llama.cpp
```

## Chat

```bash
# Built-in WebUI (best for casual use): open in any browser on Tailscale net
#   http://100.114.124.62:8080   (exec)
#   http://100.114.124.62:8081   (smart, when up)

python3 scripts/chat.py                                    # exec REPL
python3 scripts/chat.py --smart                            # smart REPL
python3 scripts/chat.py --smart --think                    # smart with reasoning
python3 scripts/chat.py --once "explain selectors"         # one-shot exec
python3 scripts/chat.py --smart --once "..." --max-tokens 2048
```

## Direct API (curl)

```bash
# Health
curl -fsS http://100.114.124.62:8080/health
curl -fsS http://100.114.124.62:8081/health

# Models
curl -fsS http://100.114.124.62:8080/v1/models | python3 -m json.tool

# Non-streaming chat
curl -sS http://100.114.124.62:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local' \
  -d '{
    "model": "local-qwen-exec",
    "max_tokens": 64,
    "chat_template_kwargs": {"enable_thinking": false},
    "messages": [{"role": "user", "content": "ping"}]
  }' | python3 -m json.tool

# Schema-constrained (note the double-nested json_schema envelope!)
curl -sS http://100.114.124.62:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "local-qwen-exec",
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
python3 tests/smoke_exec.py                  # /health, /v1/models, basic chat
python3 tests/smoke_smart.py                 # same against smart (must be up)
python3 tests/agent_decision_schema.py       # 5x schema regression on each tier
```

## Benchmarks

```bash
# Quick sweep on exec
python3 bench/llamacpp_bench.py --tier exec --concurrency 1,4,8 --requests 24

# Long-form smart bench (after ./scripts/use-smart.sh)
python3 bench/llamacpp_bench.py --tier smart --concurrency 1,4 --requests 16 \
  --max-tokens 256 --out bench/results/smart_$(date +%Y%m%d).json

# Heavy decode test
python3 bench/llamacpp_bench.py --tier exec --concurrency 1 --requests 8 \
  --max-tokens 512
```

## Hooking up agentic tools

```bash
# Codex CLI
export OPENAI_BASE_URL=http://100.114.124.62:8080/v1
export OPENAI_API_KEY=local
codex --model local-qwen-exec

# aider
aider --openai-api-base http://100.114.124.62:8080/v1 \
      --openai-api-key local \
      --model openai/local-qwen-exec

# Continue / Cursor / Zed: any "OpenAI base URL" field
#   apiBase: http://100.114.124.62:8080/v1
#   model:   local-qwen-exec
#   apiKey:  local
```

Claude Code does **not** speak OpenAI-compat; you'd need a LiteLLM proxy in
front and `ANTHROPIC_BASE_URL=http://localhost:4000`.

## Editing config

```bash
# Tweak context, KV type, model file, ports, etc.
$EDITOR .env

# After .env edit, force-recreate to pick up changes:
docker compose up -d --force-recreate exec   # or smart
```

## Adding / changing models

```bash
# Download a new GGUF
curl -L --retry-all-errors -o ~/llm-models/gguf/<filename>.gguf \
  "https://huggingface.co/<repo>/resolve/main/<filename>.gguf"

# Point the tier at it
sed -i 's/^EXEC_MODEL_FILE=.*/EXEC_MODEL_FILE=<filename>.gguf/' .env
docker compose up -d --force-recreate exec
```

> Don't use llama.cpp's `-hf user/repo:quant` shorthand — it expects a
> `gguf-manifests/...` file that Unsloth's repos don't ship and 404s.
> Pre-download + `-m` mount is the working path. Always pass
> `--retry-all-errors` to curl; without it a connection broken mid-stream
> can silently produce a truncated file.

## Troubleshooting recipes

```bash
# Everything looks healthy but Tailscale clients can't reach it?
# (Boot-race symptom: NetworkSettings.Ports is empty)
docker inspect qwen35-4b-exec --format '{{json .NetworkSettings.Ports}}'
ss -tln | grep -E '808[01]'
./scripts/recover-after-boot.sh

# Container OOMs / segfaults (exit 139)
nvidia-smi
docker logs --tail 50 qwen35-9b-smart | grep -iE 'cuda|oom|alloc|error'
# Fix in .env: lower SMART_CTX_SIZE (16384 -> 8192), then SMART_KV_TYPE q8_0 -> q4_0
docker compose up -d --force-recreate smart

# Schema-constrained outputs ignored (model returns freeform JSON)
# Make sure response_format uses the OpenAI envelope:
#   {"type":"json_schema","json_schema":{"name":"X","strict":true,"schema":{...}}}
# NOT {"type":"json_schema","schema":{...}} -- llama.cpp silently ignores that.

# llama.cpp image won't see the GPU
docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
# If that works but server-cuda doesn't, check `docker logs <container>`
# for "no usable GPU found"; usually means -m path is wrong (model never loaded)

# Driver dies after kernel upgrade (no DKMS)
sudo apt install --reinstall nvidia-driver-580-open
sudo reboot
```

## Repo + git

```bash
git status
git log --oneline -10
git diff
git push                                     # land local commits to origin
gh repo view --web                           # open the repo on GitHub
```

## Volumes / disk

```bash
docker volume ls
docker volume inspect llamacpp-cache         # where: /var/lib/docker/volumes/llamacpp-cache/_data
du -sh ~/llm-models/gguf/*                   # GGUFs on disk
df -hT /                                     # free space on root
```
