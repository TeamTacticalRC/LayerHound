#!/usr/bin/env bash
# Runs ON THE BOARD, as the board's owner (it uses sudo). Safe to run again after every update.
# Called by install.sh (new installs and --update) and deploy.sh.
#
# Where LayerHound lives (since 1.4):
#   /opt/layerhound            the code, owned by root: LayerHound can't change its own code
#   /var/lib/layerhound        its database, data folder (encryption key, backups, ...) and Files folder
#   /etc/layerhound            which setup.sh was applied, and the port
# It runs as its own "layerhound" system account: no password, no login, no sudo. A break-in to
# LayerHound stays boxed in there, away from the owner's account, files and sudo.
#
# Installs from before 1.4 lived in the owner's home folder (~/layerhound, running as the owner).
# The first run of this setup moves the database, data and Files folder over, and leaves the old
# folder untouched as a fallback (deploy/revert-to-home-install.sh goes back to it).
#
# LAYERHOUND_DEV_DEPLOY=1 (deploy.sh does this) also lets the owner's account install code from
# ~/layerhound-src without a password, for quick deploys from a development computer.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"      # where this copy of LayerHound came from
APP_DIR=/opt/layerhound
DATA_DIR=/var/lib/layerhound
CONF_DIR=/etc/layerhound
SVC_USER=layerhound
OWNER="${SUDO_USER:-$(id -un)}"
OWNER_HOME="$(getent passwd "$OWNER" | cut -d: -f6)"
LEGACY_DIR="$OWNER_HOME/layerhound"              # installs from before 1.4
PORT="${LAYERHOUND_PORT:-${TTRC_PORT:-$(cat "$CONF_DIR/port" 2>/dev/null || cat /var/lib/layerhound/port 2>/dev/null || echo 80)}}"
SERVICE=layerhound

# After renaming a board (hostnamectl), /etc/hosts may still list the old name, which makes
# sudo print "unable to resolve host". Add the current name if it's missing.
if ! grep -qE "[[:space:]]$(hostname)([[:space:]]|$)" /etc/hosts; then
  echo "127.0.1.1 $(hostname)" | sudo tee -a /etc/hosts >/dev/null
fi

echo "==> Installing system packages"
# Answer Debian's prompts automatically (e.g. "which services should be restarted?")
# NEEDRESTART_SUSPEND skips the long "outdated binaries" report after installing packages
APT="sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1 apt-get"
$APT update -qq
# avahi-daemon lets you reach the board as http://<hostname>.local
# smartmontools (smartctl) reads drive health for the Storage page
# iputils-ping and iproute2 are used by the Network page (ping checks, router address, scan)
# rsync puts the code in place
$APT install -y -qq python3 python3-venv python3-pip avahi-daemon smartmontools iputils-ping iproute2 curl rsync >/dev/null
# Announce the board's current name (it may have just been renamed) as <hostname>.local
sudo systemctl restart avahi-daemon

python3 -c "import sys; sys.exit(sys.version_info < (3, 10))" || { echo "!! Python 3.10 or newer is required" >&2; exit 1; }

echo "==> LayerHound's own account ($SVC_USER) and folders"
if ! id "$SVC_USER" >/dev/null 2>&1; then
  sudo useradd --system --user-group --home-dir "$DATA_DIR" --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
fi
# Docker container controls on the Services page: if the owner's account could use Docker, so can LayerHound
if getent group docker >/dev/null && id -nG "$OWNER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$SVC_USER"
fi
sudo mkdir -p "$DATA_DIR/data" "$DATA_DIR/files" "$CONF_DIR"
sudo chown "$SVC_USER:$SVC_USER" "$DATA_DIR" "$DATA_DIR/data" "$DATA_DIR/files"
sudo chmod 750 "$DATA_DIR"

echo "==> Code ($APP_DIR)"
sudo install -o root -g root -m 755 "$SRC_DIR/deploy/install-code.sh" /usr/local/sbin/layerhound-install-code
sudo /usr/local/sbin/layerhound-install-code "$SRC_DIR"

# Moving an install from before 1.4 (in the owner's home folder) over, once
LEGACY_DB=""
for db in "$LEGACY_DIR/backend/layerhound.db" "$LEGACY_DIR/backend/ttrc.db"; do [ -f "$db" ] && { LEGACY_DB="$db"; break; }; done
# Only once, and never over data that's already there: checked as root, because the owner's own
# account can't look inside LayerHound's data folder (a plain test would always say "no database"
# and copy the old database over the live one)
if [ -n "$LEGACY_DB" ] && [ "$LEGACY_DIR" != "$APP_DIR" ] \
   && ! sudo test -e "$DATA_DIR/layerhound.db" && ! sudo test -e "$DATA_DIR/MOVED-FROM"; then
  echo "==> Moving your printers, settings and data from $LEGACY_DIR to $DATA_DIR"
  sudo systemctl stop "$SERVICE" 2>/dev/null || true
  # A consistent copy of the database (it may have been written to just before stopping)
  sudo "$APP_DIR/backend/.venv/bin/python" - "$LEGACY_DB" "$DATA_DIR/layerhound.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
with dst: src.backup(dst)
print(f"   database: {dst.execute('SELECT COUNT(*) FROM printers').fetchone()[0]} printers")
PY
  # Encryption key, backups, problems, install ID, manufacturer list, ... (not the half-done update parts)
  [ -d "$LEGACY_DIR/backend/data" ] && sudo rsync -a --exclude 'updates/new' --exclude 'uploads' "$LEGACY_DIR/backend/data/" "$DATA_DIR/data/"
  [ -d "$OWNER_HOME/LayerHound Files" ] && sudo rsync -a "$OWNER_HOME/LayerHound Files/" "$DATA_DIR/files/"
  echo "moved from $LEGACY_DIR on $(date -u +%Y-%m-%dT%H:%MZ)" | sudo tee "$DATA_DIR/MOVED-FROM" >/dev/null
  echo "   The old folder $LEGACY_DIR is left as it was, as a fallback. Delete it once you're happy."
fi
sudo chown -R "$SVC_USER:$SVC_USER" "$DATA_DIR"
sudo find "$DATA_DIR/data" -name secret.key -exec chmod 600 {} +

# Drive health needs root, so allow exactly the read-only health command and nothing else.
# For quick deploys from a development computer (deploy.sh), also the code installer, for the owner.
SUDOERS=/etc/sudoers.d/layerhound
{
  echo "$SVC_USER ALL=(root) NOPASSWD: /usr/sbin/smartctl --json -a /dev/*"
  if [ -n "${LAYERHOUND_DEV_DEPLOY:-}" ]; then
    echo "$OWNER ALL=(root) NOPASSWD: /usr/local/sbin/layerhound-install-code $OWNER_HOME/layerhound-src"
    echo "$OWNER ALL=(root) NOPASSWD: $(command -v systemctl) restart $SERVICE.service"
  fi
  true
} | sudo tee "$SUDOERS.tmp" >/dev/null
sudo visudo -cf "$SUDOERS.tmp" >/dev/null && sudo install -m 440 "$SUDOERS.tmp" "$SUDOERS"; sudo rm -f "$SUDOERS.tmp"

# Wi-Fi settings on the Network page: let LayerHound's account (only) manage network connections
# through NetworkManager, without an admin password
POLKIT=/etc/polkit-1/rules.d/50-layerhound-network.rules
sudo tee "$POLKIT" >/dev/null <<POLKIT_RULE
// Installed by LayerHound's setup.sh: Wi-Fi settings in the dashboard
polkit.addRule(function(action, subject) {
  var allowed = ["org.freedesktop.NetworkManager.network-control",
                 "org.freedesktop.NetworkManager.settings.modify.system",
                 "org.freedesktop.NetworkManager.wifi.scan",
                 "org.freedesktop.NetworkManager.enable-disable-wifi",
                 "org.freedesktop.NetworkManager.wifi.share.open"];
  if (subject.user == "$SVC_USER" && allowed.indexOf(action.id) >= 0) return polkit.Result.YES;
});
POLKIT_RULE
sudo chmod 644 "$POLKIT"

# Setup hotspot: on LayerHound-Setup (and only there; it's the only "shared" connection),
# every web address points at the board, so phones open the setup page by themselves
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/#/10.42.0.1" | sudo tee /etc/NetworkManager/dnsmasq-shared.d/layerhound-setup.conf >/dev/null

# Remote access (remote.py, Settings -> Remote access): Tailscale, from Tailscale's official
# installer. It stays idle until the owner connects it. Installed on single-board computers only;
# on other machines LayerHound uses Tailscale if the owner already has it.
if ! command -v tailscale >/dev/null && [ -r /proc/device-tree/model ]; then
  echo "==> Installing Tailscale (for remote access; off until you connect it)"
  curl -fsSL --max-time 300 https://tailscale.com/install.sh | sudo sh >/dev/null \
    || echo "   (skipped: couldn't install Tailscale; run the install again later for remote access)"
fi
if command -v tailscale >/dev/null; then
  sudo systemctl enable --now --quiet tailscaled
  # Let LayerHound's account connect and disconnect Tailscale (only that), without root
  sudo tailscale set --operator="$SVC_USER" || echo "   (couldn't give LayerHound control of Tailscale)"
fi

echo "==> Manufacturer list for network discovery"
# Public IEEE list that maps device MAC addresses to manufacturers. Optional: discovery works without it.
OUI="$DATA_DIR/data/oui.csv"
if ! sudo test -s "$OUI" || [ -n "$(sudo find "$OUI" -mtime +90 2>/dev/null)" ]; then
  sudo -u "$SVC_USER" curl -fsSL --max-time 60 -o "$OUI.tmp" https://standards-oui.ieee.org/oui/oui.csv \
    && sudo -u "$SVC_USER" mv "$OUI.tmp" "$OUI" \
    || echo "   (skipped: couldn't download the list; device manufacturers won't be shown)"
fi

# Case fan speed (fan.py): let LayerHound's account set the fan's speed (only that), and put the
# fan back to full speed whenever the service stops, even if it crashed
sudo tee /etc/udev/rules.d/60-layerhound-fan.rules >/dev/null <<RULE
SUBSYSTEM=="hwmon", ATTR{name}=="pwmfan", RUN+="/bin/chgrp $SVC_USER /sys%p/pwm1", RUN+="/bin/chmod g+w /sys%p/pwm1"
RULE
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hwmon --attr-match=name=pwmfan --action=change || true
sudo tee /usr/local/sbin/layerhound-fan-full >/dev/null <<'SCRIPT'
#!/bin/sh
for d in /sys/class/hwmon/hwmon*; do
  [ "$(cat "$d/name" 2>/dev/null)" = pwmfan ] && echo 255 > "$d/pwm1"
done
exit 0
SCRIPT
sudo chmod 755 /usr/local/sbin/layerhound-fan-full

# Where the service finds its database and Files folder (also used by the updater and the
# "layerhound" command)
ENV_LINES="Environment=LAYERHOUND_DB=$DATA_DIR/layerhound.db
Environment=LAYERHOUND_FILES=$DATA_DIR/files
Environment=LAYERHOUND_PORT=$PORT"

# One-click updates (backend/updates.py, updater.py): a helper service that installs an update
# and restarts LayerHound, which LayerHound can't do to itself. It runs as root, because the code
# is root's; it checks the package's signature again itself before installing anything. The rule
# lets LayerHound's account start only this helper and restart only LayerHound.
sudo tee /etc/systemd/system/layerhound-updater.service >/dev/null <<EOF
[Unit]
Description=LayerHound updater (installs a signed update, rolls back if it fails)

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR/backend
$ENV_LINES
ExecStart=$APP_DIR/backend/.venv/bin/python $APP_DIR/backend/updater.py
TimeoutStartSec=45min
EOF
sudo tee /etc/polkit-1/rules.d/50-layerhound-updates.rules >/dev/null <<POLKIT_RULE
// Installed by LayerHound's setup.sh: one-click updates
polkit.addRule(function(action, subject) {
  if (action.id != "org.freedesktop.systemd1.manage-units" || subject.user != "$SVC_USER") return;
  var unit = action.lookup("unit"), verb = action.lookup("verb");
  if (unit == "layerhound-updater.service" && verb == "start") return polkit.Result.YES;
  if (unit == "$SERVICE.service" && verb == "restart") return polkit.Result.YES;
});
// Settings -> Shut down board (a clean power-off before unplugging)
polkit.addRule(function(action, subject) {
  if (subject.user == "$SVC_USER" && (action.id == "org.freedesktop.login1.power-off" ||
      action.id == "org.freedesktop.login1.power-off-multiple-sessions")) return polkit.Result.YES;
});
POLKIT_RULE
sudo chmod 644 /etc/polkit-1/rules.d/50-layerhound-updates.rules

# Owner tools on the board, e.g. "layerhound reset-password" for a forgotten password,
# or "layerhound hotspot start" to turn on the setup hotspot. They run as LayerHound's account
# (asking for your password for sudo), with the same database and data as the service.
sudo tee /usr/local/bin/layerhound >/dev/null <<CMD
#!/bin/sh
RUN="env LAYERHOUND_DB=$DATA_DIR/layerhound.db LAYERHOUND_FILES=$DATA_DIR/files $APP_DIR/backend/.venv/bin/python $APP_DIR/backend/manage.py"
if [ "\$(id -un)" = "$SVC_USER" ]; then exec \$RUN "\$@"; fi
exec sudo -u $SVC_USER \$RUN "\$@"
CMD
sudo chmod 755 /usr/local/bin/layerhound

# Another program (a web server, another app) may already use the port. LayerHound itself is fine:
# that's a reinstall or update.
if ! systemctl is-active --quiet "$SERVICE" && ss -ltnH "sport = :$PORT" 2>/dev/null | grep -q .; then
  echo "!! Port $PORT is already used by another program on this machine." >&2
  echo "   Choose another port: run the installer again with --port 8080 (or deploy with LAYERHOUND_PORT=8080)." >&2
  exit 1
fi

echo "==> systemd service ($SERVICE, port $PORT, running as $SVC_USER)"
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<EOF
[Unit]
Description=LayerHound print farm and home lab dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$DATA_DIR
ExecStart=$APP_DIR/backend/.venv/bin/uvicorn main:app --app-dir $APP_DIR/backend --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
# Tells LayerHound it runs as this service, which enables the Restart button in Settings
Environment=LAYERHOUND_SERVICE=1
$ENV_LINES
# Fan to full speed whenever LayerHound stops ("+" runs it as root)
ExecStopPost=+/usr/local/sbin/layerhound-fan-full
# Lets LayerHound listen on port 80 without running as root
AmbientCapabilities=CAP_NET_BIND_SERVICE
# Keep LayerHound away from everyone's home folders and its own temporary files private
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --quiet $SERVICE
sudo systemctl restart $SERVICE

# Startup takes a few seconds (database upgrades, loading Python). The very first start on a new
# board is slower (Python prepares its libraries, LayerHound creates its keys), so allow a minute.
echo "==> Waiting for LayerHound to start (the first start can take up to a minute)"
for _ in $(seq 60); do
  if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null; then
    URL="http://$(hostname).local"; [ "$PORT" = 80 ] || URL="$URL:$PORT"
    echo "==> Dashboard is running: $URL"
    # Record which setup was applied (as root, so it reflects what really ran); deploy.sh then
    # skips the full setup, and its password prompt, until setup.sh changes
    sha256sum "$SRC_DIR/deploy/setup.sh" | cut -d' ' -f1 | sudo tee "$CONF_DIR/setup.sha256" >/dev/null
    echo "$PORT" | sudo tee "$CONF_DIR/port" >/dev/null
    exit 0
  fi
  sleep 1
done
echo "!! Service did not answer within 60 seconds. Check the logs with: journalctl -u $SERVICE -n 50" >&2
exit 1
