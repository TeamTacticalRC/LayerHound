# Roadmap

## Where things stand (2026-10-12)

**Latest release: v1.4.0.** LayerHound is public, open source (AGPL-3.0) and released: one-line installer, Docker image, signed one-click and automatic updates. Main board: Radxa ROCK 4D, on v1.4.0.

**Next up**
- [ ] **Announce** (Kyle).
- [ ] **Status light** (its own release): software built, housing v1.1 printed; waiting on parts to wire and test. See [Status light](#status-light).
- [ ] **Starting prints on Bambu:** only if the printer is in LAN Only + Developer Mode (see [Printer controls](#printer-controls)).
- [ ] **Automatic crash reports** (opt-in, e.g. Sentry): decide after the announcement, once there's feedback to judge by.
- [ ] **LayerHound card:** a ready-to-use memory card image for the ROCK 4D (see [LayerHound card](#layerhound-card-bring-your-own-board)).
- [ ] **Native Windows version:** only if people ask (Send feedback). Meanwhile WSL2 with mirrored networking runs the Linux installer.
- [ ] Kyle's items: register `layerhound.com`, list LayerHound on ttrc.us and Etsy, brand guide, and the [LayerHound card](#layerhound-card-bring-your-own-board) business items.

## Status light

A small Wi-Fi light that shows what the printers are doing, so trouble is noticed without opening the dashboard. Its own release, once tested on hardware.

**Decided (2026-10-09): the main light is a 12-LED ring** for the desk: an arc per printer that fills with print progress, errors blinking red, in a housing styled like the LayerHound logo. An **8-LED bar** stays as an option, for mounting by the printers. Same ESP32, wiring and firmware for both. (Started 2026-10-01 as a five-, then eight-LED bar.)

| Printer | Light |
|---|---|
| Printing | Green (on the ring, the arc fills with progress) |
| Paused | Amber, pulsing |
| Finished | Blue |
| Idle | Dim white |
| Error | Red, blinking |
| Offline | Red |

**Status**
- [x] **Software** (2026-10-09): `GET /api/lightbar` (`backend/lightbar.py`) gives each LED's color and effect in Print Farm order, read with a read-only access key. ESP32 firmware in `hardware/lightbar/firmware` (PlatformIO, `ring` and `bar` builds): a setup page on its own Wi-Fi network (LayerHound-Light), finds `layerhound.local` by mDNS, purple self-status patterns. Compiles; not yet run on a real ESP32.
- [x] **Add-ons page** (2026-10-09): a card per shape with an example, **I have one**, **Build your own** and a **Get one** store link (hidden until it's listed on ttrc.us: set `buyUrl` in `ADDONS` in `src/main.jsx`). A light checking in is noticed and shown as Connected. **Hidden behind `ADDONS_RELEASED` in `src/main.jsx` until the light's release.**
- [x] **Ring housing** (`hardware/lightbar/housing`): v1 (2026-10-09) printed; v1.1 (2026-10-12, uncommitted on purpose until fit-tested) is sized for the measured ESP32 (48.3 × 26 mm, pins 8.5 mm), with roof fingers clamping the ESP32 and the level-shifter board, a perfboard pocket, a zip-tie anchor, and a 3-replug setup trigger in the firmware.
- [ ] **When the parts arrive:** load the firmware, wire it on the breadboard, check it against the farm, then fit-test the housing and make a real wiring diagram with photos.
- [ ] **Release:** turn on `ADDONS_RELEASED`, restore the Add-ons browser test (see `test_addons_page_hidden_until_the_light_is_released`), commit the ring-light work, release.

**Parts** (ordered 2026-10-09)

| Part | Where | Price |
|---|---|---|
| ESP32 38-pin "narrow" board + matching screw-terminal breakout (DORHEA set). The breakout is for prototyping; the finished light uses the bare board. | [Amazon (ASIN B0C8HDDNLV)](https://www.amazon.com/dp/B0C8HDDNLV) or [Newegg 3-set](https://www.newegg.com/p/3C6-020A-01JA0) | ~$10–15 |
| NeoPixel Ring, 12 × 5050 RGB LEDs (Adafruit #1643): **the main light** | [Adafruit](https://www.adafruit.com/product/1643) | $8.95 |
| NeoPixel Stick, 8 × 5050 RGB LEDs (Adafruit #1426): the bar option | [Adafruit](https://www.adafruit.com/product/1426) | $5.95 |
| 74AHCT125 level shifter, DIP-14. Required: the LEDs need a 5 V data signal, the ESP32 gives 3.3 V. Check the listing says **SN74AHCT125N** (AHCT). | [Amazon: Juried Engineering, 5-pack](https://www.amazon.com/Juried-Engineering-SN74AHCT125N-SN74AHCT125-Breadboard-Friendly/dp/B08FHD994N) (or [Adafruit #1787](https://www.adafruit.com/product/1787) when in stock) | ~$5–8 |
| Half-size breadboard + jumper wires (Adafruit #3314), female/male jumpers (#1954) | [Adafruit](https://www.adafruit.com/product/3314), [#1954](https://www.adafruit.com/product/1954) | ~$12 |
| 470 Ω resistor (data line) | [Amazon: E-Projects 10-pack](https://www.amazon.com/Projects-Resistors-Watt-Choose-Quantity/dp/B071NRWXFS) | ~$1 |
| 1000 µF capacitor, 6.3 V+ (across 5V/GND; **stripe to GND**) | [Amazon: E-Projects 5-pack](https://www.amazon.com/Projects-Radial-Electrolytic-Capacitor-1000uF/dp/B07YN6DS58) | ~$1–2 |
| Double-sided perfboard, cut to 26 × 40 mm for the level shifter (not stripboard) | e.g. [PAXCOO 40-piece kit](https://www.amazon.com/Paxcoo-Double-Sided-Board-Prototype/dp/B071P365J3) | ~$10 |
| USB power adapter (5 V, 1 A+) and a **data** USB cable | On hand | — |

Wiring, setup and loading the firmware: `hardware/lightbar/README.md`. Selling lights in quantity would mean a custom circuit board (ESP32 module, level shifter, capacitor, resistor, USB-C and the LEDs) from a fab such as JLCPCB or PCBWay; a pre-certified ESP32 module also simplifies the FCC check.

## Printer controls

Off by default; admins only; every action confirmed first, checked against the printer's state, logged, and only reported as done once the printer confirms it.

- [x] **Pause / resume / cancel** (2026-10-09): Klipper (Moonraker `/printer/print/*`), OctoPrint (`/api/job`), Bambu (MQTT `pause`/`resume`/`stop`; the printer's reply is checked).
- [x] **Start a print** (2026-10-12): pick a G-code file already on a Klipper or OctoPrint printer (searchable, newest first or A–Z, hidden files left out), or upload one (streamed to the board, then to the printer). Its own setting, "Also allow starting prints"; "bed is clear" confirmation with the camera shown; refused unless idle or finished.
- [x] **Tested on real printers** (2026-10-12): start, pause, resume, cancel and upload on a Snapmaker U1; start and cancel on the Elegoo Neptune 4 Max, which answers slowly (fixes: fresh readings for confirmation, a slow reply isn't a failure, an error reply still gets the printer's state checked, 20 s for file lists). OctoPrint: built and tested in code only.
- [ ] **Bambu:** the P1S (firmware 01.10, not in LAN Only / Developer Mode) silently ignores commands from other apps; LayerHound says so. Starting prints on Bambu (FTPS upload + MQTT `project_file`) only if that mode is used.
- Not planned: jogging, temperatures, fans, filament. Mainsail, Fluidd, OctoPrint and Bambu's apps do these well; link to the printer's own page instead.

## Done

**v1.0 release checklist (decided 2026-10-04)** — the main repo went public at v1.0:
- [x] Kyle's own testing, plus an automated UI walkthrough (`tests/ui/`).
- [x] Fresh screenshots for the README (2026-10-04; private details replaced).
- [x] **Scrubbed the home Wi-Fi name from git history** (2026-10-04): `git filter-repo --replace-text`, force-pushed; a backup of the old history is in `~/.layerhound/backups/` on the Mac. A pre-public audit found nothing else: no database, keys, tokens, access codes or personal email in any commit.
- [x] **v1.0.0 published** (2026-10-04) with `scripts/release.py`: built, tested, signed, verified from outside.
- [x] **Fresh install with the real one-liner** on a re-flashed SD card (2026-10-05).
- [x] **First real one-click update**: 0.5.0 → 1.0.0 with Update now (2026-10-04).
- [x] **Public** (2026-10-05): new public `TeamTacticalRC/LayerHound` with the clean history (the old repo is private `LayerHound-archive`). Dependabot, secret scanning with push protection, private vulnerability reporting, branch protection and CodeQL on; all scans at 0 open alerts.

**Releases since**
- [x] **v1.1.0** (2026-10-06): printer suggestions, Docker image, any Debian PC (`--port`), case v2.
- [x] **v1.2.0** (2026-10-07): optional automatic updates, opt-in usage stats, Settings reorder, case v3. The main board updated itself overnight.
- [x] **v1.3.0** (2026-10-12, needs setup): remote access with Tailscale, printer controls, recovery key, Recent problems and GitHub issue forms, and `install.sh --update` for setup-changing releases. The main board updated with it first.
- [x] **v1.4.0** (2026-10-12, needs setup): Settings in tabs; LayerHound moved to `/opt` with its own account. The main board updated with the published release.

**Features**
- [x] **Pre-built releases and one-line installer** (2026-10-04): `scripts/release.py` builds, tests, signs and publishes; `deploy/install.sh` downloads the latest release, checks its checksum and signature, and runs the board setup.
- [x] **Runs on any Debian-based PC** (2026-10-05): `install.sh --port N`; the setup hotspot is board-only by default (Settings → Setup hotspot: Auto/On/Off).
- [x] **Printer suggestions** (2026-10-05, `backend/discovery.py`): scans after first-run setup and daily (switchable), plus Bambu's own announcements (UDP 2021). One click for Klipper, the access code for Bambu, OctoPrint's "Allow" flow. Never added silently unless the owner turns on auto-add for Klipper.
- [x] **Docker image** (2026-10-05): `Dockerfile` and `docker-compose.yml`; non-root, data in a `/data` volume; built and tested on every push, published as `ghcr.io/teamtacticalrc/layerhound` (Intel/AMD and ARM) on each release tag.
- [x] **Optional usage stats** (2026-10-06, `backend/stats.py`): opt-in; daily random install ID, version, install type, board, printer counts by type and country, to Team Tactical RC's Google Form.
- [x] **Updates**, in three stages: (1) a daily update check (2026-10-04); (2) **Update now**: download, SHA-256 and **Ed25519 signature** check (release key in `~/.layerhound/release-signing.key` on the Mac only; public key in `backend/updates.py`), database backup, install, automatic **rollback** (2026-10-04); (3) **optional automatic updates** overnight at an hour the owner picks in their own time zone (2026-10-07). Releases that change the board setup are marked `--needs-setup` and installed with `install.sh --update` (2026-10-12), shown with Copy in Settings → Updates. Releases are built and signed on the Mac, never by GitHub Actions.
- [x] **Remote access with Tailscale** (2026-10-09): Settings → Network → Remote access connects the board to the owner's own Tailscale account (sign-in link and QR code), then shows its `ts.net` address and QR code. Tailscale DNS left off. Board only.
- [x] **Recovery key** (2026-10-09): shown once at setup; "Forgot your password?" on the sign-in screen. Only a hash is stored, it works once, wrong keys count toward the lockout.
- [x] **Tracking problems** (2026-10-12): **Settings → System → Recent problems** (`backend/problems.py`), kept on the board: unreachable printers, failed or unconfirmed printer commands, failed updates, hotspot/remote/Docker failures, server errors and dashboard-page crashes (with a Reload screen). **Send feedback** can include them (scrubbed, previewed). Public bug reports on GitHub Issues with issue forms; **Report a bug on GitHub** prefills one.
- [x] **Settings in tabs** (2026-10-12): General, Printers, Accounts, Network, System; most-used first; last tab remembered; "Settings → …" hints are links to the right tab.
- [x] **Its own account, in `/opt`** (2026-10-12, v1.4.0): code in `/opt/layerhound` (root's), data in `/var/lib/layerhound`, running as `layerhound` (no login, no sudo, no home folders); the updater runs as root and re-checks each package's signature itself. The first 1.4 setup moves an existing install and leaves `~/layerhound` as a fallback. Milestone tag `milestone-home-install-2026-10-12`; going back: [docs/REVERT-OPT-MOVE.md](docs/REVERT-OPT-MOVE.md). Tested on the main board: move, update, revert, move again.
- [x] **Printed setup guide** (2026-10-09, `docs/print`): one letter-size page for the box, with QR codes and a box to write the recovery key in.
- [x] **Login** (v0.5.0, 2026-10-02): see the Login plan below.
- [x] **Encrypt stored secrets** (2026-10-02, `backend/vault.py`): access codes, API keys and tokens encrypted in the database; the key is a separate owner-only file (`data/secret.key` next to the database: `/var/lib/layerhound/data/secret.key` on a board).
- [x] **Farm name instead of hardcoded branding** (2026-10-02): LayerHound's name and logo are fixed product branding; each install names its own farm.
- [x] **Licensing** (2026-10-04): **AGPL-3.0**; the name, logo and mascot excluded (`TRADEMARKS.md`). All dependencies compatible.
- [x] **Bambu risk** noted in the README and owner's guide: Bambu keeps tightening third-party access in firmware updates.
- [x] **First setup on the ROCK 4D** (2026-10-04): flashed, deployed with `--with-db`, Mac copy stopped (the P1S takes one local connection), temperatures, drive health, router detection and Ethernet speed all showing.

### Login plan
Built in v0.5.0 (2026-10-02).

- **First-run setup:** a fresh install opens a "Create your admin account" screen. There are no default passwords.
- **Passwords:** only a one-way hash is stored (scrypt).
- **Sessions:** a long random session ID in an HttpOnly, SameSite cookie. "Keep me signed in" lasts 30 days; otherwise the session ends when the browser closes.
- **Roles:** Admin (everything) and Viewer (read-only, for employees or a shop display).
- **Access keys:** read-only keys for devices that can't type a password (the status light, a wall display).
- **Brute-force protection:** after 5 wrong passwords (or recovery keys), pause logins from that device for a few minutes.
- **Forgot your password:** the recovery key on the sign-in screen (2026-10-09), or `layerhound reset-password` on the board.
- **Viewing:** login required by default; a setting lets anyone on the local network view without logging in. Changing anything always requires an admin.
- **Cross-site protection:** every change must carry an `X-Requested-With` header, which a form on another website can't add.
- **HTTPS:** plain `http://` on the local network. The dashboard's port must never be exposed to the internet; remote access is through Tailscale (built in since v1.3.0). Optional built-in HTTPS could come later.

## Release & security process
Open source means anyone can read and fork the code, but only people with write access can change this repository. **The maintainer's review is the release gate.**

- [x] **Automated tests:** `backend/tests` (API, validation, file-folder escape protection, secrets never returned, updates and signatures, printer controls, problems) and `tests/ui` (a real browser: setup, every page in dark/light at desktop/phone sizes, printers, controls, Settings tabs, view-only accounts).
- [x] **Checks on every pull request and push** (`.github/workflows/checks.yml`): backend tests (Python 3.10 and 3.12), frontend build, browser tests, deploy scripts (`bash -n` and shellcheck). Plus CodeQL (`codeql.yml`) and the Docker image build and test (`docker.yml`).
- [x] **Dependabot**, **`SECURITY.md`** (private reporting), **branch protection on `main`** (2026-10-05), **secret scanning** with push protection.
- [x] **2FA and a passkey** on the TeamTacticalRC GitHub account (2026-10-02). Keep the recovery codes somewhere safe off the computer.
- [x] **2FA on the email account** connected to GitHub (2026-10-12, Google account): it can reset other accounts and holds the feedback and usage-stats responses.
- [x] **Contributing guide and review rules** (2026-10-12): [CONTRIBUTING.md](CONTRIBUTING.md): small pull requests, issues first for big changes, tests required, extra care for installing/updating, sign-in, commands, file paths, network calls, printer controls and secrets; only the maintainer merges; contributors agree to AGPL plus permission for Team Tactical RC to offer other licenses. A pull request template asks for the same.
- [x] **Official releases** with checksums and **signed updates** (Ed25519), built and signed on the release Mac.

## Branding & business
Plan: free **open-source software**, plus a **ready-to-go LayerHound card** (and printed case and guide) sold by Team Tactical RC for people who want it easy. Customers bring their own board (see [LayerHound card](#layerhound-card-bring-your-own-board)).

### Decisions
- [x] **Product name: LayerHound** (chosen 2026-10-01). "LayerHound by Team Tactical RC".
- [x] **License:** **AGPL-3.0** (2026-10-04).
- [ ] **Trademark: deferred (decided 2026-10-02).** Rely on common-law rights from using the name: mark it **LayerHound™**, keep proof of first-use dates (GitHub history from 2026-10-01, domain registration, first posts and first sale). Risk accepted: someone else could register a similar name first.
- [ ] **Legal check (optional):** if the budget allows, a short attorney consult on the license, the contributor terms in CONTRIBUTING.md, the AI-generated logo and trademark risk.
- [x] **Disclaimers** (README and owner's guide): "not affiliated with" Bambu Lab, Klipper, OctoPrint and others. Don't use their logos.

### Launch checklist
- [ ] **Register `layerhound.com`** (and ideally `.io`). Unclaimed on 2026-10-01; do this first.
- [ ] **List LayerHound on ttrc.us and Etsy** (decided 2026-10-12): the shop pages are where people find it. No Facebook or Instagram accounts for now.
- [ ] **Announce** (Kyle).
- [ ] Optionally claim a `layerhound` GitHub organization name to protect it.
- [ ] Logo and simple brand guide (name usage, colors; the accent color system already exists).
- [x] Rename in the code (2026-10-01), `LICENSE` and `TRADEMARKS.md` (2026-10-04), contributing guide (2026-10-12).

### LayerHound card (bring your own board)
**Plan (decided 2026-10-12):** sell a **memory card with LayerHound already on it**, plus optionally the printed case and the paper setup guide. The customer buys the board (ROCK 4D) themselves. Why: a finished board with a radio needs FCC testing and a Declaration of Conformity before it can be sold, and the ROCK 4D has no FCC certification yet. A memory card, a printed case and a guide aren't devices that need FCC approval, and the board's FCC status stays with Radxa. A complete board can come back later if it's worth the testing.

- [ ] **Card image build script:** Radxa's OS with LayerHound in `/opt/layerhound`, built by a script so every card is identical. Also published as a **free download** to flash yourself (like OctoPi). Script written 2026-10-12 ([deploy/image](deploy/image/README.md)); a test image built on the main board (2026-10-12, copied to Kyle's Desktop) is **waiting to be tried on a card**: follow the test checklist in the README.
- [ ] **Unique per card:** on first start, each card creates its own secret key, SSH host keys and board password prompt; nothing secret is baked into the image. Test by booting two cards from the same image.
- [ ] **Board password on the setup page** (built 2026-10-12, not yet tried on a card): first-run setup also sets the board's `radxa` password (the admin password unless the owner picks another), once, through a root helper that refuses after that; the dashboard asks the admin if it didn't take. The default stays expired until then, and `rock` is locked.
- [x] **First boot** (v0.5.0): plug in Ethernet and power, open `http://layerhound.local`, name the farm, create the admin account, save the recovery key, and printers are suggested.
- [x] **No-cable Wi-Fi setup** (2026-10-02; tested 2026-10-04): with no network, the board opens **"LayerHound-Setup"**; a phone that joins it gets the setup page (pick the home Wi-Fi, and on a new board name the farm and create the admin account).
- [x] **Updates in the field:** signed one-click and automatic updates with rollback; `install.sh --update` for setup changes.
- [x] **Locked down:** LayerHound runs as its own account, can't change its own code, and only installs signed updates (v1.4.0).
- [ ] **Setup guide for the card:** "buy this exact board, put the card in, plug in power (and Ethernet if you have it)", with a direct link to the right board and power supply.
- [ ] **Cards:** brand-name **high-endurance** microSD cards (LayerHound writes to its database all the time). Name the kind in the guide for people flashing their own.
- [ ] **Licensing notice:** the image includes Linux and other free software: include a short notice with links to their source code, and check Radxa's terms for sharing their OS image.
- [ ] **Etsy:** check that a card with software on it fits Etsy's rules (ttrc.us has no such question).
- [ ] **Case** (sold printed, or as free STL files): `hardware/case/`, version 3 test-printed 2026-10-07: full-footprint base bracing the port wall, Bumpon SJ5302 feet, fan held with M3 bolts. The board must be confirmed available long-term.
- [ ] **Case fan:** 40 × 40 × 10 mm 5 V fans pre-terminated with a **2-pin 1.25 mm plug** (the ROCK 4D's fan header) at a set wire length, so no splicing is needed. Check plug polarity against Radxa's fan header page.
- [x] **Fan speed by temperature** (2026-10-04, `backend/fan.py`): quiet up to 45 °C, full at 65 °C (adjustable); full speed if LayerHound stops or can't read a temperature.
- [ ] **Status light as a kit:** sell the printed housing and a pre-flashed ESP32 (and parts) rather than a finished, powered light, for the same FCC reason. Confirm where the kit line is with a test lab.
- [ ] **Compliance check:** a short (often free) call with an EMC test lab to confirm the card and kits need no FCC testing. General information so far, not legal advice.
- [ ] **Later, a complete board (optional):** only after Radxa confirms FCC status for the ROCK 4D and its Wi-Fi module (FCU760K) has an FCC ID; then FCC Part 15 Subpart B Class B testing of the finished product at a lab, a Declaration of Conformity from Team Tactical RC, and the label and manual statements. Or use a board with FCC paperwork already (e.g. Raspberry Pi).
- [ ] **Business:** price, returns and support for the card and kits.
