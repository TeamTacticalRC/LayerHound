# Roadmap

## When the ROCK 4D arrives
- Flash a Debian-based OS (Armbian or Radxa Debian), connect it to the network, and confirm `ssh` works from the Mac.
- Run `deploy/deploy.sh user@BOARD-HOSTNAME.local --with-db` (see README).
- Stop the dashboard on the Mac. The Bambu P1S accepts only one local connection.
- Check that the board's temperature sensors show up on the Server tab.
- Turn the Docker, Home Assistant and Pi-hole entries in Services into real checks as each is installed.

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
- [ ] **Security:** optional login (anyone on the network can currently edit or delete printers), and encrypt the stored access codes and API keys.
- [ ] **Update checks:** tell the user when a new version is available.
- [ ] **Licensing:** choose a license for this code. Review paho-mqtt's license terms if it will be sold closed-source.
- [ ] **Bambu risk:** Bambu keeps tightening third-party access in firmware updates. Be upfront with customers that Bambu support could stop working.
