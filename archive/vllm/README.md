# Local LLM Inference Server

OpenAI-compatible local inference endpoint for agentic tools.

## Endpoint

- Base URL: `http://100.114.124.62:8000/v1`
- Model: `qwen2.5-coder-7b`
- Engine: vLLM
- Bind scope: Tailscale IPv4 only

## Operations

```bash
docker compose up -d
./status.sh
docker compose logs -f llm
docker compose restart llm
docker compose down
```

Configuration lives in `.env`. Model/cache storage is under `LLM_MODEL_STORAGE`, currently `/home/adam/llm-models`.

The Docker service uses `restart: unless-stopped`, so it is reboot-persistent as long as Docker starts normally.

## Client Configuration

Use OpenAI-compatible settings:

- Base URL: `http://100.114.124.62:8000/v1`
- API key: any non-empty value if the client requires one
- Model: `qwen2.5-coder-7b`

Validated client behavior:

- `/v1/models`
- `/v1/chat/completions`
- streaming chat completions
- forced OpenAI-style tool calls
- long-context recall within the configured 32K limit
- Aider edit on a throwaway repo using `--model openai/qwen2.5-coder-7b`

Known caveat: the current 7B INT4 baseline failed one tiny GSM8K arithmetic regression (`33` vs expected `31`). Tool calling, JSON mode, diff generation, and long-context recall passed.

Do not enable FP8 KV for this launch profile. It raised reported KV capacity but failed the long-context recall regression and was reverted to `KV_CACHE_DTYPE=auto`.

## Benchmarks

Baseline random 512-token input / 128-token output saturates around concurrency 8:

- Concurrency 1: `114.54` output tok/s, mean TTFT `138.06 ms`
- Concurrency 4: `370.51` output tok/s, mean TTFT `302.15 ms`
- Concurrency 8: `403.21` output tok/s, mean TTFT `1380.34 ms`
- Concurrency 16: `402.13` output tok/s, mean TTFT `3710.56 ms`

Long 4096-token input tests were stable with zero failed requests. Practical guidance: c4-c8 is the better range for long-context agent traffic; c16 works but mean TTFT reached `13.65 s` for 4096-in/128-out and `9.85 s` for 4096-in/512-out.

Forced tool-call trajectory testing passed `116/116` requests across c1/c4/c8/c16.

Full details are in `bench/results.md`.

## Files

- `hardware.md`: verified hardware inventory
- `research.md`: engine/model/optimization research
- `decision.md`: architecture decision record and VRAM math
- `docker-compose.yml`: deployment
- `bench/`: reproducible smoke, regression, and benchmark scripts
- `DEPLOYMENT_LOG.md`: ongoing deployment log
- `status.sh`: health, GPU, and recent log summary
