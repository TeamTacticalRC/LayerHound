#!/usr/bin/env bash
# Runs ON THE BOARD (deploy.sh calls it). Safe to run again after every update.
# Installs system packages, builds the Python environment and registers the
# dashboard as a systemd service that starts on boot and restarts on crashes.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(id -un)"
PORT="${LAYERHOUND_PORT:-${TTRC_PORT:-80}}"
SERVICE=layerhound

# After renaming a board (hostnamectl), /etc/hosts may still list the old name, which makes
# sudo print "unable to resolve host". Add the current name if it's missing.
if ! grep -qE "[[:space:]]$(hostname)([[:space:]]|$)" /etc/hosts; then
  echo "127.0.1.1 $(hostname)" | sudo tee -a /etc/hosts >/dev/null
fi

echo "==> Installing system packages"
# Answer Debian's prompts automatically (e.g. "which services should be restarted?")
APT="sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get"
$APT update -qq
# avahi-daemon lets you reach the board as http://<hostname>.local
# smartmontools (smartctl) reads drive health for the Storage page
# iputils-ping and iproute2 are used by the Network page (ping checks, router address, scan)
$APT install -y -qq python3 python3-venv python3-pip avahi-daemon smartmontools iputils-ping iproute2 curl >/dev/null

# Drive health needs root, so allow exactly the read-only health command and nothing else
SUDOERS=/etc/sudoers.d/layerhound
echo "$APP_USER ALL=(root) NOPASSWD: /usr/sbin/smartctl --json -a /dev/*" | sudo tee "$SUDOERS.tmp" >/dev/null
sudo visudo -cf "$SUDOERS.tmp" >/dev/null && sudo install -m 440 "$SUDOERS.tmp" "$SUDOERS"; sudo rm -f "$SUDOERS.tmp"

python3 -c "import sys; sys.exit(sys.version_info < (3, 10))" || { echo "!! Python 3.10 or newer is required" >&2; exit 1; }

# Wi-Fi settings on the Network page: let the LayerHound service account (only) manage
# network connections through NetworkManager, without an admin password
POLKIT=/etc/polkit-1/rules.d/50-layerhound-network.rules
sudo tee "$POLKIT" >/dev/null <<POLKIT_RULE
// Installed by LayerHound's setup.sh: Wi-Fi settings in the dashboard
polkit.addRule(function(action, subject) {
  var allowed = ["org.freedesktop.NetworkManager.network-control",
                 "org.freedesktop.NetworkManager.settings.modify.system",
                 "org.freedesktop.NetworkManager.wifi.scan",
                 "org.freedesktop.NetworkManager.enable-disable-wifi",
                 "org.freedesktop.NetworkManager.wifi.share.open"];
  if (subject.user == "$APP_USER" && allowed.indexOf(action.id) >= 0) return polkit.Result.YES;
});
POLKIT_RULE
sudo chmod 644 "$POLKIT"

# Setup hotspot: on LayerHound-Setup (and only there; it's the only "shared" connection),
# every web address points at the board, so phones open the setup page by themselves
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/#/10.42.0.1" | sudo tee /etc/NetworkManager/dnsmasq-shared.d/layerhound-setup.conf >/dev/null

echo "==> Python environment"
cd "$APP_DIR/backend"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Manufacturer list for network discovery"
# Public IEEE list that maps device MAC addresses to manufacturers. Optional: discovery works without it.
mkdir -p "$APP_DIR/backend/data"
if [ ! -s "$APP_DIR/backend/data/oui.csv" ] || [ -n "$(find "$APP_DIR/backend/data/oui.csv" -mtime +90)" ]; then
  curl -fsSL --max-time 60 -o "$APP_DIR/backend/data/oui.csv.tmp" https://standards-oui.ieee.org/oui/oui.csv \
    && mv "$APP_DIR/backend/data/oui.csv.tmp" "$APP_DIR/backend/data/oui.csv" \
    || echo "   (skipped: couldn't download the list; device manufacturers won't be shown)"
fi

# Owner tools on the board, e.g. "layerhound reset-password" for a forgotten password,
# or "layerhound hotspot start" to turn on the setup hotspot
sudo tee /usr/local/bin/layerhound >/dev/null <<CMD
#!/bin/sh
exec "$APP_DIR/backend/.venv/bin/python" "$APP_DIR/backend/manage.py" "\$@"
CMD
sudo chmod 755 /usr/local/bin/layerhound

echo "==> systemd service ($SERVICE, port $PORT)"
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<EOF
[Unit]
Description=LayerHound print farm and home lab dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR/backend
ExecStart=$APP_DIR/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
# Tells LayerHound it runs as this service, which enables the Restart button in Settings
Environment=LAYERHOUND_SERVICE=1
# Lets a normal user listen on port 80 without running as root
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --quiet $SERVICE
sudo systemctl restart $SERVICE

# Startup takes a few seconds on the board (database upgrades, loading Python), so keep checking for up to 20 seconds
for _ in $(seq 20); do
  if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null; then
    URL="http://$(hostname).local"; [ "$PORT" = 80 ] || URL="$URL:$PORT"
    echo "==> Dashboard is running: $URL"
    exit 0
  fi
  sleep 1
done
echo "!! Service did not answer within 20 seconds. Check the logs with: journalctl -u $SERVICE -n 50" >&2
exit 1
