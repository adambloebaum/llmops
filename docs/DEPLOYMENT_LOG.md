# Local LLM Inference Server Deployment Log

Root: `/home/adam`
Started: `2026-05-07T02:06:39Z`

## Checkpoints

### 2026-05-07T02:06:39Z - Mission start

- Treating `/home/adam` as the deployment root. No enclosing git repository was detected from that directory.
- Beginning Phase 1 hardware reconnaissance before selecting any model, engine, quantization, or parallelism strategy.
- Slack: a bot token is present in the environment, but no target channel/user variable was found. I will attempt safe destination discovery after collecting baseline system facts; local updates will be maintained here regardless.
- Guardrails: avoid destructive storage changes; do not expose services publicly; use containers and isolated directories; verify all hardware characteristics with commands.

## Decisions

- Primary baseline selected: `vllm/vllm-openai:v0.20.1-cu129-ubuntu2404` serving `Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4`.
- Rationale: the host has a single RTX 3080 10 GiB; long-context serving is KV-cache constrained. Qwen2.5-Coder-7B has a smaller KV footprint than Qwen3-8B/Qwen3.5-9B while preserving a code-agent focus and official INT4 weights.
- Excluded MoE/routed models per mission restriction: Llama 4 MoE variants, DeepSeek V3/V4-style models, Qwen3-Coder-Next, Qwen3.5 A*B variants, GLM Flash routed variants, and gpt-oss.
- Launch optimizations: prefix caching and chunked prefill. Deferred until regression testing: FP8 KV, INT4 KV, TurboQuant/KIVI-style KV, speculative decoding, EAGLE/MTP.

### 2026-05-07T02:12:38Z - Slack checkpoint

- Discovered Slack bot token and joined channel `temp-llm-adv-test`.
- Posted checkpoint summarizing hardware recon and selected candidate stack.

### 2026-05-07T02:13:00Z - Deployment scaffold

- Created `hardware.md`, `research.md`, `decision.md`, `docker-compose.yml`, `.env`, `README.md`, `status.sh`, and initial `bench/` scripts.
- Docker Compose config validated.
- Endpoint configured to bind to Tailscale IPv4 only: `100.114.124.62:8000`.

### 2026-05-07T02:24:45Z - First container start failure

- vLLM image pulled successfully and container started.
- Startup failed before model load because vLLM `v0.20.1` rejects `--disable-log-requests` and warns that model should be positional, not passed via `--model`.
- Patched `docker-compose.yml` to remove `--disable-log-requests` and pass `${MODEL_ID}` as the first positional command argument.

### 2026-05-07T02:29:07Z - Baseline server healthy

- Model download completed in about `185 s`; checkpoint size `5.19 GiB`.
- GPTQ Marlin kernel selected successfully.
- FlashAttention 2 backend selected.
- Model load used `5.18 GiB`; total GPU memory after serving warmup about `8.26 GiB`.
- vLLM reported available KV cache memory `2.29 GiB`, GPU KV cache size `42,912 tokens`, and max concurrency for 32,768-token requests `1.31x`.
- Endpoint became healthy on `100.114.124.62:8000`.
- vLLM warned model `generation_config.json` overrides default sampling; patching launch args with `--generation-config vllm` before validation to keep server defaults predictable.

### 2026-05-07T02:32:20Z - Smoke validation

- `/v1/models` returned `qwen2.5-coder-7b`.
- Basic chat returned exact `pong`.
- Forced tool call returned OpenAI-style `tool_calls` with function name `get_weather` and JSON string arguments.
- Streaming returned 16 SSE chunks.

### 2026-05-07T02:33:00Z - Regression harness adjustment

- Initial regression suite passed BFCL-style forced tool calling, JSON mode, and aider-style diff.
- GSM8K tiny item failed because `max_tokens=64` truncated the model while it was explaining, before the final answer. Prompt adjusted to request only the number and allow 128 tokens.

### 2026-05-07T02:34:00Z - Baseline quality caveat

- Retried GSM8K tiny item with tighter prompt. Model returned `33`; expected `31`.
- Treating this as a real baseline quality miss for arithmetic, not a harness issue.
- Regression suite changed to continue after failures so all categories are reported in a single run.
- Long-context recall request initially exceeded the configured 32K limit by one token: 32,705 input + 64 output = 32,769 total. Reduced filler and output budget; added HTTP error-body reporting to the harness.
- Long-context recall now passes with calibrated prompt size; GSM8K tiny remains the only regression failure.

### 2026-05-07T02:35:07Z - Benchmark harness adjustment

- Initial `vllm bench serve` failed because it tried to resolve tokenizer files using served alias `qwen2.5-coder-7b` as a Hugging Face repo.
- Patched `bench/run_vllm_bench.sh` to pass `--tokenizer "$MODEL_ID"` while keeping `--model "$SERVED_MODEL_NAME"` for requests.

### 2026-05-07T02:37:40Z - Baseline random benchmark complete

- Completed `vllm bench serve` on OpenAI chat endpoint for random 512-token input / 128-token output at concurrency 1, 4, 8, and 16.
- No failed benchmark requests.
- Output throughput saturated around `400 tok/s` at concurrency 8-16.
- TTFT increased from `138 ms` at concurrency 1 to `3711 ms` mean at concurrency 16.
- GPU telemetry during benchmark: max temp `66 C`, max power `319.23 W`, max GPU memory `8971 MiB`.
- Thermal behavior stable; power reaches the RTX 3080 board limit, so no power-limit increase is justified.

### 2026-05-07T02:45:05Z - Agent workflow validation

- Initial Aider validation failed because the isolated Docker client targeted `127.0.0.1:8000`; the inference service is intentionally bound only to `100.114.124.62:8000`.
- Retried Aider against `http://100.114.124.62:8000/v1` with model `openai/qwen2.5-coder-7b`.
- Aider `v0.86.2` generated and applied a SEARCH/REPLACE edit in throwaway repo `bench/agent-smoke`, changing `return a - b` to `return a + b`.
- Verified `python3 bench/agent-smoke/calc.py` prints `5`.
- Re-ran smoke suite: `/v1/models`, basic chat, forced OpenAI-style tool call, and streaming all passed.
- Updated `status.sh` to show a live two-second vLLM metrics sample for prompt/output token rates, active requests, and waiting requests.
- Verified listener scope with `ss -tlnp`: only `100.114.124.62:8000` is bound for the inference endpoint.
- Posted Slack checkpoint to channel `temp-llm-adv-test`.

### 2026-05-07T02:51:17Z - Extended benchmark coverage

- Added `bench/run_scenario.sh` for reproducible named `vllm bench serve` random-token scenarios.
- Added `bench/tool_trajectory.py` for concurrent forced OpenAI-style tool-call validation with JSON argument checks.
- Tool-call trajectory passed `116/116` forced tool-call requests across concurrency 1, 4, 8, and 16.
- Completed long-in/short-out benchmark: random 4096 input / 128 output at c1/c4/c8/c16, zero failures. Output throughput peaked at `164.45 tok/s` at c8; c16 mean TTFT rose to `13651 ms`.
- Completed long-in/long-out benchmark: random 4096 input / 512 output at c1/c4/c8/c16, zero failures. Output throughput held near `300 tok/s` at c8-c16; c16 mean TTFT rose to `9855 ms`.
- Additional long-scenario telemetry: max temp `68 C`, max power `319.30 W`, max GPU memory `8971 MiB`.
- Operational interpretation: for long-context agent traffic on this 10 GiB GPU, c4-c8 is the practical burst range; c16 is stable but latency-heavy.

### 2026-05-07T02:54:57Z - FP8 KV experiment rejected

- Tested `KV_CACHE_DTYPE=fp8_e5m2` as a reversible Phase 6 optimization.
- Server started successfully and reported larger KV capacity: `71,648 tokens`, maximum 32K-request concurrency `2.19x`.
- vLLM warning noted potential accuracy drop without a proper scaling factor.
- Smoke remained superficially healthy, but regression failed long-context recall. This violates launch reliability goals.
- Reverted `.env` to `KV_CACHE_DTYPE=auto` and restarted the service.
- Post-revert validation: smoke passed; long-context recall passed; GSM8K tiny arithmetic remains the only known regression failure.
- Decision: do not keep FP8 KV for launch on this model/GPU without calibrated KV scales and a stronger quality pass.
- Posted final checkpoint for this pass to Slack channel `temp-llm-adv-test`.

## Command / Benchmark Notes

- Model storage created at `/home/adam/llm-models`.
- Direct I/O storage benchmark at model path: write about `4.4 GB/s`, read about `7.1 GB/s`.
- NVIDIA container runtime verified with `nvidia/cuda:13.0.0-base-ubuntu24.04`.

---

## Phase 2 — llama.cpp two-tier migration

### 2026-05-07T19:18Z — Resumed in a new session (Claude)

- Picked up the deployment after Codex's vLLM phase closed out at `2026-05-07T02:55Z`.
- Found `local-llm-vllm` container in `Exited (128) 8h ago` (clean shutdown, not a crash).
- `nvidia-smi` failed: kernel had been upgraded `6.8.0-110-generic` → `6.8.0-111-generic`,
  and `nvidia-driver-580-open` had no DKMS, so no kernel modules existed for the new kernel.
- Confirmed `Qwen/Qwen3.5-{4B,9B}` and `unsloth/Qwen3.5-{4B,9B}-GGUF` exist on HF.
- Slack DM to Adam summarizing current state, blocker, and proposed two-tier swap. Approved
  via permission hook after recipient/content review.

### 2026-05-07T19:25Z — Driver fix

- Adam ran `sudo apt install --reinstall nvidia-driver-580-open` (security update bumped
  driver to `580.142`), then rebooted. `nvidia-smi` healthy: 10240 MiB total, 1 MiB used,
  29 °C idle, kernel `6.8.0-111-generic`.
- Removed exited `local-llm-vllm` container with `docker rm -f`.

### 2026-05-07T19:30Z — Repo extraction → `~/local-llmops`

- Created `/home/adam/local-llmops` private repo skeleton (per Adam's request) and moved
  all Codex-era artifacts into it:
  - `docs/{decision,research,hardware,DEPLOYMENT_LOG}.md` (this file).
  - `bench/{regression.py,run_scenario.sh,run_vllm_bench.sh,smoke.py,tool_trajectory.py,results.md}`.
  - `archive/vllm/{docker-compose.yml,.env.example,README.md,status.sh}`.
- Stale `~/bench/agent-smoke` (root-owned aider cache) parked under `archive/vllm/bench-stale/`.
- Old vLLM benchmark JSON output left untouched in `/home/adam/llm-models/`.

### 2026-05-07T19:35Z — New stack staged

- `docker-compose.yml`: two services `exec` (Qwen3.5-4B GGUF UD-Q4_K_XL on `:8080`) and
  `smart` (Qwen3.5-9B GGUF UD-Q4_K_XL on `:8081`), both via
  `ghcr.io/ggml-org/llama.cpp:server-cuda`. Profiles `default`, `smart`, `both` so the 9B
  can be brought up on demand instead of fighting the 4B for VRAM at boot.
- Both services bind to Tailscale IPv4 only (`${LLM_BIND_HOST}=100.114.124.62`),
  preserving the security posture of the prior deployment.
- Shared volume `llamacpp-cache` for HF GGUF caching across both containers.
- KV cache type `q8_0` for both; documented fallback ladder (ctx → KV q4 → partial offload).
- Router scaffold under `router/`: `server.py` (FastAPI :8090 forwarder with route-aware
  sampling, schema-constrained `AgentDecision`, single-retry on invalid JSON),
  `schema.py` (canonical schema + Codex packet section validator), `prompts.py`
  (exec/smart/chat system prompts), `codex_packet.py` (packet builder + validator).
- Tests under `tests/`: `smoke_exec.py`, `smoke_smart.py`, `agent_decision_schema.py`
  (5-run schema regression per tier).
- New `status.sh` probes both `/health`, `/v1/models`, and `/props`; drops the
  vLLM-specific Prometheus scraping.
- Wrote `docs/architecture.md` (tier roles, VRAM budget with fallback ladder) and
  `docs/routing-policy.md` (exec→smart→Codex rules + Codex packet shape).
