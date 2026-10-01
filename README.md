# TTRC Home Lab Dashboard — v0.3

v0.3 adds a real printer registry and live, read-only printer monitoring.

**Supported:** Klipper via Moonraker, OctoPrint, and Bambu Lab (local MQTT).

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
In another terminal:
```bash
npm install
npm run dev
```
Open `http://localhost:5173`.

### Adding printers
Open **Print Farm → Add printer**.

Klipper/Moonraker is normally `http://PRINTER-IP:7125`.
OctoPrint is normally `http://PRINTER-IP:5000` and needs its API key.
Bambu Lab printers need the IP, serial number, and the 8-character access code from the printer's network (WLAN) settings. Some firmware versions also need LAN Only mode turned on.

This build intentionally does **not** expose printer controls yet. It establishes the connection/monitoring layer first.

The existing iMac DAS remains completely separate from this project.

### Running on the home lab board
The board runs a single process: the backend also serves the built dashboard, on port 80.

**First time**, on the board: install a Debian-based OS (e.g. Armbian or Debian 12), connect it to the network, and make sure you can `ssh` into it from the Mac.

**Deploy (first install and every update)**, from the Mac, in this folder:
```bash
deploy/deploy.sh user@BOARD-HOSTNAME.local --with-db
```
`--with-db` copies this Mac's printer list to the board. Leave it off for later updates so the board keeps its own list.

The script builds the frontend, copies the project to `~/ttrc-dashboard` on the board, and runs `deploy/setup.sh` there, which installs Python packages and a `ttrc-dashboard` systemd service (starts on boot, restarts on crashes). Then open `http://BOARD-HOSTNAME.local`.

The Storage page's **TTRC Files** folder is `~/TTRC Files` for the user the service runs as (set `TTRC_FILES` to use another location). It lives outside the app folder, so deploys never touch it. Drive health uses `smartctl`, which `setup.sh` installs along with a sudo rule limited to the read-only health command.

The Network page checks the internet and your monitored devices every minute and keeps 7 days of history. Network scans only cover the local network (at most 254 addresses) and only run when you press **Scan network**. `setup.sh` downloads the public IEEE manufacturer list (`backend/data/oui.csv`) so scans can name device makers.

Useful commands on the board:
```bash
systemctl status ttrc-dashboard
journalctl -u ttrc-dashboard -f
```

**Only run one copy at a time.** Bambu P1-series printers accept only one local connection, so once the board is live, stop the dashboard on the Mac or the P1S will show offline on one of them.
