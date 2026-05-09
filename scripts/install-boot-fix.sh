#!/usr/bin/env bash
# Install a systemd unit that brings up the exec tier *after* tailscaled.
#
# Without this, Docker's daemon often races Tailscale at boot and silently
# fails to bind 100.114.124.62:8080 ("cannot assign requested address"). The
# container reports healthy via its internal /health check, but no Tailscale
# client can reach it.
#
# The installed unit is a oneshot that:
#   1. compose-downs any stale containers from the failed boot attempt
#   2. compose-ups exec (fresh container + correct port binding) after
#      tailscaled.service and network-online.target are ready
#
# Run this once with sudo. Idempotent.

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "re-running with sudo..."
  exec sudo -E bash "$0" "$@"
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_ACCT="${SUDO_USER:-adam}"
USER_GROUP="$(id -gn "$USER_ACCT")"
UNIT_PATH="/etc/systemd/system/local-llmops.service"

DOCKER_BIN="$(command -v docker)"
if [[ -z "$DOCKER_BIN" ]]; then
  echo "ERROR: docker not on PATH"
  exit 1
fi

echo "writing $UNIT_PATH"
cat >"$UNIT_PATH" <<UNIT
[Unit]
Description=local-llmops two-tier llama.cpp stack (exec tier)
After=docker.service tailscaled.service network-online.target
Wants=docker.service tailscaled.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$USER_ACCT
Group=$USER_GROUP
WorkingDirectory=$REPO
# Clean up any half-bound containers from the boot race, then recreate exec
ExecStartPre=-$DOCKER_BIN compose -f $REPO/docker-compose.yml down --remove-orphans
ExecStart=$DOCKER_BIN compose -f $REPO/docker-compose.yml --profile default up -d exec
ExecStop=$DOCKER_BIN compose -f $REPO/docker-compose.yml down

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable local-llmops.service
echo "enabled local-llmops.service — exec will start automatically after tailscaled on every boot"
echo
echo "to test without rebooting:"
echo "  sudo systemctl start local-llmops.service"
echo "  ./status.sh"
echo
echo "smart is intentionally not in the unit; bring it up on demand with"
echo "  ./scripts/use-smart.sh"
