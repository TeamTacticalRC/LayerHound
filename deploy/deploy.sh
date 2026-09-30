#!/usr/bin/env bash
# Runs ON YOUR MAC. Builds the dashboard, copies it to the board and (re)starts it.
#
#   deploy/deploy.sh user@board-hostname.local            first install + every update
#   deploy/deploy.sh user@board-hostname.local --with-db  also copy this Mac's printer list
#
# The board's printer database is never overwritten unless you pass --with-db.
set -euo pipefail

TARGET="${1:-}"; WITH_DB="${2:-}"
if [ -z "$TARGET" ]; then echo "Usage: deploy/deploy.sh user@host [--with-db]" >&2; exit 1; fi
REMOTE_DIR="ttrc-dashboard"   # relative to the board user's home folder
cd "$(dirname "$0")/.."

echo "==> Building frontend"
npm run build --silent

echo "==> Copying files to $TARGET:~/$REMOTE_DIR"
rsync -az --delete \
  --exclude .git --exclude node_modules --exclude .DS_Store \
  --exclude 'backend/.venv' --exclude '__pycache__' --exclude 'backend/*.db*' \
  ./ "$TARGET:$REMOTE_DIR/"

if [ "$WITH_DB" = "--with-db" ]; then
  echo "==> Copying printer database"
  rsync -az backend/ttrc.db "$TARGET:$REMOTE_DIR/backend/ttrc.db"
fi

echo "==> Running setup on the board (it may ask for the board's password for sudo)"
ssh -t "$TARGET" "bash ~/$REMOTE_DIR/deploy/setup.sh"
