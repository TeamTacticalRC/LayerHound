#!/usr/bin/env bash
# Goes back from the 1.4 layout (/opt/layerhound, data in /var/lib/layerhound, its own account) to
# the layout before it (~/layerhound, running as you), keeping your current data. Run ON THE BOARD
# as the board's owner (it asks for your password for sudo):
#
#   bash deploy/revert-to-home-install.sh               installs LayerHound 1.3.0 (the last home-folder
#                                                       version), downloaded and signature-checked
#   bash deploy/revert-to-home-install.sh --package F   from a downloaded package (F.sig next to it)
#
# 1. Stops LayerHound and copies your current database, data folder (encryption key, backups, ...)
#    and Files folder back into ~/layerhound and ~/LayerHound Files.
# 2. Puts the 1.3.0 code in ~/layerhound and runs its own setup, which sets the service, permissions
#    and Tailscale back to the home-folder way.
# /opt/layerhound, /var/lib/layerhound and the "layerhound" account are left in place (unused; the
# database there is renamed .before-revert-..., so moving again copies your current data fresh);
# remove them by hand once you're sure. See docs/REVERT-OPT-MOVE.md.
set -euo pipefail
VERSION=1.3.0
RELEASES="TeamTacticalRC/layerhound-releases"
HOME_DIR="$HOME/layerhound"; DATA_DIR=/var/lib/layerhound
PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAqTr3P5crD7RJzCkzsuZdTwBzZ2WKyRp3rPiePQIjt6E=
-----END PUBLIC KEY-----"
say() { printf '==> %s\n' "$*"; }
fail() { printf '!! %s\n' "$*" >&2; exit 1; }

package=""
[ "${1:-}" = "--package" ] && package="${2:?--package needs a file}"
[ "$(id -u)" != 0 ] || fail "Run this as your normal user, not root. It asks for sudo when needed."
sudo test -f "$DATA_DIR/layerhound.db" || fail "No LayerHound data in $DATA_DIR: this board isn't on the /opt layout, nothing to revert."

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
if [ -z "$package" ]; then
  say "Downloading LayerHound $VERSION"
  base="https://github.com/$RELEASES/releases/download/v$VERSION"
  curl -fsSL "$base/layerhound-$VERSION.tar.gz" -o "$work/p.tar.gz" || fail "Couldn't download it. Is the board online?"
  curl -fsSL "$base/layerhound-$VERSION.tar.gz.sig" -o "$work/p.tar.gz.sig"
  package="$work/p.tar.gz"
fi
printf '%s\n' "$PUBLIC_KEY" > "$work/key.pem"
base64 -d "$package.sig" > "$work/sig.bin" 2>/dev/null || fail "The signature file is unreadable."
openssl pkeyutl -verify -pubin -inkey "$work/key.pem" -rawin -in "$package" -sigfile "$work/sig.bin" >/dev/null 2>&1 \
  || fail "This package is not signed by Team Tactical RC. Not installing it."
say "Signature OK"
mkdir -p "$work/unpack"; tar -xzf "$package" -C "$work/unpack" --no-same-owner
src="$work/unpack/layerhound"
grep -q "^APP_VERSION='$VERSION'" "$src/backend/settings.py" || say "(note: the package isn't $VERSION)"

say "Stopping LayerHound and copying your current data back to $HOME_DIR"
sudo systemctl stop layerhound
mkdir -p "$HOME_DIR/backend/data" "$HOME/LayerHound Files"
sudo python3 - "$DATA_DIR/layerhound.db" "$HOME_DIR/backend/layerhound.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
with dst: src.backup(dst)
print(f"   database: {dst.execute('SELECT COUNT(*) FROM printers').fetchone()[0]} printers")
PY
sudo rsync -a --exclude 'updates/new' --exclude 'uploads' "$DATA_DIR/data/" "$HOME_DIR/backend/data/"
sudo rsync -a "$DATA_DIR/files/" "$HOME/LayerHound Files/"
sudo chown -R "$(id -un):$(id -gn)" "$HOME_DIR" "$HOME/LayerHound Files"
chmod 600 "$HOME_DIR/backend/data/secret.key" 2>/dev/null || true

# The copy in $DATA_DIR is now out of date: set it aside (renamed, not deleted), so moving to the
# 1.4 layout again later copies your current data instead of starting from this one
stamp="$(date +%Y%m%d-%H%M%S)"
sudo mv "$DATA_DIR/layerhound.db" "$DATA_DIR/layerhound.db.before-revert-$stamp"
sudo rm -f "$DATA_DIR/MOVED-FROM"

say "Putting LayerHound $VERSION back in $HOME_DIR"
for d in backend dist deploy; do
  rsync -a --delete --exclude '.venv' --exclude 'data' --exclude '*.db' --exclude '*.db-*' --exclude '__pycache__' "$src/$d/" "$HOME_DIR/$d/"
done
cp "$src/VERSION" "$HOME_DIR/VERSION" 2>/dev/null || true
[ -x "$HOME_DIR/backend/.venv/bin/python" ] || python3 -m venv "$HOME_DIR/backend/.venv"
"$HOME_DIR/backend/.venv/bin/pip" install -q -r "$HOME_DIR/backend/requirements.txt"

say "Running the $VERSION board setup (service, permissions, Tailscale back to the home-folder way)"
# The 1.4 setup records live in /etc/layerhound; the old setup uses /var/lib/layerhound's
sudo rm -f /etc/sudoers.d/layerhound
LAYERHOUND_PORT="$(cat /etc/layerhound/port 2>/dev/null || echo 80)" bash "$HOME_DIR/deploy/setup.sh"
echo
say "Reverted: LayerHound runs from $HOME_DIR as $(id -un) again, with your current data."
echo "    Left in place, unused: /opt/layerhound, $DATA_DIR and the 'layerhound' account."
