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
STACK_UNIT="/etc/systemd/system/local-llmops.service"
ROUTER_UNIT="/etc/systemd/system/local-llmops-router.service"

DOCKER_BIN="$(command -v docker)"
if [[ -z "$DOCKER_BIN" ]]; then
  echo "ERROR: docker not on PATH"
  exit 1
fi
PYTHON_BIN="$(command -v python3)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: python3 not on PATH"
  exit 1
fi

echo "writing $STACK_UNIT"
cat >"$STACK_UNIT" <<UNIT
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

echo "writing $ROUTER_UNIT"
cat >"$ROUTER_UNIT" <<UNIT
[Unit]
Description=local-agent-router (OpenAI-compat facade + telemetry on :8090)
After=local-llmops.service tailscaled.service network-online.target
Wants=local-llmops.service tailscaled.service network-online.target

[Service]
Type=simple
User=$USER_ACCT
Group=$USER_GROUP
WorkingDirectory=$REPO
EnvironmentFile=$REPO/.env
ExecStart=$PYTHON_BIN -m router.server
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/local-llmops-router.log
StandardError=append:/var/log/local-llmops-router.log

[Install]
WantedBy=multi-user.target
UNIT

# Make sure the router log file exists and is writable by the user
touch /var/log/local-llmops-router.log
chown "$USER_ACCT:$USER_GROUP" /var/log/local-llmops-router.log

systemctl daemon-reload
systemctl enable local-llmops.service local-llmops-router.service
echo
echo "enabled:"
echo "  local-llmops.service         — brings up exec after Docker + Tailscale + network-online"
echo "  local-llmops-router.service  — runs router on :8090 once exec is up"
echo
echo "to test without rebooting:"
echo "  sudo systemctl start local-llmops.service"
echo "  sudo systemctl start local-llmops-router.service"
echo "  ./status.sh"
echo "  curl -fsS http://100.114.124.62:8090/health"
echo
echo "smart is intentionally not in either unit; bring it up on demand with"
echo "  ./scripts/use-smart.sh"
