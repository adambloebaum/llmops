#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/.env"

mkdir -p "$ROOT/bench/artifacts"

for concurrency in 1 4 8 16; do
  docker exec local-llm-vllm vllm bench serve \
    --backend openai-chat \
    --base-url "http://127.0.0.1:8000" \
    --endpoint /v1/chat/completions \
    --model "$SERVED_MODEL_NAME" \
    --tokenizer "$MODEL_ID" \
    --dataset-name random \
    --random-input-len 512 \
    --random-output-len 128 \
    --num-prompts $((concurrency * 8)) \
    --request-rate inf \
    --max-concurrency "$concurrency" \
    --temperature 0 \
    --save-result \
    --result-filename "/models/bench_random_c${concurrency}.json" \
    2>&1 | tee "$ROOT/bench/artifacts/random_c${concurrency}.log"
done
