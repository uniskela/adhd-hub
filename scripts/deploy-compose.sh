#!/usr/bin/env bash
# Copy this repo onto a Tailscale-connected Docker host and run:
#   ./scripts/deploy-compose.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — edit ADHD_HUB_AUTH_TOKEN (and OpenClaw URLs) before relying on this."
fi
docker compose up -d --build
sleep 2
curl -sf "http://127.0.0.1:8787/api/health" | tee /dev/stderr
echo
echo "MCP: http://$(hostname -I 2>/dev/null | awk '{print $1}'):8787/mcp  (prefer Tailscale IP)"
