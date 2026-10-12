#!/usr/bin/env bash
# Runs ON YOUR MAC. Builds the dashboard, copies it to the board and (re)starts it.
#
#   deploy/deploy.sh user@board-hostname.local            first install + every update
#   deploy/deploy.sh user@board-hostname.local --with-db  also copy this Mac's printer list
#   deploy/deploy.sh user@board-hostname.local --full     run the full board setup even if unchanged
#
# The files go to a staging folder on the board (~/layerhound-src); LayerHound itself runs from
# /opt/layerhound (see setup.sh). Most deploys only change LayerHound itself: the code installer
# (/usr/local/sbin/layerhound-install-code, which setup.sh lets your account run without a password
# on a development board) puts the code in place and installs any new Python packages, then
# LayerHound restarts, with no password needed. The full board setup (deploy/setup.sh, which needs
# the board's password for sudo) runs only the first time, when setup.sh has changed since it was
# last applied, or with --full. The board records which setup.sh it last applied in
# /etc/layerhound/setup.sha256 (written by setup.sh as root).
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
REMOTE_DIR="layerhound-src"   # staging, relative to the board user's home folder
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
  echo "==> Copying printer database (needs the board's password)"
  DB=backend/layerhound.db; [ -f "$DB" ] || DB=backend/ttrc.db   # installs from before the rename
  ssh "$TARGET" "mkdir -p $REMOTE_DIR/.import"
  rsync -az "$DB" "$TARGET:$REMOTE_DIR/.import/layerhound.db"
  # Stored access codes are encrypted with this computer's key; the board needs the same key to read them
  [ -f backend/data/secret.key ] && rsync -az --chmod=F600 backend/data/secret.key "$TARGET:$REMOTE_DIR/.import/secret.key"
  ssh -t "$TARGET" "sudo systemctl stop layerhound; sudo install -o layerhound -g layerhound -m 640 ~/$REMOTE_DIR/.import/layerhound.db /var/lib/layerhound/layerhound.db; \
    [ -f ~/$REMOTE_DIR/.import/secret.key ] && sudo install -o layerhound -g layerhound -m 600 ~/$REMOTE_DIR/.import/secret.key /var/lib/layerhound/data/secret.key; rm -rf ~/$REMOTE_DIR/.import"
fi

if [ -z "$FULL" ]; then
  echo "==> Updating LayerHound on the board"
  # Exit code 10 means the board setup changed (or never ran), so the full setup is needed
  set +e
  ssh "$TARGET" "REMOTE_DIR=$REMOTE_DIR bash -s" <<'QUICK'
set -e
cd ~/"$REMOTE_DIR"
want=$(sha256sum deploy/setup.sh | cut -d' ' -f1)
have=$(cat /etc/layerhound/setup.sha256 2>/dev/null || true)
[ "$want" = "$have" ] || exit 10
PORT=$(cat /etc/layerhound/port 2>/dev/null || echo 80)
# Puts the code in /opt/layerhound (allowed without a password on a development board; otherwise
# exit 10 runs the full setup)
sudo -n /usr/local/sbin/layerhound-install-code "$HOME/$REMOTE_DIR" || exit 10
# Allowed without a password on a development board (setup.sh, LAYERHOUND_DEV_DEPLOY)
sudo -n "$(command -v systemctl)" restart layerhound.service
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
# LAYERHOUND_DEV_DEPLOY lets this account install code from ~/layerhound-src without a password next time
ssh -t "$TARGET" "LAYERHOUND_DEV_DEPLOY=1 bash ~/$REMOTE_DIR/deploy/setup.sh"
