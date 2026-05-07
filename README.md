# local-llmops

Two-tier local LLM serving on a single RTX 3080 10 GiB. OpenAI-compatible
endpoints for agentic tools, with a router that compresses local-state into
Codex packets before paying for cloud tokens.

## Tiers

| Tier | Container | Endpoint | Model | Role |
| --- | --- | --- | --- | --- |
| Exec | `qwen35-4b-exec` | `http://${TAILSCALE}:8080/v1` | `unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL` (alias `local-qwen-exec`) | Default executor: tool calls, log/test parsing, JSON decisions, small patches |
| Smart | `qwen35-9b-smart` | `http://${TAILSCALE}:8081/v1` | `unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL` (alias `local-qwen-smart`) | Escalation, multi-step planning, chat, Codex packet generation |

`${TAILSCALE}` is `100.114.124.62`. Endpoints are deliberately not LAN-exposed.

## VRAM reality

The 10 GiB card cannot comfortably host both tiers at full configured context
simultaneously. Default operation: **`exec` always-on, `smart` on demand.**

```
docker compose up -d exec       # always-on
docker compose up -d smart      # bring up smart when escalation needed
docker compose stop smart       # release VRAM
```

To attempt both at once (lower contexts, expect tight margins):

```
docker compose --profile both up -d
```

If `smart` OOMs, ratchet `SMART_CTX_SIZE` from 16384 → 8192 in `.env`, then
`SMART_KV_TYPE` from `q8_0` → `q4_0`, then drop `--n-gpu-layers` from `999`
to a partial offload (manual edit to compose `command:`).

## Quick start

```
cp .env.example .env             # already populated; tweak if needed
docker compose up -d exec
./status.sh
```

First start downloads the GGUF weights into a Docker named volume
(`llamacpp-cache`); expect ~3 GiB for 4B and ~6 GiB for 9B. Subsequent starts
reuse the cache.

## Health & smoke

```
./status.sh                                      # both tiers + GPU + recent logs
python3 tests/smoke_exec.py                      # exec endpoint
python3 tests/smoke_smart.py                     # smart endpoint
python3 tests/agent_decision_schema.py           # JSON-schema regression
```

## Layout

```
.
├── docker-compose.yml          two services (exec, smart) under profiles
├── .env / .env.example         runtime config (.env gitignored)
├── status.sh                   one-shot health + GPU + log probe
├── docs/
│   ├── architecture.md         tier roles, generation defaults, agent contract
│   ├── routing-policy.md       4B→9B and 9B→Codex escalation rules
│   ├── decision.md             original ADR (Qwen2.5-Coder-7B / vLLM era)
│   ├── research.md             engine + model + optimization survey
│   ├── hardware.md             host inventory
│   └── DEPLOYMENT_LOG.md       append-only ops log
├── router/                     local-agent-router (in progress)
├── bench/                      smoke + regression scripts (vLLM-era; needs port)
├── tests/                      llama.cpp-era smoke and schema tests
└── archive/vllm/               prior Codex deployment (kept for reference)
```

## What changed vs. the prior vLLM deployment

The original deployment (in `archive/vllm/`) ran a single
`Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4` on vLLM 0.20.1 at `:8000`. This
repo replaces that with the two-tier llama.cpp design from the project spec:

- vLLM → llama.cpp `server-cuda` (GGUF Q4 native, simpler 10 GiB story)
- 1× 7B GPTQ → 2× Qwen3.5 GGUFs at 4B and 9B
- 1 endpoint → 2 endpoints with stable aliases (`local-qwen-exec`, `local-qwen-smart`)
- Adds a router/scaffold for schema-constrained `AgentDecision` JSON,
  4B→9B escalation rules, and Codex packet compression

See `docs/DEPLOYMENT_LOG.md` for the full migration log.

## Operations

```
docker compose ps
docker compose logs -f exec
docker compose logs -f smart
docker compose restart exec
docker compose down
```

## Client config

Any OpenAI-compatible client:

- Base URL: `http://100.114.124.62:8080/v1` (exec) or `:8081/v1` (smart)
- Model: `local-qwen-exec` or `local-qwen-smart`
- API key: any non-empty string

Default sampling (executor): `temperature=0.2, top_p=0.8, top_k=20`,
`chat_template_kwargs={"enable_thinking": false}`. See
`docs/architecture.md` for smart and reasoning-mode defaults.
