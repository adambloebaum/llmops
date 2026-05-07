# Architecture

## Goal

Move execution-adjacent agent work onto the local RTX 3080 to reduce
Codex/cloud-token spend, while keeping cloud reasoning available behind a
compressed-context handoff.

## Stack

```
agentic CLI / harness
        |
        v
  local-agent-router  (router/, optional)
        |
        |-- :8080 /v1   local-qwen-exec   -> Qwen3.5-4B  UD-Q4_K_XL
        |
        '-- :8081 /v1   local-qwen-smart  -> Qwen3.5-9B  UD-Q4_K_XL
                                             (escalate to Codex from here)
```

The router (when running) owns model selection, system-prompt injection,
sampling, schema enforcement, and Codex packet construction. The harness
owns tool execution.

## Why two tiers

A single 7-9B model is either too weak for hard reasoning or too slow for
tight tool loops. Splitting them lets:

- the 4B run hot for the high-frequency, low-ambiguity loop work
  (parsing test output, picking the next inspection command, summarizing logs)
- the 9B handle the stuff where 4B's confidence drops off (multi-file plans,
  ambiguous failures, packet quality review)
- cloud Codex stay on a strict diet of pre-compressed packets

## Why llama.cpp not vLLM

The original deployment used vLLM with `Qwen2.5-Coder-7B-Instruct-GPTQ-Int4`.
That stack worked but only ever fit one model on this card. llama.cpp's
`server-cuda` image:

- runs GGUF natively (UD-Q4_K_XL is the dynamic-2.0 quant we want)
- supports schema-constrained JSON via `response_format`
- exposes `--cache-type-k q8_0`/`q4_0` for KV quantization without the
  long-context-recall regressions we saw on FP8 KV under vLLM
- is small enough at runtime to run a second container alongside

The vLLM stack (preserved under `archive/vllm/`) is a working fallback if
the workload ever shifts toward higher concurrency on a bigger GPU.

## Schema-constrained outputs

llama.cpp's server expects the OpenAI structured-outputs envelope, not a flat
schema:

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "AgentDecision",
      "strict": true,
      "schema": { ... }
    }
  }
}
```

Sending `{"type": "json_schema", "schema": ...}` (the simpler form some
inference servers accept) makes llama.cpp ignore the schema silently and
return whatever JSON the model felt like producing. The router and
`tests/agent_decision_schema.py` use the correct envelope.

## Generation defaults

Qwen3.5 enables thinking mode by default. For an execution agent, disable
thinking unless the route explicitly wants deep reasoning.

| Route             | temperature | top_p | top_k | max_tokens | enable_thinking |
| ----------------- | ----------: | ----: | ----: | ---------: | --------------- |
| exec              |        0.20 |  0.80 |    20 |       1024 | false           |
| smart             |        0.30 |  0.80 |    20 |       2048 | false           |
| smart_reasoning   |        0.60 |  0.95 |    20 |       4096 | true            |
| chat              |        0.70 |  0.80 |    20 |       2048 | false           |

Pass non-thinking via `chat_template_kwargs: {"enable_thinking": false}`.
`/think` and `/nothink` soft switches are not officially supported on Qwen3.5.

## VRAM budget

After driver reservation (~365 MiB), available is ~9.8 GiB.

| Component                           | Approx |
| ----------------------------------- | -----: |
| 4B UD-Q4_K_XL weights               | ~3.0 GiB |
| 4B 32K KV at q8_0                   | ~0.5 GiB |
| 4B runtime / scheduler              | ~0.7 GiB |
| 9B UD-Q4_K_XL weights               | ~6.0 GiB |
| 9B 16K KV at q8_0                   | ~0.6 GiB |
| 9B runtime / scheduler              | ~0.7 GiB |

Both tiers at full configured context simultaneously: ~11.5 GiB → OOM.

Mitigation order:

1. Run `exec` always-on, `smart` on demand (default).
2. `SMART_CTX_SIZE` 16384 → 8192.
3. `SMART_KV_TYPE` q8_0 → q4_0.
4. 9B `--n-gpu-layers 999` → partial offload.

## Bind / network posture

Both containers map host `${LLM_BIND_HOST}:{8080,8081}` (Tailscale IPv4) to
the container's `:8080`. There is no LAN listener, no public listener.
This matches the security posture of the prior vLLM deployment.

## Persistence

Weights cache in the Docker named volume `llamacpp-cache`, mounted at
`/root/.cache/llama.cpp` inside both containers. First boot of each tier
downloads the GGUF from HuggingFace; subsequent boots are seconds.

The original GPTQ weights for the vLLM era remain at
`/home/adam/llm-models/huggingface` and are not in the new cache.

## Out of scope (deliberately)

- Multi-user serving — single-developer agent loop only
- Fine-tuning
- Vision / video input
- 128K-262K local context (model card supports it; the GPU does not)
- Replacing Codex for cross-cutting refactor or unfamiliar repos
