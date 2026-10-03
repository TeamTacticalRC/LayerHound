# LayerHound case for the Radxa ROCK 4D

A two-part printed case with a 40 mm fan that blows across the board, and the LayerHound emblem and wordmark inlaid in the lid.

**Status: design draft, not test-printed yet.** Port positions come from Radxa's official 2D drawing (v1.11). Print the shell once and check the fit before printing more.

- Outside size: **91 × 73 × 49 mm**
- The fan sits on the back (the 40-pin header side). It pulls air in through the grill and blows it across the processor and memory, out through the vents in the front and right side.
- All ports are open: USB, Ethernet and the antenna on the right, power, HDMI and audio on the front, microSD on the left.

## Files

| File | What it is |
|---|---|
| `stl/case-shell.stl` | Walls and lid, already upside down for printing (lid on the bed). |
| `stl/case-logo-blue.stl`, `-white.stl`, `-gray.stl` | Logo inlays for a multicolor print. They fill the recesses in the lid's top surface. |
| `stl/case-base.stl` | Floor plate with the board standoffs. |
| `viewer.html` | 3D viewer: assembled, exploded and inside views. |
| `build_case.py`, `emblem.py` | The design itself. Every size is a setting at the top of `build_case.py`. |

## Printing

**Material:** PETG or ASA. PLA can soften from the board's heat over time. 0.2 mm layers, 3 walls, 15% infill. **No supports needed:** every opening is open at the edge that faces up.

**Shell with a multicolor logo (AMS, or the U1's toolheads):**
1. In Bambu Studio, import `case-shell.stl` and the three `case-logo-*.stl` files together. When asked, load them as **a single object with multiple parts**.
2. Give the shell black or charcoal, and give the logo parts blue, white and gray.
3. The logo is only the first 3 layers, so color changes happen only at the start of the print and waste very little filament.

**Shell in one color:** print `case-shell.stl` on its own. The logo comes out as a recessed outline in the lid.

**Base:** print `case-base.stl` flat as it is.

## Parts

| Part | Qty | Notes |
|---|---|---|
| 40 × 40 × 10 mm fan, **5 V** | 1 | For example Noctua NF-A4x10 5V (quiet) or any 4010 5 V fan. |
| M3 × 14 screws (or the fan's own screws) | 4 | From outside the back wall into the fan. |
| M2.5 × 12 screws | 4 | Up through the base and the board into the shell's posts. |
| Rubber feet, 8 mm | 4 | Optional; there are shallow pockets for them. |
| 2 female-to-female jumper wires | — | If the fan has a 3-pin plug instead of separate wires. |

## Putting it together

1. Screw the fan to the inside of the back wall, with the **label facing into the case**. Fans blow out of the label side.
2. Connect the fan to the 40-pin header: red to **pin 4 (5 V)**, black to **pin 6 (ground)**. On Raspberry Pi-style headers these are on the outer row, at the end nearest the corner mounting hole. Check Radxa's ROCK 4D pinout before plugging in.
3. Set the board on the base's standoffs.
4. Lower the shell straight down over the board. The port openings are open at the bottom, so it slides over the connectors.
5. Turn it over and drive the four M2.5 screws up through the base and the board into the shell. They hold everything together.

## Wi-Fi antenna

The ROCK 4D's Wi-Fi uses an external antenna. If yours is a stick antenna with an SMA connector, mount it through the 6.6 mm hole near the top of the left side. If it's a flat stick-on antenna, put it on the inside of the lid. Plastic doesn't block Wi-Fi. If you don't need the hole, set `SMA_HOLE=False` and rebuild.

## Changing the design

```bash
python3 -m venv .venv
.venv/bin/pip install -r hardware/case/requirements.txt
.venv/bin/python hardware/case/build_case.py
```

Run these from the project folder. Settings are at the top of `build_case.py`: wall thickness, gaps, fan position, port openings and the antenna hole.

**To view in 3D:** run this from the project folder, then open http://localhost:8770/viewer.html:

```bash
python3 -m http.server 8770 --directory hardware/case
```

The emblem is traced from `public/brand/layerhound-mascot.png`, so updated art changes the case logo too. The wordmark uses Arial Black, slanted; swap in the final brand font when there is one.
