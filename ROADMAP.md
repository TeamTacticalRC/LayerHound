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

**Update (2026-10-09): the main light is a 12-LED ring** for the desk (an arc per printer, filling with progress, errors blinking red), in a housing styled like the LayerHound logo; the 8-LED bar stays as an option for mounting by the printers. Same ESP32, wiring and firmware.

**Decided (2026-10-01):** a separate Wi-Fi bar mounted by the printers. An ESP32 polls the dashboard API and drives an 8-LED NeoPixel Stick. Eight LEDs leave room for more printers, and other farm sizes if this is sold. It doesn't depend on the ROCK 4D, so it can be built and tested against the dashboard on the Mac.

#### Parts to order
| Part | Where | Price |
|---|---|---|
| ESP32 38-pin "narrow" board + matching screw-terminal breakout (DORHEA set). Check that the listing says "38-Pin Narrow… with Breakout Board". | [Amazon (ASIN B0C8HDDNLV)](https://www.amazon.com/dp/B0C8HDDNLV) or [Newegg 3-set](https://www.newegg.com/p/3C6-020A-01JA0) | ~$10–15 |
| NeoPixel Ring, 12 × 5050 RGB LEDs (Adafruit #1643). **The main LayerHound light** (decided 2026-10-09): a desk/shelf status ring, an arc per printer. | [Adafruit](https://www.adafruit.com/product/1643) | $8.95 |
| NeoPixel Stick, 8 × 5050 RGB LEDs (Adafruit #1426). The bar option, for lights mounted by the printers; worth getting too, to test both. | [Adafruit](https://www.adafruit.com/product/1426) | $5.95 |
| 74AHCT125 level shifter, DIP-14 (the same chip as Adafruit #1787, which was out of stock on 2026-10-09). Required: the LEDs need a stronger data signal than the ESP32's 3.3V. Check the listing says **SN74AHCT125N** (AHCT, not HC). | [Amazon: Juried Engineering SN74AHCT125N, 5-pack](https://www.amazon.com/Juried-Engineering-SN74AHCT125N-SN74AHCT125-Breadboard-Friendly/dp/B08FHD994N) (or [Adafruit #1787](https://www.adafruit.com/product/1787) when back in stock) | ~$5–8 |
| Half-size breadboard + jumper wire bundle (Adafruit #3314) | [Adafruit](https://www.adafruit.com/product/3314) | $9.95 |
| Female/male jumper wires, 6" (Adafruit #1954) | [Adafruit](https://www.adafruit.com/product/1954) | $1.95 |
| 470 Ω resistors, 1/4 W. One goes on the data wire, just before the stick's DIN pad, to clean up the signal. | [Amazon: E-Projects 10-pack](https://www.amazon.com/Projects-Resistors-Watt-Choose-Quantity/dp/B071NRWXFS) (or Adafruit #2781, pack of 25) | ~$1 |
| 1000 µF electrolytic capacitor, 6.3 V or higher (10 V or 16 V is fine). Goes across the stick's 5V and GND to protect the LEDs when power is plugged in. **Polarity matters:** the stripe (−) goes to GND. Adafruit doesn't stock this size. | [Amazon: E-Projects 1000 µF 16 V, 5-pack](https://www.amazon.com/Projects-Radial-Electrolytic-Capacitor-1000uF/dp/B07YN6DS58) | ~$1–2 |
| Perma-Proto half-size board (Adafruit #1609, or the 3-pack #571). Same layout as the breadboard: once the prototype works, solder the same parts into the same holes for a permanent bar. Not needed for the first prototype. | [Adafruit single](https://www.adafruit.com/product/1609) or [3-pack](https://www.adafruit.com/product/571) | ~$4.50 |
| USB power adapter (5V, 1A+) and a cable matching the ESP32 board (Micro-USB or USB-C). The cable must carry **data**, not just charge, so firmware can be loaded from the Mac. | On hand | — |

About $35–40 total. All the Adafruit parts can go in one order. Prices were checked on 2026-10-01 (the resistor, capacitor and Perma-Proto rows were added 2026-10-09; the single Perma-Proto showed out of stock then, so check, or get the 3-pack).

**Breadboard vs. production:** the breadboard is for prototyping only (parts held by friction). A permanent bar uses the Perma-Proto board. Selling bars in quantity would mean a custom circuit board (ESP32 module, level shifter, capacitor, resistor, USB-C and the 8 LEDs on one board, shaped for the housing) made and assembled by a fab such as JLCPCB or PCBWay; using a pre-certified ESP32 module also simplifies the FCC check.

#### Build notes
- Solder three wires to the stick's input pads: **5V**, **GND** and **DIN** (data in). Use the input side, not DOUT.
- Rough wiring: the stick's 5V and GND go to the ESP32's 5V/VIN and GND, with the 1000 µF capacitor across them near the stick. The 74AHCT125 is powered from 5V/GND, with its 1OE pin to GND. An ESP32 data pin goes to the chip's 1A pin, and the chip's 1Y pin goes through the 470 Ω resistor to the stick's DIN. Make a proper wiring diagram when building.
- At status-light brightness, 8 LEDs draw well under what USB power provides.
- Design a 3D-printed bar with a diffuser (translucent PETG or white PLA over the LEDs) and printer labels.
- [x] **Software** (built 2026-10-09, not yet tried on hardware): `GET /api/lightbar` (`backend/lightbar.py`) gives the 8 LEDs' colors and effects in Print Farm order, read with a read-only access key; now 12-LED ring (main) or 8-LED bar. An **Add-ons** page (admins only, sidebar above Send feedback; 2026-10-09) has a card per shape: example preview, **I have one**, **Build your own** (GitHub guide) and a **Get one** store link, hidden until the light is listed on ttrc.us (set `buyUrl` in `ADDONS` in `src/main.jsx`). Owned or detected lights get a live preview, Connected/last-seen (a light checking in with its access key is noticed and marked owned), brightness and reverse order. ESP32 firmware in `hardware/lightbar/firmware` (PlatformIO): setup page on its own Wi-Fi network (LayerHound-Light) for Wi-Fi, address and key; finds `layerhound.local` by mDNS; purple status patterns when it can't show printers. Wiring and setup in `hardware/lightbar/README.md`.

## Packaging for release
Goal: make installing as easy as possible for other people, once it's proven on the ROCK 4D.

**Decide first:** sell it, or release it free/open source (with donations or paid extras)? Free makes distribution easy through a public GitHub repository. Selling means private downloads and probably license keys.

### Install options
- **One-line installer (lead with this):** `curl -fsSL https://.../install.sh | bash`. It downloads the latest release and installs it on Debian-based systems (Raspberry Pi OS, Armbian, Ubuntu). Build it from `deploy/setup.sh`.
- **Docker image:** a multi-architecture image (arm64 and amd64) plus a `docker compose` file for home lab users.
- **SD card image:** skip at first. It needs a separate image per board model and a rebuild for every update.

### v1.0 release checklist (decided 2026-10-04)
The main repo goes public at v1.0 (it provides the AGPL source). In order:
- [x] Kyle's own testing, plus an automated UI walkthrough (now `tests/ui/`).
- [x] Fresh screenshots for the README (2026-10-04: dark and light dashboard, History, Server, Network, Services, Settings; private details replaced).
- [x] **Scrubbed the home Wi-Fi name from git history** (2026-10-04): rewritten with `git filter-repo --replace-text` (52 commits, latest files unchanged), force-pushed, and Dependabot asked to recreate its PRs on the new history. A backup of the old history is in `~/.layerhound/backups/` on the Mac. A pre-public audit found nothing else: no database, keys, tokens, access codes or personal email in any commit.
- [x] **v1.0.0 published** (2026-10-04) with `scripts/release.py`: built, tested, signed, verified from outside.
- [x] **Fresh install with the real one-liner** on a re-flashed SD card (2026-10-05): download, signature check, rename, setup, all passed.
- [x] **First real one-click update**: the main board went 0.5.0 → 1.0.0 with Update now (2026-10-04, about 5 s, all printers reconnected), so no v1.0.1 was needed for the test.
- [x] **Public** (2026-10-05): old repo renamed to private `LayerHound-archive`; new public `TeamTacticalRC/LayerHound` with the clean history and `v1.0.0` tag. Dependabot alerts and security updates, secret scanning with push protection, private vulnerability reporting and branch protection on `main` are on. CodeQL's first findings (TLS version, error details) and a pytest advisory were fixed the same day; all scans at 0 open alerts.
- [x] Releases README links to the public source (2026-10-05).
- [ ] **Announce** (Kyle).

### Work needed
- [x] **Pre-built releases** (2026-10-04): `scripts/release.py` builds, signs and publishes each version (dashboard already built), so owners don't need Node.js. **One-line installer** `deploy/install.sh` (published with every release) downloads the latest release, checks its checksum and signature, installs and runs the board setup. Fresh-board install tested end to end on 2026-10-04 (new SD card: install, rename, setup, setup hotspot from a phone).
- [x] **Runs on any Debian-based PC too** (2026-10-05): `install.sh --port N` for machines where port 80 is taken (setup stops with a clear message if the port is in use), and the setup hotspot is board-only by default (Settings → Setup hotspot: Auto/On/Off; Auto = on when Linux reports a single-board computer model).
- [x] **Printer suggestions** (2026-10-05, `backend/discovery.py`): scans after first-run setup and daily (switchable), plus Bambu's own network announcements (UDP 2021); found printers appear on the Dashboard and Print Farm. One click for Klipper, the access code for Bambu, OctoPrint's "Allow" flow (Application Keys). Never added silently unless the owner turns on auto-add for Klipper (off by default: shared networks).
- [x] **Docker image** (2026-10-05): `Dockerfile` and `docker-compose.yml` for other Linux systems, NAS boxes (Unraid, Synology, TrueNAS) and Docker Desktop. Non-root, data in a `/data` volume, host networking recommended. GitHub builds and tests it on every push (including the browser tests against the container) and publishes `ghcr.io/teamtacticalrc/layerhound` for Intel/AMD and ARM on each release tag. Board-only features hide themselves; updates are by pulling the image.
- [x] **Optional usage stats** (2026-10-06, `backend/stats.py`): opt-in (asked at first-run setup and once on existing installs; nothing sent until yes). Daily: random install ID, version, install type, board, printer counts by type, two-letter country from the existing Cloudflare check. To Team Tactical RC's "LayerHound usage stats" Google Form; count active farms (distinct install IDs in the last 30 days), printers and countries in its Sheet.
- [x] **Remote access with Tailscale** (built 2026-10-09, for v1.3.0): board setup installs Tailscale (idle) and makes LayerHound its operator; Settings → Remote access connects it to the owner's own Tailscale account with Tailscale's sign-in link and a QR code, then shows the board's `ts.net` address and its QR code, phone steps and the key-expiry tip. Turn off / sign out. Tailscale DNS left off. Board only (Docker and PC owners use their own Tailscale). Changes `deploy/setup.sh`, so v1.3.0 needs `--needs-setup`.
- [x] **Printer controls, phase 1** (2026-10-09): pause / resume / cancel from a printing printer's detail panel. Off by default (Settings → Printer controls), admins only, confirmed first, logged. Klipper (Moonraker `/printer/print/*`), OctoPrint (`/api/job`), Bambu (MQTT `pause`/`resume`/`stop` on the existing connection; the printer's reply is checked, and newer firmware's refusal outside LAN Only / Developer mode is explained). Not yet tried on real printers.
- [ ] **Printer controls, phase 2:** upload a sliced file and start it, with a "bed is clear" confirmation and the camera snapshot shown first. Klipper and OctoPrint first; Bambu (FTPS upload + MQTT start) last. Skip jogging/temperatures/fans: link to each printer's own page instead.
- [ ] **Native Windows version** only if people ask (Send feedback): a Windows service and updater, a Windows installer, and Windows versions of the ping, device-table and route lookups. WSL2 with mirrored networking runs the Linux installer meanwhile.
- [ ] **Proper install location:** install to `/opt` under a dedicated system user, with a standard service setup. Updates must keep the buyer's printer list and upgrade the database.
- [x] **Remove hardcoded personal details:** the LayerHound name and logo are fixed product branding (2026-10-02); each install sets its own **farm name** in Settings, shown under the logo, as the main heading and in the browser tab. The first-run welcome screen asks for it (v0.5.0).
- [x] **Login** (v0.5.0, 2026-10-02): see the Login plan below.
- [x] **Encrypt stored secrets** (2026-10-02): printer access codes, API keys and service tokens are encrypted in the database (`backend/vault.py`, using the `cryptography` package). The key is in `backend/data/secret.key` (owner-only), never in the database, so a copied database file doesn't reveal them. Backups with secrets hold them in plain text so they can be restored onto another board.
- [ ] **Updates** (planned 2026-10-02; stages 1 and 2 built 2026-10-04). Today the board only updates when `deploy/deploy.sh` is run from the Mac; it never fetches anything itself. Customers need the board to update on its own, in stages:
  - [x] **Stage 1: update check.** Once a day (switchable) the board asks the public releases repo, **TeamTacticalRC/layerhound-releases**, for the latest release; Settings → Updates shows it with the release notes, plus **Check now**.
  - [x] **Stage 2: one-click update.** **Update now** downloads the package, checks its SHA-256 and **Ed25519 signature** (release key in `~/.layerhound/release-signing.key` on the Mac only; public key in `backend/updates.py`), then `layerhound-updater.service` backs up the database, installs, restarts and **rolls back** automatically if the new version doesn't start. Releases that change `deploy/setup.sh` are marked "needs setup" and must be deployed instead. Publish with `scripts/release.py` (see RELEASING.md).
  - [x] **Stage 3: optional automatic updates** (2026-10-07): Settings → Updates → Install updates automatically, off by default, at an hour the owner picks in their own time zone (saved from the browser, since boards run on UTC). Checked every 10 minutes; at most once a day; same download, signature check, backup and rollback as Update now. A version that failed isn't retried automatically, and releases that need setup are left for the owner. Board installs only (not Docker).
  - Releases are built and signed on the Mac by `scripts/release.py`, not by GitHub Actions, so the signing key never leaves the Mac.
- [x] **Licensing** (2026-10-04): **AGPL-3.0** (`LICENSE`); the name, logo and mascot are excluded (`TRADEMARKS.md`). All dependencies are compatible (paho-mqtt is dual-licensed EPL-2.0/EDL-1.0).
- [x] **Bambu risk** (noted in the README and owner's guide): Bambu keeps tightening third-party access in firmware updates. Be upfront with customers that Bambu support could stop working.

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
- [x] **Branch protection on `main`** (2026-10-05): require a pull request with passing checks, and block force-pushes and deletion. Free once the repository is public; private repositories need a paid GitHub plan.
- [x] **Enabled** (2026-10-05) Dependabot alerts, secret scanning and private vulnerability reporting under the repository's Settings → Code security, as each becomes available.
- [ ] **Review rules for contributions:** read every pull request, with extra care for the installer, updates, network calls, file paths and anything that runs commands. Ask for small pull requests. Don't hand out write access quickly; for now, only the maintainer merges.
- [x] **Official releases** with checksums and signatures, built and signed on the release Mac by `scripts/release.py` (not GitHub Actions, so the signing key never leaves the Mac).
- [x] **Signed updates** (2026-10-04, Ed25519): when automatic updates exist, boards only install updates signed with the project's key. Otherwise a compromised download server could take over every board.
- [x] **Frontend tests** (2026-10-04, `tests/ui/`): a real browser checks first-run setup, every page in dark/light at desktop/phone sizes, adding and removing a printer, the theme choice, sign-out, and that view-only accounts see no admin controls. Run on every push and by `scripts/release.py`.

## Branding & business
Plan: free **open-source software**, plus a **pre-built plug-and-play board** sold by Team Tactical RC. This is the Home Assistant model (open software, with Home Assistant Green hardware for people who want it ready to go).

### Decisions
- [x] **Product name: LayerHound** (chosen 2026-10-01). Team Tactical RC stays the maker: "LayerHound by Team Tactical RC".
- [x] **License:** **AGPL-3.0**, chosen 2026-10-04. Anyone who modifies it and offers it to others, even as a hosted service, must share their changes. All current dependencies (FastAPI, React, paho-mqtt, psutil, lucide) are compatible.
- [ ] **Trademark: deferred (decided 2026-10-02).** Registering costs about $1,000 in USPTO fees (two classes: 9 and 42, intent-to-use) plus $500–$2,000 for an attorney. Until it's worth it, rely on common-law rights from using the name: mark it **LayerHound™**, keep proof of first-use dates (GitHub history from 2026-10-01, domain registration, first posts and first sale), and revisit filing if sales take off. Risk accepted: someone else could register a similar name first.
- [ ] **Legal check (optional for now):** if the budget allows before launch, a short attorney consult on the license, the AI-generated logo and trademark risk.
- [x] **Disclaimers** (README and owner's guide): "not affiliated with" Bambu Lab, Klipper, OctoPrint and others. Don't use their logos.

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
- [ ] GitHub: the repository is at [TeamTacticalRC/LayerHound](https://github.com/TeamTacticalRC/LayerHound) (public since 2026-10-05). Optionally also claim a `layerhound` organization name to protect it.
- [x] Add `LICENSE` (AGPL-3.0) and a trademark policy (`TRADEMARKS.md`), 2026-10-04.
- [ ] Contributing guide. If outside contributions are accepted, use a contributor agreement so Team Tactical RC can still offer other licenses later.
- [ ] Logo and simple brand guide (name usage, colors; the accent color system already exists).

### Plug-and-play board
- [ ] **Hardware:** the board (currently ROCK 4D; confirm long-term availability), a 3D-printed enclosure from the farm (with a 40 mm fan: `hardware/case/`, designed 2026-10-02; test print fit confirmed 2026-10-04; version 2 on 2026-10-05 makes room for fan bolts and nuts: fan moved 6.5 mm left, case 4 mm deeper; version 3 on 2026-10-06, test printed 2026-10-07: full-footprint base that braces the port wall, pockets for 3M Bumpon SJ5302 feet, looser screw pilot holes), a power supply, and the LED status bar as an optional add-on.
- [ ] **Case fan for production:** order 40 × 40 × 10 mm 5 V fans pre-terminated with a **2-pin 1.25 mm plug** (fits the ROCK 4D's fan header) and a set wire length, so no splicing is needed. For now the prototypes use common 4010 5 V fans with a 1.25 mm pigtail soldered on. Check plug polarity against Radxa's fan header page.
- [x] **Fan speed by temperature** (2026-10-04, `backend/fan.py`): on the ROCK 4D's fan header, LayerHound runs the fan at a quiet minimum up to 45°C and speeds up evenly to full at 65°C (adjustable in Settings → Cooling fan, or set to always full). The Server page shows the fan speed. If LayerHound stops, crashes or can't read a temperature, the fan goes to full speed.
- [x] **First boot** (welcome screen built in v0.5.0): plug in Ethernet and power, open `http://[product].local`, and a setup screen asks for a name, admin password (see Login plan) and printers. The network scan makes adding printers nearly automatic.
- [x] **No-cable Wi-Fi setup (setup hotspot)** (built 2026-10-02; tested with a phone on a fresh board 2026-10-04). When the board has no network for 3 minutes (45 seconds if it was never set up), it creates an open Wi-Fi network, **"LayerHound-Setup"**. Joining it from a phone opens the setup page automatically (captive portal): pick the home Wi-Fi and, on a new board, name the farm and create the admin account. Once accounts exist, changing Wi-Fi there needs an admin sign-in. The board then joins the network and deletes the hotspot profile; a wrong password brings the hotspot back with the error. While on, it retries the saved Wi-Fi every 5 minutes when no phone is connected, and it turns off when a cable is plugged in. `layerhound hotspot start|stop` turns it on by hand (it turns itself off after 30 minutes). Code: `backend/hotspot.py`; DNS redirect and permission in `deploy/setup.sh`.
- [x] **Updates** that work for devices in the field: one-click signed updates with automatic rollback (see Updates above).
- [ ] **Compliance:** check FCC requirements for the finished product (using a pre-certified board helps).
- [ ] **Business:** price (Home Assistant Green is roughly $100–130 for reference), warranty, returns and support.
