#!/usr/bin/env bash
# Puts LayerHound's code from a folder (a release package, or deploy.sh's staging copy) into
# /opt/layerhound, owned by root, so the LayerHound service account can't change its own code.
# The Python environment, the database and the data folder are never touched here.
#
#   layerhound-install-code SOURCE_DIR        (as root; setup.sh installs it in /usr/local/sbin)
#
# Installs new Python packages when requirements.txt changed. Doesn't restart LayerHound.
set -euo pipefail
SRC="${1:?usage: layerhound-install-code SOURCE_DIR}"
APP_DIR=/opt/layerhound
[ "$(id -u)" = 0 ] || { echo "!! Run as root" >&2; exit 1; }
[ -f "$SRC/backend/main.py" ] && [ -f "$SRC/deploy/setup.sh" ] || { echo "!! $SRC doesn't look like LayerHound" >&2; exit 1; }
SRC="$(cd "$SRC" && pwd)"
[ "$SRC" = "$APP_DIR" ] && exit 0   # already in place

mkdir -p "$APP_DIR"
# The code only: backend (without its Python environment, data, databases and caches), the built
# dashboard, the deploy scripts and the version file
rsync -a --delete --chown=root:root \
  --exclude '.venv' --exclude 'data' --exclude '*.db' --exclude '*.db-*' --exclude '__pycache__' --exclude 'tests' \
  "$SRC/backend/" "$APP_DIR/backend/"
for d in dist deploy; do
  [ -d "$SRC/$d" ] && rsync -a --delete --chown=root:root --exclude '__pycache__' "$SRC/$d/" "$APP_DIR/$d/"
done
for f in VERSION LICENSE; do [ -f "$SRC/$f" ] && install -o root -g root -m 644 "$SRC/$f" "$APP_DIR/$f"; done
chmod -R go-w "$APP_DIR"

cd "$APP_DIR/backend"
[ -x .venv/bin/python ] || python3 -m venv .venv
if ! cmp -s requirements.txt .venv/.installed-requirements; then
  echo "==> Installing Python packages"
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  cp requirements.txt .venv/.installed-requirements   # lets later installs skip pip when nothing changed
fi
