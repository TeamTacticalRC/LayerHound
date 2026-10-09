# LayerHound LED status light

A small light that shows what your printers are doing, so you notice trouble without opening the dashboard. An ESP32 joins your Wi-Fi, asks LayerHound every few seconds, and lights the LEDs. Printers are in the dashboard's order (**Print Farm → Reorder**). Two shapes, from the same firmware:

- **Ring (the main LayerHound light):** a 12-LED ring for your desk or shelf. Each printer gets a part (arc) of the ring, with a dark LED between parts. A printing arc fills up as the print goes; an error arc blinks red. With 1 printer it gets the whole ring; with more than 6, each gets one LED.
- **Bar (option):** 8 LEDs in a row, mounted by the printers: one LED per printer.

**Status: prototype** (2026-10-09). Both firmware versions compile and the dashboard side is built and tested; the first light hasn't been wired yet.

| Printer | Light |
|---|---|
| Printing | Green (on the ring, the arc fills up with the print's progress) |
| Paused | Amber, pulsing |
| Finished | Blue |
| Idle | Dim white |
| Error | Red, blinking |
| Offline | Red |
| No printer for this light | Off |

LayerHound picks the colors (`backend/lightbar.py`), so they can change without reloading the light. **Settings → LED status light** has the shape (ring or bar), a live preview, the brightness, and an option to reverse the order.

When the light can't show printers, it uses purple, which never means a printer state:

| Light | Meaning |
|---|---|
| All lights pulse purple | Setup page waiting (see Setting it up) |
| One white light sweeps back and forth | Joining your Wi-Fi |
| All lights blink dim purple | Can't reach LayerHound; it keeps trying |
| All lights solid dim purple | LayerHound refused the access key |

## Parts

See the parts list in [ROADMAP.md](../../ROADMAP.md#parts-to-order): ESP32 38-pin board with a screw-terminal breakout, a NeoPixel Ring (12 LEDs) or Stick (8 LEDs), 74AHCT125 level shifter, a 470 Ω resistor, a 1000 µF capacitor, a breadboard for the prototype (a Perma-Proto board for a permanent one), a USB power adapter and a **data** USB cable.

## Wiring

```
USB power ── ESP32 ─┬─ 5V/VIN ──┬───────────────── ring/stick 5V (PWR on the ring)
                    │           ├─ 74AHCT125 VCC (pin 14)
                    │           └─ 1000 µF + leg
                    ├─ GND ─────┬───────────────── ring/stick GND
                    │           ├─ 74AHCT125 GND (pin 7) and 1OE (pin 1)
                    │           └─ 1000 µF − leg (striped side)
                    └─ GPIO13 ── 74AHCT125 1A (pin 2)
                                 74AHCT125 1Y (pin 3) ── 470 Ω ── ring/stick DIN (Data Input)
```

- Solder three wires to the ring's or stick's **input** pads (power, GND, **Data Input/DIN**), not Data Out.
- Put the capacitor near the LEDs. **Its striped side (−) goes to GND**; backwards, it can overheat and burst.
- The level shifter is required: the LEDs need a 5 V data signal, and the ESP32 gives 3.3 V.
- Unused inputs of the 74AHCT125 (2A, 3A, 4A) can go to GND, and their OE pins to 5V, to keep the chip quiet.
- Check the pin labels on your ESP32 board and breakout before powering up. A proper diagram with photos comes with the first light.

## Loading the firmware

Needs [PlatformIO](https://platformio.org) (`pip install platformio`, or the VS Code extension). With the ESP32 plugged into the computer by USB:

```bash
cd hardware/lightbar/firmware
pio run -e ring -t upload      # or: pio run -e bar -t upload
```

`pio device monitor` shows the light's log (Wi-Fi, LayerHound address, each request's result).

## Setting it up

1. In LayerHound, **Settings → Login & users → Access keys**: create a key named **Status light** and copy it. Keys can only view.
2. Plug in the light. The first time, it pulses purple and makes a Wi-Fi network called **LayerHound-Light**.
3. Join that network from a phone. On the page that opens, choose **Configure WiFi**, pick your Wi-Fi and enter its password, keep the LayerHound address (`http://layerhound.local`) and paste the key. Save.
4. The light joins your Wi-Fi and lights up, matching the preview in **Settings → LED status light**. Pick **Ring** or **Bar** there to match yours.

**To change its settings later** (new Wi-Fi, new key), hold the ESP32's **BOOT** button while plugging the light in.

## Next

- A printable housing, made like the case (`hardware/case`): for the ring, a desk puck styled like the LayerHound logo (the hound emblem inside the ring of light) with a diffuser; for the bar, a strip with a diffuser and printer labels.
- A permanent build on the Perma-Proto board, and, for selling lights, a custom circuit board.
