#!/usr/bin/env bash
# Runs ON YOUR MAC. Builds the dashboard, copies it to the board and (re)starts it.
#
#   deploy/deploy.sh user@board-hostname.local            first install + every update
#   deploy/deploy.sh user@board-hostname.local --with-db  also copy this Mac's printer list
#   deploy/deploy.sh user@board-hostname.local --full     run the full board setup even if unchanged
#
# Most deploys only change LayerHound itself: they copy the files, install any new Python packages
# and restart it, with no password needed. The full board setup (deploy/setup.sh, which needs the
# board's password for sudo) runs only the first time, when setup.sh has changed since it was last
# applied, or with --full. The board records which setup.sh it last applied in
# /var/lib/layerhound/setup.sha256 (written by setup.sh as root).
#
# The board's printer database is never overwritten unless you pass --with-db.
set -euo pipefail

TARGET=""; WITH_DB=""; FULL=""
for arg in "$@"; do
  case "$arg" in
    --with-db) WITH_DB="--with-db" ;;
    --full) FULL=1 ;;
    -*) echo "Unknown option: $arg" >&2; exit 1 ;;
    *) TARGET="$arg" ;;
  esac
done
if [ -z "$TARGET" ]; then echo "Usage: deploy/deploy.sh user@host [--with-db] [--full]" >&2; exit 1; fi
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

if [ -z "$FULL" ]; then
  echo "==> Updating LayerHound on the board"
  # Exit code 10 means the board setup changed (or never ran), so the full setup is needed
  set +e
  ssh "$TARGET" "REMOTE_DIR=$REMOTE_DIR bash -s" <<'QUICK'
set -e
cd ~/"$REMOTE_DIR"
want=$(sha256sum deploy/setup.sh | cut -d' ' -f1)
have=$(cat /var/lib/layerhound/setup.sha256 2>/dev/null || true)
[ "$want" = "$have" ] || exit 10
PORT=$(cat /var/lib/layerhound/port 2>/dev/null || echo 80)
cd backend
if ! cmp -s requirements.txt .venv/.installed-requirements; then
  echo "==> Installing Python packages"
  .venv/bin/pip install -q -r requirements.txt && cp requirements.txt .venv/.installed-requirements
fi
# Allowed without a password by the rule setup.sh installs for updates
systemctl restart layerhound.service
for _ in $(seq 40); do
  if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null; then
    URL="http://$(hostname).local"; [ "$PORT" = 80 ] || URL="$URL:$PORT"
    echo "==> Dashboard is running: $URL"; exit 0
  fi
  sleep 1
done
echo "!! Service did not answer within 40 seconds. Check the logs with: journalctl -u layerhound -n 50" >&2
exit 1
QUICK
  code=$?
  set -e
  [ "$code" = 10 ] || exit "$code"
  echo "==> The board setup changed since it was last applied, so running the full setup"
fi

echo "==> Running setup on the board (it may ask for the board's password for sudo)"
ssh -t "$TARGET" "bash ~/$REMOTE_DIR/deploy/setup.sh"
