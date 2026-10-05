#!/usr/bin/env bash
# LayerHound installer. Run ON THE BOARD (Debian 12, Armbian, Raspberry Pi OS or Ubuntu):
#
#   curl -fsSL https://github.com/TeamTacticalRC/layerhound-releases/releases/latest/download/install.sh | bash
#
# Downloads the latest LayerHound release, checks its checksum and Team Tactical RC signature,
# installs it to ~/layerhound and runs the board setup (deploy/setup.sh). Asks for your password
# for sudo. Already installed? Update from Settings -> Updates instead.
#
# Options (after "bash -s --" when piping, e.g. "| bash -s -- --hostname myfarm"):
#   --hostname NAME   name the board NAME, reachable at http://NAME.local (otherwise you're asked
#                     whether to rename a board that still has a default name)
#   --keep-hostname   never rename the board
#   --package FILE    install from a downloaded package (FILE.sig must be next to it)
#
# LAYERHOUND_INSTALL_TEST=1 checks and unpacks the package, then stops before anything needs sudo
# (no packages, renaming or board setup). Used to test the installer on a board that already runs LayerHound.
set -euo pipefail
TEST="${LAYERHOUND_INSTALL_TEST:-}"

RELEASES="TeamTacticalRC/layerhound-releases"
APP_DIR="$HOME/layerhound"
DEFAULT_NAME="layerhound"
# Team Tactical RC's release signing key (the same key as PUBLIC_KEY in backend/updates.py)
PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAqTr3P5crD7RJzCkzsuZdTwBzZ2WKyRp3rPiePQIjt6E=
-----END PUBLIC KEY-----"

say() { printf '==> %s\n' "$*"; }
fail() { printf '!! %s\n' "$*" >&2; exit 1; }
# Questions read from the terminal even when this script arrives through a pipe
ask() { local reply=""; if [ -r /dev/tty ]; then read -r -p "$1 " reply </dev/tty || true; fi; printf '%s' "$reply"; }

main() {
  local hostname_opt="" keep_hostname="" package=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --hostname) hostname_opt="${2:-}"; shift 2 ;;
      --keep-hostname) keep_hostname=1; shift ;;
      --package) package="${2:-}"; shift 2 ;;
      *) fail "Unknown option: $1" ;;
    esac
  done

  [ "$(id -u)" != 0 ] || fail "Run this as your normal user, not root. It asks for sudo when needed."
  command -v apt-get >/dev/null && command -v systemctl >/dev/null || fail "This installer needs a Debian-based Linux with systemd (Debian 12, Armbian, Raspberry Pi OS, Ubuntu)."
  if [ -e "$APP_DIR/backend/main.py" ]; then
    fail "LayerHound is already installed in $APP_DIR. To update, open LayerHound and go to Settings -> Updates."
  fi

  if [ -z "$TEST" ]; then
    say "Installing tools the installer needs (on a new board this can take a few minutes)"
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1 apt-get install -y -qq curl ca-certificates openssl tar python3 >/dev/null
  fi

  work="$(mktemp -d)"   # global, so the cleanup below can still see it after main() returns
  trap 'rm -rf "${work:-}"' EXIT
  local pkg sig manifest=""
  if [ -n "$package" ]; then
    [ -f "$package" ] && [ -f "$package.sig" ] || fail "Need both $package and $package.sig"
    pkg="$package"; sig="$package.sig"
    [ -f "$(dirname "$package")/manifest.json" ] && manifest="$(dirname "$package")/manifest.json"
  else
    say "Finding the latest LayerHound release"
    local base="https://github.com/$RELEASES/releases/latest/download"
    curl -fsSL "$base/manifest.json" -o "$work/manifest.json" || fail "Couldn't download the release information. Is the board online?"
    manifest="$work/manifest.json"
    local file; file="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["file"])' "$manifest")"
    say "Downloading $file"
    curl -fSL --progress-bar "$base/$file" -o "$work/$file"
    curl -fsSL "$base/$file.sig" -o "$work/$file.sig"
    pkg="$work/$file"; sig="$work/$file.sig"
  fi

  say "Checking the download"
  if [ -n "$manifest" ]; then
    local want; want="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$manifest")"
    [ "$(sha256sum "$pkg" | cut -d' ' -f1)" = "$want" ] || fail "The download is damaged (checksum mismatch). Try again."
  fi
  printf '%s\n' "$PUBLIC_KEY" > "$work/key.pem"
  base64 -d "$sig" > "$work/sig.bin" 2>/dev/null || fail "The signature file is unreadable."
  openssl pkeyutl -verify -pubin -inkey "$work/key.pem" -rawin -in "$pkg" -sigfile "$work/sig.bin" >/dev/null 2>&1 \
    || fail "This package is not signed by Team Tactical RC. Not installing it."
  say "Signature OK: signed by Team Tactical RC"

  say "Unpacking to $APP_DIR"
  mkdir -p "$work/unpack"
  tar -xzf "$pkg" -C "$work/unpack" --no-same-owner
  [ -f "$work/unpack/layerhound/deploy/setup.sh" ] || fail "The package doesn't look like LayerHound."
  mv "$work/unpack/layerhound" "$APP_DIR"
  local version; version="$(cat "$APP_DIR/VERSION" 2>/dev/null || echo "?")"
  if [ -n "$TEST" ]; then say "Test mode: LayerHound $version unpacked to $APP_DIR; stopping before board setup"; return 0; fi

  # A board with its maker's default name is easier to find as http://layerhound.local
  local current; current="$(hostname)"; local target=""
  if [ -n "$hostname_opt" ]; then target="$hostname_opt"
  elif [ -z "$keep_hostname" ] && [ "$current" != "$DEFAULT_NAME" ]; then
    case "$current" in
      radxa|rock*|raspberrypi|ubuntu|debian|armbian|orangepi*|localhost)
        local answer; answer="$(ask "This board is called '$current'. Rename it to '$DEFAULT_NAME' so LayerHound is at http://$DEFAULT_NAME.local? [Y/n]")"
        case "$answer" in [nN]*) ;; *) target="$DEFAULT_NAME" ;; esac ;;
    esac
  fi
  if [ -n "$target" ] && [ "$target" != "$current" ]; then
    [[ "$target" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$ ]] || fail "'$target' isn't a valid name (letters, numbers and dashes)."
    say "Renaming the board to $target"
    sudo hostnamectl set-hostname "$target"
    grep -qE "[[:space:]]$target([[:space:]]|\$)" /etc/hosts || echo "127.0.1.1 $target" | sudo tee -a /etc/hosts >/dev/null
  fi

  say "Setting up the board (this takes a few minutes)"
  bash "$APP_DIR/deploy/setup.sh"
  # Announce the (new) name on the network right away
  sudo systemctl restart avahi-daemon 2>/dev/null || true

  echo
  say "LayerHound $version is installed."
  echo "    Open http://$(hostname).local in a browser on the same network to create your admin account."
  echo "    Forgot your password later? Run: layerhound reset-password"
}

# Everything runs from here, so a half-downloaded script does nothing
main "$@"
