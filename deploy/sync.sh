#!/usr/bin/env bash
# Push the fly service to the box. Usage: deploy/sync.sh [ssh-alias]   (default form4-vps)
# Never copies .env, state/, build/ or data/. Restart yourself: ssh form4-vps systemctl restart fly
set -euo pipefail
HOST=${1:-form4-vps}
cd "$(dirname "$0")/.."
rsync -az --exclude __pycache__ --exclude state --exclude build --exclude data --exclude '.env' --exclude '.venv' ./ "$HOST:/opt/fly/"
echo "synced. restart: ssh $HOST systemctl restart fly"
