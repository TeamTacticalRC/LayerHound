#!/usr/bin/env bash
# Runs ON THE BOARD (deploy.sh calls it). Safe to run again after every update.
# Installs system packages, builds the Python environment and registers the
# dashboard as a systemd service that starts on boot and restarts on crashes.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(id -un)"
PORT="${TTRC_PORT:-80}"
SERVICE=ttrc-dashboard

echo "==> Installing system packages"
sudo apt-get update -qq
# avahi-daemon lets you reach the board as http://<hostname>.local
# smartmontools (smartctl) reads drive health for the Storage page
# iputils-ping and iproute2 are used by the Network page (ping checks, router address, scan)
sudo apt-get install -y -qq python3 python3-venv python3-pip avahi-daemon smartmontools iputils-ping iproute2 curl >/dev/null

# Drive health needs root, so allow exactly the read-only health command and nothing else
SUDOERS=/etc/sudoers.d/ttrc-dashboard
echo "$APP_USER ALL=(root) NOPASSWD: /usr/sbin/smartctl --json -a /dev/*" | sudo tee "$SUDOERS.tmp" >/dev/null
sudo visudo -cf "$SUDOERS.tmp" >/dev/null && sudo install -m 440 "$SUDOERS.tmp" "$SUDOERS"; sudo rm -f "$SUDOERS.tmp"

python3 -c "import sys; sys.exit(sys.version_info < (3, 10))" || { echo "!! Python 3.10 or newer is required" >&2; exit 1; }

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

echo "==> systemd service ($SERVICE, port $PORT)"
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<EOF
[Unit]
Description=TTRC Home Lab Dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR/backend
ExecStart=$APP_DIR/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
# Lets a normal user listen on port 80 without running as root
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --quiet $SERVICE
sudo systemctl restart $SERVICE

sleep 2
if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  URL="http://$(hostname).local"; [ "$PORT" = 80 ] || URL="$URL:$PORT"
  echo "==> Dashboard is running: $URL"
else
  echo "!! Service did not answer yet. Check the logs with: journalctl -u $SERVICE -n 50" >&2
  exit 1
fi
