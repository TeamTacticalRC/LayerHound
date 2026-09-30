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
