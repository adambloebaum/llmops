# Current Landscape Research

Collected: `2026-05-07`

Primary constraint from `hardware.md`: one RTX 3080 with 10 GiB VRAM. This rules out launch-day dense models above the 7B-9B INT4/GGUF class for 32K context, and it rules out MoE/routed models by mission requirement.

## Sources

- vLLM tool calling docs: https://docs.vllm.ai/en/stable/features/tool_calling/
- vLLM repository / feature overview: https://github.com/vllm-project/vllm
- SGLang docs: https://docs.sglang.io/
- TensorRT-LLM docs: https://nvidia.github.io/TensorRT-LLM/
- llama.cpp server docs: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- TabbyAPI: https://github.com/theroyallab/tabbyAPI/
- Hugging Face TGI docs: https://huggingface.co/docs/text-generation-inference/en/index
- LMDeploy docs: https://lmdeploy.readthedocs.io/
- Aphrodite docs: https://aphrodite.pygmalion.chat/
- MLC LLM docs: https://llm.mlc.ai/docs/
- Qwen2.5-Coder-7B-Instruct: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct
- Qwen2.5-Coder-7B-Instruct-GPTQ-Int4: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4
- Qwen3-8B: https://huggingface.co/Qwen/Qwen3-8B
- Qwen3.5-9B: https://huggingface.co/Qwen/Qwen3.5-9B
- BFCL V4 leaderboard: https://gorilla.cs.berkeley.edu/leaderboard
- OpenAI gpt-oss overview: https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss

## Inference Engine Evaluation

| Engine | OpenAI API | Streaming | Tool Calls / JSON | Batching / Prefill | KV Quant | Multi-GPU | Quant Formats | Operational Fit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vLLM | Strong `/v1` server | Yes | Strongest launch fit. Named/required tool calling uses structured outputs; auto tool choice uses parsers. Qwen2.5 uses Hermes-style parser. Strict mode accepted but not enforced in auto mode. | Continuous batching, prefix caching, chunked prefill, paged attention | FP8 KV supported; INT4/TurboQuant more experimental/plugin-class | TP/PP/data parallel; best on matched GPUs | FP16/BF16, FP8, GPTQ, AWQ, GPTQ/AWQ Marlin, GGUF, bitsandbytes, INT4 W4A16, compressed-tensors | Best production baseline for OpenAI-compatible agent workloads if model fits VRAM |
| SGLang | Strong `/v1` server | Yes | Strong, especially Qwen3/Qwen3.5 parser support and structured outputs | Continuous batching, RadixAttention prefix caching, chunked prefill, FlashInfer | FP8 and INT4-family support depending backend/model | TP/PP/DP and advanced routing | FP16/BF16, FP8, AWQ, GPTQ, INT4 | Excellent but more moving parts; Qwen3.5 support is attractive, but 10 GB VRAM limits launch use |
| TensorRT-LLM | OpenAI-like server through Triton/NIM patterns | Yes | Capable but less simple for local agent integration | Very high performance, inflight batching, paged KV, speculative decoding | FP8 and lower precision support strongest on newer NVIDIA GPUs | Excellent on datacenter matched GPUs | FP16/BF16, FP8, INT8/INT4, AWQ/GPTQ paths | Too complex for this single-GPU overnight deployment |
| llama.cpp / llama-server | OpenAI-compatible chat/completions | Yes | Supports JSON/schema and OpenAI-style function calling with correct Jinja templates; tool parsing has more template/model edge cases | Slots/parallelism, prompt cache, speculative decoding; not vLLM-class continuous batching | Mature GGUF KV quant options such as q8/q4 | Multi-GPU layer split; heterogeneous friendly | GGUF, many K/IQ quants | Best fallback on 10 GB if vLLM cannot fit; lower dependency surface |
| ExLlamaV2 + TabbyAPI | OpenAI-compatible via TabbyAPI | Yes | OAI-style function calling, JSON schema/regex/EBNF support | Async concurrent inference; optimized single-user EXL2 | EXL2 memory efficiency; KV options engine-specific | Tensor parallel exists but less production-standard | EXL2, GPTQ, FP16 | Good fallback for EXL2 speed; less standard for broad agent tooling than vLLM |
| TGI | OpenAI-compatible | Yes | Guidance/tools/JSON schema support | Continuous batching, paged attention, flash attention | Limited relative to vLLM/SGLang | Tensor parallel | bitsandbytes, GPTQ, safetensors | Not selected because upstream docs say TGI is in maintenance mode |
| LMDeploy | OpenAI-compatible server | Yes | Usable; strongest around TurboMind-supported model families | Paged attention, prefix caching, chunked prefill-like features | 4/8-bit KV cache in TurboMind with head-dim constraints | TP support | AWQ W4A16, FP16/BF16, limited GPTQ/GGUF | Worth testing later, but less universal for agent tools |
| Aphrodite | OpenAI API | Yes | Similar lineage to vLLM; supports structured serving features | Paged attention, batching | FP8 KV cache documented | Multi-GPU support | GPTQ, AWQ, FP8, GGUF, Marlin-class support varies | Smaller ecosystem; not launch pick over vLLM |
| MLC-LLM | OpenAI-compatible REST | Yes | Basic chat API; tool fidelity less proven for coding agents | Continuous batching and compiled deployment | Quantization-centric compiled artifacts | Tensor parallel shards | MLC q4f16/q3f16/q0f16, etc. | More build/compile complexity than desired |

## Model Research

Mission restriction: no MoE, no routed architectures, no sparse expert stacks.

### Dense Candidates

| Model | Params | Context | Tool / Agent Notes | Formats | License | Fit on RTX 3080 10 GB |
| --- | ---: | ---: | --- | --- | --- | --- |
| Qwen2.5-Coder-7B-Instruct | 7.61B | 131K advertised | Code-tuned; Qwen card explicitly targets code agents; vLLM docs say Qwen2.5 tool template supports Hermes-style tool use | FP16/BF16, official GPTQ Int4/Int8, GGUF variants | Apache-2.0 | Best launch candidate with GPTQ Int4. KV is small due 4 KV heads |
| Qwen3-8B | 8.2B | 32K native, 131K YaRN | Stronger general reasoning and agent claims than Qwen2.5; thinking mode adds complexity for tool streams | FP16/BF16, AWQ/FP8/GGUF variants | Apache-2.0 | Possible in INT4/GGUF, but KV cache is ~2.6x larger than Qwen2.5-Coder-7B due 36 layers and 8 KV heads |
| Qwen3.5-9B | 9B | 262K native | Current Qwen card provides vLLM/SGLang commands with `qwen3_coder` tool parser; strong native tool-call positioning | BF16 first-party, community GGUF | Apache-2.0 | Not launch-day fit in vLLM on 10 GB; community GGUF possible fallback after llama.cpp validation |
| Llama 3.1/3.2/3.3 8B class | ~8B | up to 128K on 3.1 | Good ecosystem, weaker coding/tool-use than Qwen coder line at this size | FP16, GPTQ/AWQ/GGUF | Meta Llama license | Viable fallback, not best for coding agents |
| DeepSeek Coder 6.7B / 7B dense line | ~7B | model-dependent | Historically strong coding; older context/tool-call stack than Qwen2.5/Qwen3 | FP16/GGUF/GPTQ community | DeepSeek license varies | Fallback only |
| Mistral 7B / Devstral Small 24B dense | 7B / 24B | 32K to 256K depending model | Devstral is agentic-coding focused but too large for 10 GB at useful context | FP16, GGUF, quant variants | Apache-2.0 for Devstral Small | 7B Mistral fallback; Devstral 24B not launch fit |
| Granite 8B / Granite code models | ~8B | long-context variants exist | vLLM has Granite parsers; IBM emphasizes tool calling in newer Granite releases | FP16, GGUF, quant variants | Apache-2.0 or IBM open licenses by model | Viable fallback if Qwen tool quality disappoints |
| Gemma dense small models | 2B/4B/27B/31B classes by generation | model-dependent | Newer Gemma tool-calling claims are attractive, but larger dense variants exceed 10 GB at 32K | FP16/GGUF | Gemma terms | Small fallback only |

### Rejected By Architecture

- Llama 4 Scout/Maverick: MoE/routed architecture.
- DeepSeek V3/V4/V3.2-style models: MoE/routed architecture.
- Qwen3-Coder-Next and Qwen3-Coder large variants: MoE/routed architecture.
- Qwen3.5 35B-A3B, 122B-A10B, 397B-A17B: MoE/routed architecture.
- gpt-oss-20B / gpt-oss-120B: open-weight and strong tool-use positioning, but MoE. Also 20B target memory is above this card for comfortable 32K concurrent serving.
- GLM Flash / modern Flash variants with active experts: MoE/routed architecture.

## Optimization Techniques

| Technique | Expected Gain | Compatibility / Risk | Launch Decision |
| --- | --- | --- | --- |
| Prefix caching | Large TTFT gains when system prompt/tool schemas repeat | Works best with stable prefixes; vLLM/SGLang mature | Enable at launch |
| Chunked prefill | Better interactivity under long prompts/concurrency | Mature in vLLM/SGLang; tune max batched tokens | Enable at launch |
| FP8 KV cache | Roughly halves KV memory, enabling more total context | Accuracy risk in tool-call tokens; better on newer GPUs; must regression-test | Deferred experiment |
| INT4 KV / KIVI-style | Larger context gain than FP8 | Less mature in vLLM; llama.cpp GGUF KV quant more mature but tool quality must be tested | Deferred/fallback experiment |
| TurboQuant-style KV | Promising KV compression reports | Plugin/rapidly changing; not baseline production | Deferred |
| Speculative decoding | Can improve decode throughput if draft model accepts well | More VRAM and operational complexity; draft model reduces available KV on 10 GB | Deferred |
| Medusa | Can improve decode with trained heads | Requires compatible model/head; TGI has docs but maintenance mode | Deferred |
| EAGLE-2 / EAGLE-3 | Strong speedups when supported | Needs compatible draft/head and extra memory | Deferred |
| FlashAttention-3 | Excellent on Hopper/Blackwell class; not primary RTX 3080 path | Ampere uses FlashAttention/FlashInfer variants, not FA3 advantage | Not launch blocker |
| FlashInfer | Strong in SGLang/vLLM paths | Backend compatibility varies | Use if selected engine enables it by default/stably |
| Marlin / Machete | Major INT4 throughput improvement | Marlin is mature for GPTQ/AWQ on Ampere; Machete varies by engine | Use GPTQ Marlin if vLLM loads; otherwise fall back to GPTQ |

## Research Conclusion

Launch baseline should favor vLLM with the official Qwen2.5-Coder-7B GPTQ Int4 checkpoint. This gives the best balance of OpenAI compatibility, tool parser support, continuous batching, and a KV cache small enough to attempt 32K context on 10 GiB VRAM.

Fallback if vLLM fails to load or cannot keep stable 32K context: llama.cpp `llama-server` with official/community GGUF of the same model, using Q5_K_M or Q4_K_M plus conservative KV quantization and explicit Jinja/tool-call validation.
