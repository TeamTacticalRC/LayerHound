#!/usr/bin/env bash
# Builds a LayerHound card image for the Radxa ROCK 4D: Radxa's own OS with LayerHound already
# installed. Write it to a microSD card (balenaEtcher, Raspberry Pi Imager), put the card in the
# board, plug in power: LayerHound is at http://layerhound.local (or, with no network, the board
# opens the "LayerHound-Setup" Wi-Fi).
#
# Run as root on an arm64 Debian or Ubuntu computer (a ROCK 4D or Raspberry Pi works, or GitHub's
# arm64 runners). Needs about 15 GB free and internet, and takes 15-30 minutes.
#
#   sudo deploy/image/build-image.sh [--package layerhound-X.Y.Z.tar.gz] [--base radxa.img.xz] [--out DIR]
#
#   --package FILE   a signed LayerHound release package (FILE.sig next to it). Default: the latest
#                    release, downloaded and checked like install.sh does
#   --base FILE      Radxa's OS image (.img.xz). Default: the tested image below, downloaded and checked
#   --out DIR        where the image goes (default: the current folder)
#   --work DIR       where to unpack while building, about 13 GB (default: /var/tmp)
#   --source DIR     for testing only: an unpacked, unsigned LayerHound folder (e.g. deploy.sh's
#                    ~/layerhound-src) instead of a signed package. Never sell or share these images
#   --keep-desktop   keep Radxa's desktop starting (by default the card starts without it: LayerHound
#                    runs headless and the desktop only uses memory)
#
# Nothing secret goes on the card: LayerHound's keys, its database and the SSH host keys are all
# created on each card's first start (firstboot.sh), and the build stops if any are found.
set -euo pipefail

# The tested base: Radxa OS for RK3576 boards (ROCK 4D), release rsdk-r6 (2026-01-13), 512-byte sectors
BASE_URL="https://github.com/radxa-build/radxa-rk3576/releases/download/rsdk-r6/radxa-rk3576_bookworm_kde_r6.output_512.img.xz"
BASE_SHA256="3ce028cd20683d6b89900ce962cfb79736423c9b88616a67fece974f48918fc0"
RELEASES="TeamTacticalRC/layerhound-releases"
GROW=3G                 # room added to the image for LayerHound and its packages
HOSTNAME_ON_CARD=layerhound
# Team Tactical RC's release signing key (the same key as PUBLIC_KEY in backend/updates.py and install.sh)
PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAqTr3P5crD7RJzCkzsuZdTwBzZ2WKyRp3rPiePQIjt6E=
-----END PUBLIC KEY-----"
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf '==> %s\n' "$*"; }
fail() { printf '!! %s\n' "$*" >&2; exit 1; }

package="" source="" base="" out="$PWD" work_in=/var/tmp keep_desktop=""
while [ $# -gt 0 ]; do
  case "$1" in
    --package) package="${2:-}"; shift 2 ;;
    --source) source="${2:-}"; shift 2 ;;
    --base) base="${2:-}"; shift 2 ;;
    --out) out="${2:-}"; shift 2 ;;
    --work) work_in="${2:-}"; shift 2 ;;
    --keep-desktop) keep_desktop=1; shift ;;
    *) fail "Unknown option: $1" ;;
  esac
done
[ "$(id -u)" = 0 ] || fail "Run this as root (sudo)."
[ "$(uname -m)" = aarch64 ] || fail "Run this on an arm64 (aarch64) Linux computer: the image's programs are installed by running them."
for tool in xz losetup parted sgdisk e2fsck resize2fs rsync openssl curl python3 chroot; do
  command -v "$tool" >/dev/null || fail "Missing $tool. Install: apt-get install xz-utils parted gdisk e2fsprogs rsync openssl curl python3"
done
mkdir -p "$out"; out="$(cd "$out" && pwd)"

mkdir -p "$work_in"; work="$(mktemp -d "$work_in/layerhound-image.XXXXXX")"
root="$work/root"; loop=""
cleanup() {
  set +e
  for m in dev/pts dev proc sys run config boot/efi; do mountpoint -q "$root/$m" && umount -l "$root/$m"; done
  mountpoint -q "$root" && umount -l "$root"
  [ -n "$loop" ] && losetup -d "$loop"
  rm -rf "$work"
}
trap cleanup EXIT
trap 'printf "!! Stopped: \"%s\" failed (line %s)\n" "$BASH_COMMAND" "$LINENO" >&2' ERR

# --- The LayerHound package, checked like install.sh does ---
if [ -n "$source" ]; then
  [ -f "$source/deploy/setup.sh" ] && [ -f "$source/backend/main.py" ] || fail "$source doesn't look like LayerHound."
  mkdir -p "$work/pkg"; rsync -a --exclude .venv --exclude node_modules --exclude .git --exclude .import --exclude data --exclude "*.db*" "$source/" "$work/pkg/layerhound/"
  say "TEST IMAGE from $source (unsigned): for testing only, never sell or share it"
elif [ -z "$package" ]; then
  say "Downloading the latest LayerHound release"
  rel="https://github.com/$RELEASES/releases/latest/download"
  curl -fsSL "$rel/manifest.json" -o "$work/manifest.json"
  file="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["file"])' "$work/manifest.json")"
  curl -fSL --progress-bar "$rel/$file" -o "$work/$file"
  curl -fsSL "$rel/$file.sig" -o "$work/$file.sig"
  package="$work/$file"
  want="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$work/manifest.json")"
  [ "$(sha256sum "$package" | cut -d' ' -f1)" = "$want" ] || fail "The LayerHound download is damaged (checksum mismatch)."
fi
if [ -z "$source" ]; then
  [ -f "$package" ] && [ -f "$package.sig" ] || fail "Need both $package and $package.sig"
  printf '%s\n' "$PUBLIC_KEY" > "$work/key.pem"
  base64 -d "$package.sig" > "$work/sig.bin" 2>/dev/null || fail "The signature file is unreadable."
  openssl pkeyutl -verify -pubin -inkey "$work/key.pem" -rawin -in "$package" -sigfile "$work/sig.bin" >/dev/null 2>&1 \
    || fail "$package is not signed by Team Tactical RC."
  mkdir -p "$work/pkg"; tar -xzf "$package" -C "$work/pkg" --no-same-owner
  [ -f "$work/pkg/layerhound/deploy/setup.sh" ] || fail "The package doesn't look like LayerHound."
fi
[ -d "$work/pkg/layerhound/dist" ] || fail "The dashboard isn't built in this LayerHound (no dist folder)."
grep -q LAYERHOUND_IMAGE_BUILD "$work/pkg/layerhound/deploy/setup.sh" \
  || fail "This LayerHound is too old to build a card image (needs the version after 1.4.0)."
version="$(cat "$work/pkg/layerhound/VERSION" 2>/dev/null || sed -n "s/^APP_VERSION='\(.*\)'/\1/p" "$work/pkg/layerhound/backend/settings.py")"
[ -n "$source" ] && version="$version-test"
say "LayerHound $version"

# --- Radxa's OS image ---
if [ -z "$base" ]; then
  base="$out/$(basename "$BASE_URL")"
  if [ ! -f "$base" ] || [ "$(sha256sum "$base" | cut -d' ' -f1)" != "$BASE_SHA256" ]; then
    say "Downloading Radxa OS (about 1.5 GB)"
    curl -fSL --progress-bar "$BASE_URL" -o "$base.part" && mv "$base.part" "$base"
  fi
fi
if [ "$(sha256sum "$base" | cut -d' ' -f1)" != "$BASE_SHA256" ]; then
  [ -n "${LAYERHOUND_ALLOW_UNTESTED_BASE:-}" ] || fail "$base isn't the tested Radxa image (checksum differs). Set LAYERHOUND_ALLOW_UNTESTED_BASE=1 to use it anyway."
  say "Using an untested base image"
fi

img="$work/layerhound.img"
say "Unpacking Radxa OS and making room for LayerHound"
xz -dc "$base" > "$img"
truncate -s "+$GROW" "$img"
# A GPT disk keeps a copy of its partition table at the very end: move it to the new end first
if parted -s "$img" print 2>/dev/null | grep -q '^Partition Table: gpt'; then sgdisk -e "$img" >/dev/null; fi
parted -s "$img" resizepart 3 100%
loop="$(losetup -fP --show "$img")"
sleep 1
[ "$(blkid -s LABEL -o value "${loop}p3")" = rootfs ] || fail "Partition 3 of the base image isn't Radxa's rootfs."
e2fsck -pf "${loop}p3" >/dev/null || [ $? -le 1 ] || fail "The base image's file system has errors."
resize2fs "${loop}p3" >/dev/null

mkdir -p "$root"
mount "${loop}p3" "$root"
mount "${loop}p2" "$root/boot/efi"
mkdir -p "$root/config"; mount "${loop}p1" "$root/config"
for m in dev dev/pts proc sys run; do mount --bind "/$m" "$root/$m"; done
say "Radxa's first-start settings (/config/before.txt):"
sed 's/^/     /' "$root/config/before.txt" 2>/dev/null || echo "     (none)"

# Internet for apt and pip inside the image, and no services started while installing
rm -f "$root/etc/resolv.conf"; cp -L /etc/resolv.conf "$root/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$root/usr/sbin/policy-rc.d"; chmod 755 "$root/usr/sbin/policy-rc.d"

say "Installing LayerHound $version in the image (this is the long part)"
rm -rf "$root/root/layerhound-image-src"
cp -a "$work/pkg/layerhound" "$root/root/layerhound-image-src"
# As plain root: the account that ran sudo here doesn't exist in the image (Radxa makes it on first start)
chroot "$root" env -u SUDO_USER -u SUDO_UID -u SUDO_GID -u SUDO_COMMAND LC_ALL=C.UTF-8 LANG=C.UTF-8 LAYERHOUND_IMAGE_BUILD=1 LAYERHOUND_PORT=80 HOME=/root \
  bash /root/layerhound-image-src/deploy/setup.sh
rm -rf "$root/root/layerhound-image-src"

say "First start: keys, passwords and Tailscale"
install -m 755 "$HERE/firstboot.sh" "$root/usr/local/sbin/layerhound-firstboot"
cat > "$root/etc/systemd/system/layerhound-firstboot.service" <<'EOF'
[Unit]
Description=LayerHound card first start (keys, board password, Tailscale)
ConditionPathExists=!/etc/layerhound/first-boot-done
After=network.target tailscaled.service layerhound.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/layerhound-firstboot
RemainAfterExit=yes
TimeoutStartSec=15min

[Install]
WantedBy=multi-user.target
EOF
chroot "$root" systemctl enable --quiet layerhound-firstboot.service

# The setup page asks for a board password while this mark is there (backend/board.py)
echo radxa > "$root/etc/layerhound/board-password-needed"; chmod 644 "$root/etc/layerhound/board-password-needed"

say "Naming the board $HOSTNAME_ON_CARD (http://$HOSTNAME_ON_CARD.local)"
echo "$HOSTNAME_ON_CARD" > "$root/etc/hostname"
sed -i -E "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t$HOSTNAME_ON_CARD/" "$root/etc/hosts"
grep -q "^127.0.1.1" "$root/etc/hosts" || printf '127.0.1.1\t%s\n' "$HOSTNAME_ON_CARD" >> "$root/etc/hosts"
if [ -z "$keep_desktop" ]; then chroot "$root" systemctl set-default multi-user.target >/dev/null; fi

say "Cleaning up"
chroot "$root" apt-get clean
rm -rf "$root"/var/lib/apt/lists/* "$root"/var/log/journal/* "$root"/root/.cache "$root"/root/.bash_history \
       "$root"/tmp/* "$root"/var/tmp/* "$root/usr/sbin/policy-rc.d" "$root/etc/resolv.conf"
rm -f "$root"/etc/ssh/ssh_host_*
: > "$root/etc/machine-id"; rm -f "$root/var/lib/dbus/machine-id"
find "$root/var/log" -type f -exec truncate -s 0 {} +

say "Checking nothing secret is on the card"
leftovers=""
for f in var/lib/layerhound/layerhound.db var/lib/layerhound/data/secret.key var/lib/layerhound/data/install-id \
         var/lib/tailscale/tailscaled.state etc/layerhound/first-boot-done; do
  [ -e "$root/$f" ] && leftovers="$leftovers /$f"
done
ls "$root"/etc/ssh/ssh_host_* >/dev/null 2>&1 && leftovers="$leftovers /etc/ssh/ssh_host_*"
[ -s "$root/etc/machine-id" ] && leftovers="$leftovers /etc/machine-id"
[ -z "$leftovers" ] || fail "Found files that must be made on each card, not in the image:$leftovers"
cat "$root/etc/layerhound/setup.sha256" >/dev/null || fail "LayerHound's setup didn't finish in the image."

for m in dev/pts dev proc sys run config boot/efi; do umount "$root/$m"; done
umount "$root"
e2fsck -pf "${loop}p3" >/dev/null || true
losetup -d "$loop"; loop=""

name="layerhound-$version-rock-4d.img.xz"
say "Compressing to $out/$name (several minutes)"
xz -T0 -6 -c "$img" > "$out/$name.part" && mv "$out/$name.part" "$out/$name"
(cd "$out" && sha256sum "$name" > "$name.sha256")
say "Done: $out/$name"
echo "    Write it to a microSD card (16 GB or larger, high endurance) with balenaEtcher or Raspberry Pi Imager."
