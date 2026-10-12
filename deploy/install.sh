#!/usr/bin/env bash
# LayerHound installer. Run ON THE BOARD (Debian 12, Armbian, Raspberry Pi OS or Ubuntu):
#
#   curl -fsSL https://github.com/TeamTacticalRC/layerhound-releases/releases/latest/download/install.sh | bash
#
# Downloads the latest LayerHound release, checks its checksum and Team Tactical RC signature,
# and runs the board setup (deploy/setup.sh), which installs it to /opt/layerhound with its data in
# /var/lib/layerhound, running as its own "layerhound" account. Asks for your password
# for sudo. Already installed? Update from Settings -> Updates instead; for an update that changes
# the board setup (Settings says so), run this with --update:
#
#   curl -fsSL https://github.com/TeamTacticalRC/layerhound-releases/releases/latest/download/install.sh | bash -s -- --update
#
# Options (after "bash -s --" when piping, e.g. "| bash -s -- --hostname myfarm"):
#   --hostname NAME   name the board NAME, reachable at http://NAME.local (otherwise you're asked
#                     whether to rename a board that still has a default name)
#   --keep-hostname   never rename the board
#   --package FILE    install from a downloaded package (FILE.sig must be next to it)
#   --port N          serve LayerHound on port N instead of 80 (when another program already uses 80)
#   --update          update an existing install to the latest release, keeping its printers, settings,
#                     accounts and data: the same backup, install and automatic rollback as Settings ->
#                     Updates, then the new board setup
#
# LAYERHOUND_INSTALL_TEST=1 checks and unpacks the package, then stops before anything needs sudo
# (no packages, renaming or board setup). Used to test the installer on a board that already runs LayerHound.
set -euo pipefail
TEST="${LAYERHOUND_INSTALL_TEST:-}"

RELEASES="TeamTacticalRC/layerhound-releases"
APP_DIR=/opt/layerhound
LEGACY_DIR="$HOME/layerhound"   # installs from before 1.4 (setup.sh moves them to $APP_DIR)
DATA_DIR=/var/lib/layerhound
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
  local hostname_opt="" keep_hostname="" package="" port="80" update=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --update) update=1; shift ;;
      --hostname) hostname_opt="${2:-}"; shift 2 ;;
      --keep-hostname) keep_hostname=1; shift ;;
      --package) package="${2:-}"; shift 2 ;;
      --port) port="${2:-}"; shift 2 ;;
      *) fail "Unknown option: $1" ;;
    esac
  done

  [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail "--port needs a number from 1 to 65535."
  [ "$(id -u)" != 0 ] || fail "Run this as your normal user, not root. It asks for sudo when needed."
  command -v apt-get >/dev/null && command -v systemctl >/dev/null || fail "This installer needs a Debian-based Linux with systemd (Debian 12, Armbian, Raspberry Pi OS, Ubuntu)."
  # Which install is the live one: the account the service runs as says so (after going back from
  # 1.4 with revert-to-home-install.sh, /opt/layerhound is still there, unused)
  local installed="" runs_as; runs_as="$(systemctl show -p User --value layerhound 2>/dev/null || true)"
  if [ "$runs_as" = layerhound ] && [ -e "$APP_DIR/backend/main.py" ]; then installed="$APP_DIR"
  elif [ -e "$LEGACY_DIR/backend/main.py" ]; then installed="$LEGACY_DIR"
  elif [ -e "$APP_DIR/backend/main.py" ]; then installed="$APP_DIR"
  fi
  if [ -n "$update" ]; then
    [ -n "$installed" ] && [ -x "$installed/backend/.venv/bin/python" ] || fail "LayerHound isn't installed yet. Run the installer without --update."
    # Keep the port it already uses
    port="$(cat /etc/layerhound/port 2>/dev/null || cat /var/lib/layerhound/port 2>/dev/null || echo 80)"
  elif [ -n "$installed" ]; then
    fail "LayerHound is already installed in $installed. To update, open LayerHound and go to Settings -> Updates (or, if it says the update needs a full install, run this installer with --update)."
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

  if [ -n "$update" ]; then update_existing "$pkg" "$sig" "$installed"; return 0; fi

  say "Unpacking"
  mkdir -p "$work/unpack"
  tar -xzf "$pkg" -C "$work/unpack" --no-same-owner
  [ -f "$work/unpack/layerhound/deploy/setup.sh" ] || fail "The package doesn't look like LayerHound."
  local src="$work/unpack/layerhound"
  local version; version="$(cat "$src/VERSION" 2>/dev/null || echo "?")"
  if [ -n "$TEST" ]; then say "Test mode: LayerHound $version unpacked; stopping before board setup"; return 0; fi

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

  say "Setting up the board and installing LayerHound to $APP_DIR (this takes a few minutes)"
  LAYERHOUND_PORT="$port" bash "$src/deploy/setup.sh"
  # Announce the (new) name on the network right away
  sudo systemctl restart avahi-daemon 2>/dev/null || true

  echo
  say "LayerHound $version is installed."
  local url="http://$(hostname).local"; [ "$port" = 80 ] || url="$url:$port"
  echo "    Open $url in a browser on the same network to create your admin account."
  echo "    Forgot your password later? Run: layerhound reset-password"
}

# Update an installed LayerHound with a verified package: the installed updater does what
# Settings -> Updates does (back up the database, keep the current code, put the new code in place
# with data, the database and the Python environment kept, restart, and roll back if the new
# version doesn't start); then the new board setup runs, which is the part that needs sudo.
update_existing() {
  local pkg="$1" sig="$2" dir="$3" from version updates job
  # The installed version: from a release package's VERSION file, or the code itself
  from="$(sed -n "s/^APP_VERSION='\(.*\)'/\1/p" "$dir/backend/settings.py" 2>/dev/null || true)"
  [ -n "$from" ] || from="$(cat "$dir/VERSION" 2>/dev/null || echo "?")"
  mkdir -p "$work/peek" && tar -xzf "$pkg" -C "$work/peek" --no-same-owner layerhound/VERSION 2>/dev/null || true
  version="$(cat "$work/peek/layerhound/VERSION" 2>/dev/null || echo "?")"
  [ -n "$TEST" ] && { say "Test mode: would update LayerHound $from in $dir to $version; stopping here"; return 0; }
  say "Updating LayerHound $from to $version (your printers, settings and accounts are kept)"
  job="layerhound-$version.tar.gz"
  if [ "$dir" = "$APP_DIR" ]; then
    # Since 1.4: the updater runs as root and checks the signature again itself
    updates="$DATA_DIR/data/updates"
    sudo install -d -o layerhound -g layerhound "$updates"
    sudo install -o layerhound -g layerhound -m 644 "$pkg" "$updates/$job"
    sudo install -o layerhound -g layerhound -m 644 "$sig" "$updates/$job.sig"
    write_job "$updates" "$version" "$from" | sudo -u layerhound tee "$updates/state.json" >/dev/null
    sudo env LAYERHOUND_DB="$DATA_DIR/layerhound.db" LAYERHOUND_FILES="$DATA_DIR/files" LAYERHOUND_PORT="$port" \
      "$APP_DIR/backend/.venv/bin/python" "$APP_DIR/backend/updater.py" || true
  else
    # Before 1.4 (in the home folder): its own updater, as before; the new setup then moves it to $APP_DIR
    updates="$dir/backend/data/updates"
    mkdir -p "$updates"; cp "$pkg" "$updates/$job"; cp "$sig" "$updates/$job.sig"
    write_job "$updates" "$version" "$from" > "$updates/state.json"
    LAYERHOUND_PORT="$port" "$dir/backend/.venv/bin/python" "$dir/backend/updater.py" || true
  fi
  # Since 1.4 the status file is in LayerHound's own data folder, which only it (and root) can read
  local read=""; [ "$dir" = "$APP_DIR" ] && read="sudo"
  local result; result="$($read python3 -c 'import json,sys; j=json.load(open(sys.argv[1])); print(j.get("phase"), j.get("rolled_back"), j.get("error") or "")' "$updates/state.json" 2>/dev/null || echo "unknown")"
  case "$result" in
    done*) ;;
    "failed True"*) fail "The update didn't work (${result#failed True }). LayerHound went back to $from and is running." ;;
    *) fail "The update didn't finish ($result). Check LayerHound in a browser; Settings -> Recent problems may say more." ;;
  esac
  say "Setting up the board for $version (this takes a few minutes)"
  local setup="$APP_DIR/deploy/setup.sh"; [ "$dir" = "$APP_DIR" ] || setup="$dir/deploy/setup.sh"
  LAYERHOUND_PORT="$port" bash "$setup" || fail "LayerHound $version is installed, but the board setup didn't finish. Run this command again."
  echo
  say "LayerHound is updated to $version."
}

# The updater's job: install this package
write_job() {
  python3 - "$@" <<'PY'
import json, sys, time
d, version, old = sys.argv[1:4]
print(json.dumps({'version': version, 'from_version': old, 'started': time.time(), 'phase': 'installing',
                  'package': f'{d}/layerhound-{version}.tar.gz'}))
PY
}

# Everything runs from here, so a half-downloaded script does nothing
main "$@"
