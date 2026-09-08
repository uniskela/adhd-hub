#!/usr/bin/env pwsh
# Sync + deploy adhd-hub to a Tailscale Docker host (Windows).
# Usage:
#   .\scripts\sync-and-deploy.ps1 -HostName root@100.115.187.7 -RemoteDir /opt/adhd-hub
param(
  [Parameter(Mandatory = $true)][string]$HostName,
  [string]$RemoteDir = "/opt/adhd-hub"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Write-Host "Syncing $Root -> ${HostName}:${RemoteDir}"

ssh $HostName "mkdir -p '$RemoteDir'"
# Prefer scp of a tar stream (no rsync required on Windows)
$tar = Join-Path $env:TEMP "adhd-hub-deploy.tgz"
Push-Location $Root
try {
  tar -czf $tar --exclude=.git --exclude=.venv --exclude=data --exclude=__pycache__ --exclude=.env --exclude=graphify-out .
} finally {
  Pop-Location
}
scp $tar "${HostName}:/tmp/adhd-hub-deploy.tgz"
Remove-Item $tar -Force

$remote = @"
set -euo pipefail
mkdir -p '$RemoteDir'
tar -xzf /tmp/adhd-hub-deploy.tgz -C '$RemoteDir'
rm -f /tmp/adhd-hub-deploy.tgz
cd '$RemoteDir'
if [[ ! -f .env ]]; then
  cp .env.example .env
  TOKEN=`$(openssl rand -hex 32)
  sed -i "s/^ADHD_HUB_AUTH_TOKEN=.*/ADHD_HUB_AUTH_TOKEN=`$TOKEN/" .env
  echo "Created .env"
  echo "ADHD_HUB_AUTH_TOKEN=`$TOKEN"
fi
if docker compose version >/dev/null 2>&1; then
  docker compose up -d --build
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose up -d --build
else
  echo 'docker compose not found' >&2
  exit 1
fi
sleep 2
curl -sf http://127.0.0.1:8787/api/health
echo
"@
ssh $HostName $remote
