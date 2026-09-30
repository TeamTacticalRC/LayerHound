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
sudo apt-get install -y -qq python3 python3-venv python3-pip avahi-daemon >/dev/null

python3 -c "import sys; sys.exit(sys.version_info < (3, 10))" || { echo "!! Python 3.10 or newer is required" >&2; exit 1; }

echo "==> Python environment"
cd "$APP_DIR/backend"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

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
