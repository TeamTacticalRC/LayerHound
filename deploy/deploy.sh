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
REMOTE_DIR="layerhound"   # relative to the board user's home folder
cd "$(dirname "$0")/.."

echo "==> Building frontend"
npm run build --silent

# Fresh board images don't always include rsync; install it first (may ask for the board's password)
if ! ssh "$TARGET" 'command -v rsync >/dev/null'; then
  echo "==> Installing rsync on the board"
  ssh -t "$TARGET" "sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get install -y -qq rsync"
fi

echo "==> Copying files to $TARGET:~/$REMOTE_DIR"
rsync -az --delete \
  --exclude .git --exclude node_modules --exclude .DS_Store \
  --exclude 'backend/.venv' --exclude '__pycache__' --exclude 'backend/*.db*' --exclude 'backend/data' \
  ./ "$TARGET:$REMOTE_DIR/"

if [ "$WITH_DB" = "--with-db" ]; then
  echo "==> Copying printer database"
  DB=backend/layerhound.db; [ -f "$DB" ] || DB=backend/ttrc.db   # installs from before the rename
  rsync -az "$DB" "$TARGET:$REMOTE_DIR/backend/layerhound.db"
  # Stored access codes are encrypted with this computer's key; the board needs the same key to read them
  if [ -f backend/data/secret.key ]; then
    ssh "$TARGET" "mkdir -p $REMOTE_DIR/backend/data"
    rsync -az --chmod=F600 backend/data/secret.key "$TARGET:$REMOTE_DIR/backend/data/secret.key"
  fi
fi

echo "==> Running setup on the board (it may ask for the board's password for sudo)"
ssh -t "$TARGET" "bash ~/$REMOTE_DIR/deploy/setup.sh"
