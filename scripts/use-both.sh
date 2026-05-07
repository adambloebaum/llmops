#!/usr/bin/env bash
# EXPERIMENTAL: bring up both tiers simultaneously with reduced contexts.
# At default ctx (32K exec + 16K smart), the 10 GiB card OOMs and the
# late-starter segfaults (exit 139). This script overrides via env to
# fit both: exec 8K q8, smart 8K q4.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
EXEC_CTX_SIZE=8192 \
EXEC_KV_TYPE=q8_0 \
SMART_CTX_SIZE=8192 \
SMART_KV_TYPE=q4_0 \
docker compose --profile both up -d
echo "[ok] both tiers up at reduced contexts (exec 8K q8 + smart 8K q4)"
echo "If smart OOMs, drop SMART_CTX_SIZE further or use ./scripts/use-smart.sh."
