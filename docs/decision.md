# Architecture Decision Record

Date: `2026-05-07`

## Decision

Deploy a vLLM OpenAI-compatible server on the single RTX 3080 10 GiB using:

- Primary model: `Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4`
- Served model name: `qwen2.5-coder-7b`
- Engine: `vllm/vllm-openai:v0.20.1-cu129-ubuntu2404`
- Quantization: official GPTQ Int4, prefer GPTQ Marlin kernels; fall back to GPTQ if Marlin fails
- Precision: FP16 activations and FP16 KV cache for baseline quality
- Context target: 32K launch target
- Tool parser: Hermes-style vLLM parser for Qwen2.5
- Launch optimizations: prefix caching and chunked prefill
- Network bind: Tailscale IPv4 `100.114.124.62` only

## Rationale

This host has only one GPU and 10 GiB VRAM. Long-context inference is dominated by KV cache, not just model weights. Qwen2.5-Coder-7B has a much smaller KV footprint than Qwen3-8B because it has 28 layers and 4 KV heads, while Qwen3-8B has 36 layers and 8 KV heads. That matters more than the small parameter-count difference.

Qwen2.5-Coder-7B is also dense, Apache-2.0, code-tuned, available in official GPTQ Int4 weights, and documented as long-context/code-agent capable. vLLM gives the best launch-day OpenAI-compatible API, streaming support, continuous batching, and tool-call parser stack.

## VRAM Math

For Qwen2.5-Coder-7B:

- Parameters: 7.61B
- Layers: 28
- Attention heads: 28 Q heads, 4 KV heads
- Head dim: 128
- KV cache per token at FP16:
  - `2` tensors (K,V) × `28` layers × `4` KV heads × `128` head dim × `2` bytes
  - `57,344 bytes/token`, about `56 KiB/token`
- 32,768-token KV cache:
  - `57,344 × 32,768 = 1,879,048,192 bytes`
  - about `1.75 GiB` per full 32K sequence

Estimated memory budget:

- GPTQ Int4 weights: about `4.0-4.8 GiB`
- Runtime/kernel/metadata overhead: about `0.8-1.4 GiB`
- Activations/scheduler/CUDA graphs/fragmentation: about `0.8-1.2 GiB`
- One full 32K FP16 KV sequence: about `1.75 GiB`
- Practical remaining KV budget on 10 GiB after driver reservation: about `2.0-3.0 GiB`, depending vLLM load overhead and quant kernel path

Concurrency implication:

- One full 32K agent trajectory should fit if vLLM overhead stays inside budget.
- Four concurrent agents can fit when their active contexts average below full 32K, especially with chunked prefill and prefix caching.
- Four simultaneous 32K prompts cannot fit with FP16 KV on this card.
- FP8 KV would cut KV to about `0.875 GiB` per 32K sequence, but the launch experiment failed long-context recall and was reverted to FP16/auto KV.

## Parallelism Strategy

- Tensor parallelism: none (`tp=1`)
- Pipeline parallelism: none
- Heterogeneous GPU handling: not applicable
- Draft-model GPU: none
- Do not add CPU offload at launch; it increases latency and operational variance.

## Launch Optimizations

- `--enable-prefix-caching`
- `--enable-chunked-prefill`
- Conservative `--max-num-batched-tokens` initially
- Conservative `--max-num-seqs` initially
- Docker restart policy
- Healthcheck and status script
- Tailscale-only bind

## Deferred Experiments

- INT4/KIVI/TurboQuant-style KV cache
- Speculative decoding with small draft model
- EAGLE/MTP variants
- SGLang Qwen3.5-9B path if vLLM and model support prove stable enough later
- llama.cpp GGUF with KV q8/q4 if vLLM cannot satisfy context/concurrency on 10 GiB

## Rejected Experiments

- FP8 KV cache (`fp8_e5m2`): vLLM started and reported `71,648` KV tokens, but the regression suite failed long-context recall. Reverted to `KV_CACHE_DTYPE=auto`, which reports `42,912` KV tokens and passes long-context recall.

## Fallback Configuration

Fallback model:

- `Qwen/Qwen2.5-Coder-7B-Instruct-GGUF` or a reputable Q4_K_M/Q5_K_M GGUF quant of the same model.

Fallback engine:

- `llama.cpp` / `llama-server` with CUDA.

Degraded mode:

- Reduce `MAX_MODEL_LEN` to `16384`.
- Keep FP16 KV for tool-call quality if possible.
- If concurrency is more important than long context, cap context at 16K and raise parallel slots.
- If long context is more important than quality-sensitive tools, test KV q8 first, then q4 only after regression suite passes.
