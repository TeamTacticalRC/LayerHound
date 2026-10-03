# Roadmap

## When the ROCK 4D arrives
- Flash a Debian-based OS (Armbian or Radxa Debian), connect it to the network, and confirm `ssh` works from the Mac.
- Run `deploy/deploy.sh user@BOARD-HOSTNAME.local --with-db` (see README).
- Stop the dashboard on the Mac. The Bambu P1S accepts only one local connection.
- Check that the board's temperature sensors show up on the Server tab.
- As Home Assistant, Pi-hole and other apps are installed, add them on the Services page (with tokens for the extra stats). One-click suggestions add each Klipper printer's web page.
- Docker: after installing it, give the dashboard access with `sudo usermod -aG docker $USER` and restart the service. Note: Docker access is effectively admin access to the board, and it enables the container restart buttons. That's fine at home; for the product, keep it opt-in and behind login.
- Check that drive health (NVMe wear, temperature, hours) shows up on the Storage page.
- Optional: share TTRC Files to the Mac as a network drive (Samba).
- On the Network page, check that the router is found automatically and the Ethernet link speed shows.

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

**Decided (2026-10-01):** a separate Wi-Fi bar mounted by the printers. An ESP32 polls the dashboard API and drives an 8-LED NeoPixel Stick. Eight LEDs leave room for more printers, and other farm sizes if this is sold. It doesn't depend on the ROCK 4D, so it can be built and tested against the dashboard on the Mac.

#### Parts to order
| Part | Where | Price |
|---|---|---|
| ESP32 38-pin "narrow" board + matching screw-terminal breakout (DORHEA set). Check that the listing says "38-Pin Narrow… with Breakout Board". | [Amazon (ASIN B0C8HDDNLV)](https://www.amazon.com/dp/B0C8HDDNLV) or [Newegg 3-set](https://www.newegg.com/p/3C6-020A-01JA0) | ~$10–15 |
| NeoPixel Stick, 8 × 5050 RGB LEDs (Adafruit #1426) | [Adafruit](https://www.adafruit.com/product/1426) | $5.95 |
| 74AHCT125 level shifter (Adafruit #1787). Required: the LEDs need a stronger data signal than the ESP32's 3.3V. | [Adafruit](https://www.adafruit.com/product/1787) | $1.50 |
| Half-size breadboard + jumper wire bundle (Adafruit #3314) | [Adafruit](https://www.adafruit.com/product/3314) | $9.95 |
| Female/male jumper wires, 6" (Adafruit #1954) | [Adafruit](https://www.adafruit.com/product/1954) | $1.95 |
| USB power adapter (5V, 1A+) and a cable matching the ESP32 board (Micro-USB or USB-C) | On hand | — |

About $30–35 total. All the Adafruit parts can go in one order. Prices were checked on 2026-10-01.

#### Build notes
- Solder three wires to the stick's input pads: **5V**, **GND** and **DIN** (data in). Use the input side, not DOUT.
- Rough wiring: the stick's 5V and GND go to the ESP32's 5V/VIN and GND. The 74AHCT125 is powered from 5V/GND, with its 1OE pin to GND. An ESP32 data pin goes to the chip's 1A pin, and the chip's 1Y pin goes to the stick's DIN. Make a proper wiring diagram when building.
- At status-light brightness, 8 LEDs draw well under what USB power provides.
- Design a 3D-printed bar with a diffuser (translucent PETG or white PLA over the LEDs) and printer labels.
- Software: a small read-only status endpoint on the dashboard and ESP32 firmware that polls it. Once login exists, the bar uses a read-only access key (see the Login plan).

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
- [x] **Remove hardcoded personal details:** the LayerHound name and logo are fixed product branding (2026-10-02); each install sets its own **farm name** in Settings, shown under the logo, as the main heading and in the browser tab. The first-run welcome screen asks for it (v0.5.0).
- [x] **Login** (v0.5.0, 2026-10-02): see the Login plan below.
- [x] **Encrypt stored secrets** (2026-10-02): printer access codes, API keys and service tokens are encrypted in the database (`backend/vault.py`, using the `cryptography` package). The key is in `backend/data/secret.key` (owner-only), never in the database, so a copied database file doesn't reveal them. Backups with secrets hold them in plain text so they can be restored onto another board.
- [ ] **Updates** (planned 2026-10-02). Today the board only updates when `deploy/deploy.sh` is run from the Mac; it never fetches anything itself. Customers need the board to update on its own, in stages:
  - [ ] **Stage 1: update check (do first, about an hour once Releases exist).** Once a day the board asks GitHub for the latest release, and Settings → About shows "Update available: vX.Y.Z" with the release notes and a link. It only reads public release information. It helps Kyle and early testers know when a deploy is due, before automatic installs exist.
  - [ ] **Stage 2: one-click update.** An **Update now** button in Settings that downloads the release, **verifies its signature** (see Signed updates), backs up the database, installs the new version next to the old one, restarts, and checks the dashboard comes back. If it doesn't, it **rolls back** automatically.
  - [ ] **Stage 3: optional automatic updates** overnight, off by default, with a setting to choose.
  - Requires **pre-built releases** (above): GitHub Actions builds each tagged version with a checksum and signature.
- [ ] **Licensing:** choose a license for this code. Review paho-mqtt's license terms if it will be sold closed-source.
- [ ] **Bambu risk:** Bambu keeps tightening third-party access in firmware updates. Be upfront with customers that Bambu support could stop working.

### Login plan
Built in v0.5.0 (2026-10-02), including encrypting the stored printer secrets.

- **First-run setup:** a fresh install opens a "Create your admin account" screen. There are no default passwords.
- **Passwords:** store only a one-way hash (scrypt, built into Python; no new dependency).
- **Sessions:** a long random session ID in a cookie that page scripts can't read (HttpOnly, SameSite). "Keep me signed in" lasts 30 days; otherwise the session ends when the browser closes. Logout ends it immediately. Every API endpoint requires a session except login, setup and `/api/health`.
- **Roles:** Admin (everything, including restarting Docker containers and managing files) and Viewer (read-only, for employees or a shop display).
- **Access keys:** read-only keys for devices that can't type a password (the LED status bar, a wall display). Admins create and revoke them in Settings.
- **Brute-force protection:** after 5 wrong passwords, pause logins from that device for a few minutes.
- **Password reset:** `layerhound reset-password` on the board. Being able to log into the board proves ownership.
- **Viewing:** login required by default. A setting lets anyone on the local network view without logging in (for a shop wall screen). Changing anything always requires an admin login.
- **Cross-site protection:** every change must carry an `X-Requested-With` header, which a form on another website can't add.
- **HTTPS:** plain `http://` on the local network is acceptable. Document clearly that the dashboard's port must never be exposed to the internet, and recommend Tailscale for remote access. Optional built-in HTTPS can come later.

## Release & security process
Open source means anyone can read and fork the code, but only people with write access can change this repository. **The maintainer's review is the release gate.** Added 2026-10-02.

### In place
- [x] **Automated tests** (`backend/tests`): API, validation, file-folder escape protection, secrets never returned, backups and settings. Run with `cd backend && .venv/bin/python -m pytest -q tests`.
- [x] **Checks workflow** (`.github/workflows/checks.yml`): every pull request and push to `main` runs the backend tests (Python 3.10 and 3.12), the frontend build and a deploy-script check.
- [x] **CodeQL security scanning** (`.github/workflows/codeql.yml`): switches on automatically when the repository is public (free for public repos), and runs weekly.
- [x] **Dependabot** (`.github/dependabot.yml`): weekly update pull requests for npm and Python packages, monthly for GitHub Actions. Each one still needs to pass checks and your review.
- [x] **`SECURITY.md`**: how to report a vulnerability privately.

### To do
- [x] **2FA and a passkey** on the TeamTacticalRC GitHub account (2026-10-02). Keep the recovery codes somewhere safe off the computer.
- [ ] **2FA on the email account** connected to GitHub, since it can be used to reset access.
- [ ] **Branch protection on `main`**: require a pull request with passing checks, and block force-pushes and deletion. Free once the repository is public; private repositories need a paid GitHub plan.
- [ ] **Enable** Dependabot alerts, secret scanning and private vulnerability reporting under the repository's Settings → Code security, as each becomes available.
- [ ] **Review rules for contributions:** read every pull request, with extra care for the installer, updates, network calls, file paths and anything that runs commands. Ask for small pull requests. Don't hand out write access quickly; for now, only the maintainer merges.
- [ ] **Official releases built by GitHub Actions** from tagged versions, with checksums (and later signatures) so anyone can verify a download came from this repository.
- [ ] **Signed updates:** when automatic updates exist, boards only install updates signed with the project's key. Otherwise a compromised download server could take over every board.
- [ ] **Frontend tests** for key screens, alongside the backend tests.

## Branding & business
Plan: free **open-source software**, plus a **pre-built plug-and-play board** sold by Team Tactical RC. This is the Home Assistant model (open software, with Home Assistant Green hardware for people who want it ready to go).

### Decisions
- [x] **Product name: LayerHound** (chosen 2026-10-01). Team Tactical RC stays the maker: "LayerHound by Team Tactical RC".
- [ ] **License:** recommended **AGPL-3.0**. Anyone who modifies it and offers it to others, even as a hosted service, must share their changes. All current dependencies (FastAPI, React, paho-mqtt, psutil, lucide) are compatible.
- [ ] **Trademark: deferred (decided 2026-10-02).** Registering costs about $1,000 in USPTO fees (two classes: 9 and 42, intent-to-use) plus $500–$2,000 for an attorney. Until it's worth it, rely on common-law rights from using the name: mark it **LayerHound™**, keep proof of first-use dates (GitHub history from 2026-10-01, domain registration, first posts and first sale), and revisit filing if sales take off. Risk accepted: someone else could register a similar name first.
- [ ] **Legal check (optional for now):** if the budget allows before launch, a short attorney consult on the license, the AI-generated logo and trademark risk.
- [ ] **Disclaimers:** "not affiliated with" Bambu Lab, Klipper, OctoPrint and others. Don't use their logos.

### Name shortlist (first-pass check on 2026-10-01)
Every name below had an unregistered .com (per whois), a free GitHub name, and no matching product found in a web search. This is **not** a trademark search: check the USPTO database (and with the attorney) before committing, and register the domain as soon as you decide.

| Name | Notes |
|---|---|
| **LayerHound** | Recommended. Distinctive, so it's a stronger trademark. A "hound that watches your printers" mascot works well for a logo and the 3D-printed enclosure. |
| **Fleetbed** | Coined ("fleet of printers" + "print bed"). Distinctive, but needs a moment to explain. |
| **FarmGlance** | Clear meaning (glance at your print farm), but "farm" can read as agriculture. |
| HotbedHQ | "Hotbed" is a common 3D-printing term, which makes a weaker trademark. |
| NozzleWatch | Descriptive and printer-only; the product also monitors servers, network and services. |
| SpoolSight | Too close to an existing 3D printing app, SpoolSense. |

Taken or in use when checked: FarmDeck, LayerWatch, Spoolhouse, PrintHQ, PrintHound, SpoolHound, FarmSight, PrintRadar, LayerLens, Farmlight and others.

### LayerHound launch checklist
- [ ] **Register `layerhound.com`** (and ideally `.io`) and social handles. They were unclaimed on 2026-10-01; do this first.
- [ ] **USPTO trademark filing:** deferred (see Decisions). If revisited: search first, file the plain-text name LAYERHOUND, and use the USPTO's pre-approved wording to avoid surcharges.
- [x] Rename in the code (done 2026-10-01): LayerHound is the default branding, the files folder is `~/LayerHound Files`, settings use `LAYERHOUND_*` (old `TTRC_*` names still work), the service and install folder are `layerhound`, and backups are `layerhound-backup-*.json` (old backups still restore). This install keeps Team Tactical RC branding in Settings.
- [x] Project folder renamed to `~/Downloads/layerhound` (2026-10-01).
- [ ] GitHub: the repository is at [TeamTacticalRC/LayerHound](https://github.com/TeamTacticalRC/LayerHound) (private). Optionally also claim a `layerhound` organization name to protect it.
- [ ] Add `LICENSE` (AGPL-3.0), a trademark policy and a contributing guide.
- [ ] Logo and simple brand guide (name usage, colors; the accent color system already exists).

### Plug-and-play board
- [ ] **Hardware:** the board (currently ROCK 4D; confirm long-term availability), a 3D-printed enclosure from the farm (first draft with a 40 mm fan: `hardware/case/`, 2026-10-02, not test-printed yet), a power supply, and the LED status bar as an optional add-on.
- [ ] **First boot:** plug in Ethernet and power, open `http://[product].local`, and a setup screen asks for a name, admin password (see Login plan) and printers. The network scan makes adding printers nearly automatic.
- [x] **No-cable Wi-Fi setup (setup hotspot)** (built 2026-10-02, needs a real-phone test on the board). When the board has no network for 3 minutes (45 seconds if it was never set up), it creates an open Wi-Fi network, **"LayerHound-Setup"**. Joining it from a phone opens the setup page automatically (captive portal): pick the home Wi-Fi and, on a new board, name the farm and create the admin account. Once accounts exist, changing Wi-Fi there needs an admin sign-in. The board then joins the network and deletes the hotspot profile; a wrong password brings the hotspot back with the error. While on, it retries the saved Wi-Fi every 5 minutes when no phone is connected, and it turns off when a cable is plugged in. `layerhound hotspot start|stop` turns it on by hand (it turns itself off after 30 minutes). Code: `backend/hotspot.py`; DNS redirect and permission in `deploy/setup.sh`.
- [ ] **Updates** that work for devices in the field (ties into Update checks above).
- [ ] **Compliance:** check FCC requirements for the finished product (using a pre-certified board helps).
- [ ] **Business:** price (Home Assistant Green is roughly $100–130 for reference), warranty, returns and support.
