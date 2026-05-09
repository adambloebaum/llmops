#!/usr/bin/env bash
# Manual fix when Docker raced Tailscale at boot and exec is "healthy" but
# unreachable on 100.114.124.62:8080. Force-recreates the container so the
# port binding actually engages now that Tailscale is up.
#
# Use scripts/install-boot-fix.sh once to make this automatic on future boots.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "recreating containers (any half-bound ones from boot race will be replaced)..."
docker compose down --remove-orphans >/dev/null 2>&1 || true
docker compose --profile default up -d exec
echo
echo "exec recreated. status:"
docker compose ps
