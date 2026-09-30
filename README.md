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
