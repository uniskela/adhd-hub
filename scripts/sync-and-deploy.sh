#!/usr/bin/env bash
# Sync this tree to a Docker host and bring the stack up.
# Usage:
#   ./scripts/sync-and-deploy.sh root@100.115.187.7 /opt/adhd-hub
set -euo pipefail

HOST="${1:?usage: $0 user@host [remote_dir]}"
REMOTE_DIR="${2:-/opt/adhd-hub}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Syncing $ROOT -> ${HOST}:${REMOTE_DIR}"
ssh "$HOST" "mkdir -p '$REMOTE_DIR'"
rsync -az --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'data' \
  --exclude '__pycache__' \
  --exclude '.env' \
  --exclude 'graphify-out' \
  "$ROOT/" "${HOST}:${REMOTE_DIR}/"

ssh "$HOST" "bash -s" <<EOF
set -euo pipefail
cd '$REMOTE_DIR'
if [[ ! -f .env ]]; then
  cp .env.example .env
  TOKEN=\$(openssl rand -hex 32)
  if grep -q '^ADHD_HUB_AUTH_TOKEN=' .env; then
    sed -i "s/^ADHD_HUB_AUTH_TOKEN=.*/ADHD_HUB_AUTH_TOKEN=\${TOKEN}/" .env
  else
    echo "ADHD_HUB_AUTH_TOKEN=\${TOKEN}" >> .env
  fi
  echo "Created .env with generated ADHD_HUB_AUTH_TOKEN"
  echo "TOKEN=\${TOKEN}"
fi
if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    docker compose up -d --build
  else
    docker-compose up -d --build
  fi
else
  echo "docker not found on remote" >&2
  exit 1
fi
sleep 2
curl -sf http://127.0.0.1:8787/api/health
echo
echo "Done. Point MCP at http://<tailscale-ip>:8787/mcp"
EOF
