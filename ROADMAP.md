# Roadmap

## When the ROCK 4D arrives
- Flash a Debian-based OS (Armbian or Radxa Debian), connect it to the network, and confirm `ssh` works from the Mac.
- Run `deploy/deploy.sh user@BOARD-HOSTNAME.local --with-db` (see README).
- Stop the dashboard on the Mac. The Bambu P1S accepts only one local connection.
- Check that the board's temperature sensors show up on the Server tab.
- Turn the Docker, Home Assistant and Pi-hole entries in Services into real checks as each is installed.
- Check that drive health (NVMe wear, temperature, hours) shows up on the Storage page.
- Optional: share TTRC Files to the Mac as a network drive (Samba).

## After the server is fully running
### Printer status LED bar
Five LEDs, one per printer, in the dashboard's display order.

| State | LED |
|---|---|
| Printing | Green |
| Error or offline | Red |
| Paused (optional) | Amber |
| Finished (optional) | Blue |
| Idle (optional) | Dim |

Two options. Pick based on where the LEDs will sit:
- **On the ROCK 4D's 40-pin header:** APA102/SK9822 ("DotStar") LEDs driven over SPI, with a 74AHCT125 level shifter. Avoid WS2812/NeoPixel; the Raspberry Pi libraries for them don't work on Rockchip boards.
- **Separate Wi-Fi bar near the printers:** an ESP32 with 5 LEDs that polls the dashboard API. Works independently of the board's pins.

## Packaging for release
Goal: make installing as easy as possible for other people, once it's proven on the ROCK 4D.

**Decide first:** sell it, or release it free/open source (with donations or paid extras)? Free makes distribution easy through a public GitHub repository. Selling means private downloads and probably license keys.

### Install options
- **One-line installer (lead with this):** `curl -fsSL https://.../install.sh | bash`. It downloads the latest release and installs it on Debian-based systems (Raspberry Pi OS, Armbian, Ubuntu). Build it from `deploy/setup.sh`.
- **Docker image:** a multi-architecture image (arm64 and amd64) plus a `docker compose` file for home lab users.
- **SD card image:** skip at first. It needs a separate image per board model and a rebuild for every update.

### Work needed
- [ ] **Pre-built releases:** GitHub Actions builds the frontend on each version tag, so buyers don't need Node.js.
- [ ] **Proper install location:** install to `/opt` under a dedicated system user, with a standard service setup. Updates must keep the buyer's printer list and upgrade the database.
- [ ] **Remove hardcoded personal details:** the Team Tactical RC branding, ROCK 4D wording and the planned Docker, Home Assistant and Pi-hole services become settings or a first-run setup screen.
- [ ] **Security:** add login (see the Login plan below), and encrypt the stored access codes and API keys. Right now anyone on the network can edit or delete printers and upload, rename or delete files in TTRC Files.
- [ ] **Update checks:** tell the user when a new version is available.
- [ ] **Licensing:** choose a license for this code. Review paho-mqtt's license terms if it will be sold closed-source.
- [ ] **Bambu risk:** Bambu keeps tightening third-party access in firmware updates. Be upfront with customers that Bambu support could stop working.

### Login plan
About one focused session of work. Do it together with encrypting the stored printer secrets.

- **First-run setup:** a fresh install opens a "Create your admin account" screen. There are no default passwords.
- **Passwords:** store only a one-way hash (scrypt, built into Python; no new dependency).
- **Sessions:** a long random session ID in a cookie that page scripts can't read (HttpOnly, SameSite). "Keep me signed in" lasts 30 days; otherwise the session ends when the browser closes. Logout ends it immediately. Every API endpoint requires a session except login, setup and `/api/health`.
- **Roles:** Admin (everything) and Viewer (read-only, for employees or a shop display).
- **Access keys:** read-only keys for devices that can't type a password (the LED status bar, a wall display). Admins create and revoke them in Settings.
- **Brute-force protection:** after 5 wrong passwords, pause logins from that device for a few minutes.
- **Password reset:** a command on the board, e.g. `ttrc reset-password`. Being able to log into the board proves ownership.
- **Undecided:** should viewing require a login? Suggested default: required, with a setting to let anyone on the local network view without logging in. Changing anything always requires an admin login.
- **HTTPS:** plain `http://` on the local network is acceptable. Document clearly that the dashboard's port must never be exposed to the internet, and recommend Tailscale for remote access. Optional built-in HTTPS can come later.
