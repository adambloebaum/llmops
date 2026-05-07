#!/usr/bin/env bash
# Activate the smart tier (Qwen3.5-9B). Stops exec to free VRAM.
# Use when escalation rules in routing-policy.md fire.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose stop exec >/dev/null 2>&1 || true
docker compose --profile smart up -d smart
echo "[ok] smart active on \${LLM_BIND_HOST}:\${SMART_PORT}"
