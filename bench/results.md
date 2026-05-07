# Benchmark Results

Collected: `2026-05-07`

Endpoint: `http://100.114.124.62:8000/v1`
Model: `qwen2.5-coder-7b`
Engine: `vllm/vllm-openai:v0.20.1-cu129-ubuntu2404`
Scenario completed: random 512-token input / 128-token output, OpenAI chat endpoint.

## Baseline Random 512 In / 128 Out

| Max concurrency | Requests | Failures | Duration s | Req/s | Output tok/s | Total tok/s | Mean TTFT ms | P99 TTFT ms | Mean TPOT ms | Mean ITL ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 0 | 8.94 | 0.89 | 114.54 | 598.68 | 138.06 | 178.66 | 7.71 | 8.37 |
| 4 | 32 | 0 | 11.05 | 2.89 | 370.51 | 1936.50 | 302.15 | 476.34 | 8.50 | 8.98 |
| 8 | 64 | 0 | 20.32 | 3.15 | 403.21 | 2107.39 | 1380.34 | 1951.42 | 8.40 | 9.00 |
| 16 | 128 | 0 | 40.74 | 3.14 | 402.13 | 2101.78 | 3710.56 | 4861.59 | 8.72 | 9.27 |

Interpretation:

- Throughput saturates around concurrency 8 at about `400 output tok/s`.
- Decode speed remains stable as concurrency rises; TPOT stays around `8-9 ms`.
- TTFT rises sharply past concurrency 4, which is expected on this 10 GiB card with limited KV budget and bursty prefill contention.
- No failed requests were observed in this baseline benchmark.

## Long-In / Short-Out: Random 4096 In / 128 Out

| Max concurrency | Requests | Failures | Duration s | Req/s | Output tok/s | Total tok/s | Mean TTFT ms | P99 TTFT ms | Mean TPOT ms | Mean ITL ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 0 | 4.01 | 0.50 | 63.92 | 2123.68 | 994.88 | 1014.43 | 7.93 | 11.38 |
| 4 | 8 | 0 | 8.18 | 0.98 | 125.14 | 4157.82 | 2305.60 | 3831.50 | 14.01 | 15.64 |
| 8 | 16 | 0 | 12.45 | 1.28 | 164.45 | 5463.97 | 3448.43 | 8745.76 | 13.46 | 15.63 |
| 16 | 32 | 0 | 40.06 | 0.80 | 102.24 | 3396.97 | 13651.12 | 18808.95 | 23.33 | 27.73 |

Interpretation: long prefill is the bottleneck. Concurrency 16 is stable but not latency-friendly for 4K-input agent traffic; c4-c8 is the practical burst range for long-in/short-out workloads.

## Long-In / Long-Out: Random 4096 In / 512 Out

| Max concurrency | Requests | Failures | Duration s | Req/s | Output tok/s | Total tok/s | Mean TTFT ms | P99 TTFT ms | Mean TPOT ms | Mean ITL ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 0 | 5.15 | 0.19 | 99.33 | 899.61 | 1008.46 | 1008.46 | 8.11 | 15.35 |
| 4 | 4 | 0 | 7.78 | 0.51 | 263.10 | 2382.81 | 1989.87 | 2964.33 | 11.31 | 16.57 |
| 8 | 8 | 0 | 13.63 | 0.59 | 300.54 | 2721.87 | 4816.12 | 8806.48 | 9.69 | 16.68 |
| 16 | 16 | 0 | 27.32 | 0.59 | 299.87 | 2715.86 | 9854.54 | 22479.90 | 11.22 | 18.09 |

Interpretation: sustained decode remains healthy near `300 output tok/s` at c8-c16, but TTFT becomes high under c16 long-prompt bursts.

## Tool-Calling Trajectory

Forced OpenAI-style tool-call requests were issued concurrently with JSON argument validation on every response.

| Max concurrency | Requests | Passed | Failed | Duration s | Req/s | Mean latency s | P95 latency s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 4 | 0 | 0.75 | 5.35 | 0.19 | 0.27 |
| 4 | 16 | 16 | 0 | 1.06 | 15.05 | 0.26 | 0.53 |
| 8 | 32 | 32 | 0 | 1.54 | 20.80 | 0.36 | 0.53 |
| 16 | 64 | 64 | 0 | 2.72 | 23.55 | 0.62 | 0.68 |

## Endpoint / Quality Validation

Smoke suite:

- `/v1/models`: pass
- `/v1/chat/completions`: pass
- streaming: pass
- forced OpenAI-style tool call: pass

Regression suite:

| Check | Result | Note |
| --- | --- | --- |
| BFCL-style forced tool call | Pass | Returned `tool_calls` with JSON string arguments |
| JSON mode | Pass | Returned parseable JSON with expected field |
| Aider-style unified diff | Pass | Produced diff markers and corrected text |
| GSM8K tiny arithmetic | Fail | Returned `33`; expected `31` |
| Long-context recall | Pass | Recalled needle within calibrated long prompt |

The arithmetic failure is a baseline model-quality caveat. It is not caused by an optimization experiment because launch baseline uses FP16 KV (`KV_CACHE_DTYPE=auto`) and no speculative decoding.

## Agentic Workflow Validation

Aider was run in an isolated `python:3.12-slim` Docker container against the OpenAI-compatible endpoint. The first attempt targeted `127.0.0.1:8000` and failed because the server is intentionally bound only to the Tailscale IPv4 address.

The retry used `http://100.114.124.62:8000/v1` and succeeded:

- Tool: `aider-chat` `v0.86.2`
- Model setting: `openai/qwen2.5-coder-7b`
- Test repo: `bench/agent-smoke`
- Task: fix `calc.py` so `add(a, b)` returns `a + b`
- Result: Aider generated a SEARCH/REPLACE block, applied it to `calc.py`, and `python3 bench/agent-smoke/calc.py` printed `5`.

## Thermal / Power

Telemetry file: `bench/artifacts/gpu_baseline_random.csv`
Additional long-scenario telemetry file: `bench/artifacts/gpu_long_scenarios.csv`

- Samples: `120`
- Max GPU temp: `66 C`
- Max GPU power draw: `319.23 W`
- Max GPU utilization: `100%`
- Max GPU memory observed: `8971 MiB / 10240 MiB`
- Long-scenario telemetry samples: `88`
- Long-scenario max GPU temp: `68 C`
- Long-scenario max GPU power draw: `319.30 W`

Thermals were stable during the completed baseline run. Peak power reached the configured RTX 3080 board limit, so future sustained overnight benchmarking should keep this CSV capture enabled and should avoid raising GPU power limits.

## Artifacts

- `bench/artifacts/random_c1.log`
- `bench/artifacts/random_c4.log`
- `bench/artifacts/random_c8.log`
- `bench/artifacts/random_c16.log`
- `bench/artifacts/long_short_4096_128_c1.log`
- `bench/artifacts/long_short_4096_128_c4.log`
- `bench/artifacts/long_short_4096_128_c8.log`
- `bench/artifacts/long_short_4096_128_c16.log`
- `bench/artifacts/long_long_4096_512_c1.log`
- `bench/artifacts/long_long_4096_512_c4.log`
- `bench/artifacts/long_long_4096_512_c8.log`
- `bench/artifacts/long_long_4096_512_c16.log`
- `bench/artifacts/gpu_baseline_random.csv`
- `bench/artifacts/gpu_long_scenarios.csv`
- `bench/artifacts/tool_trajectory.json`
- `/home/adam/llm-models/bench_random_c1.json`
- `/home/adam/llm-models/bench_random_c4.json`
- `/home/adam/llm-models/bench_random_c8.json`
- `/home/adam/llm-models/bench_random_c16.json`
- `/home/adam/llm-models/bench_long_short_4096_128_c1.json`
- `/home/adam/llm-models/bench_long_short_4096_128_c4.json`
- `/home/adam/llm-models/bench_long_short_4096_128_c8.json`
- `/home/adam/llm-models/bench_long_short_4096_128_c16.json`
- `/home/adam/llm-models/bench_long_long_4096_512_c1.json`
- `/home/adam/llm-models/bench_long_long_4096_512_c4.json`
- `/home/adam/llm-models/bench_long_long_4096_512_c8.json`
- `/home/adam/llm-models/bench_long_long_4096_512_c16.json`

## Pending

- lower context mode benchmark for latency-focused profiles
- alternate engine fallback only if vLLM becomes unstable

## Rejected Optimizations

| Optimization | Result | Reason |
| --- | --- | --- |
| FP8 KV cache (`fp8_e5m2`) | Rejected | Increased reported KV capacity from `42,912` to `71,648` tokens, but failed long-context recall regression. Reverted to `KV_CACHE_DTYPE=auto`. |
