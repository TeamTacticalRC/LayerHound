# LayerHound case for the Radxa ROCK 4D

A two-part printed case with a 40 mm fan that blows across the board, and the LayerHound emblem and wordmark inlaid in the lid.

**Status: version 2** (2026-10-05). The first test print fit the board and ports. Version 2 moves the fan 6.5 mm to the left and adds 4 mm behind the board, so the fan can be held with bolts and nuts: they used to hit a board post and the 40-pin header. Port positions come from Radxa's official 2D drawing (v1.11). [Before and after](fan-move.png).

- Outside size: **91 × 77 × 49 mm**
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
| 40 × 40 × 10 mm fan, **5 V**, 2-wire | 1 | Ideally with a **2-pin 1.25 mm plug** (often sold as "JST 1.25" or "PH1.25" for single-board computers), to fit the board's fan header. See Connecting the fan. |
| M3 × 16 bolts and M3 nuts | 4 each | From outside the back wall, through the fan's corner holes, with the nut on the inside. There's room behind the board for the nuts; `build_case.py` checks it. |
| M2.5 × 12 screws, button or pan head | 4 | Up through the base and the board into the shell's posts (10–14 mm also works). They cut their own threads in the plastic. |
| Rubber feet, 8 mm | 4 | Optional; there are shallow pockets for them. |
| 2-pin 1.25 mm pigtail | — | Only if your fan has a different plug: splice it on. |

## Putting it together

1. Bolt the fan to the inside of the back wall with the **label facing into the case** (fans blow out of the label side): M3 × 16 bolts from outside, nuts on the inside. Fit the fan before the board, while there's room for your fingers.
2. Plug the fan into the board's fan header (see Connecting the fan).
3. Set the board on the base's standoffs.
4. Lower the shell straight down over the board. The port openings are open at the bottom, so it slides over the connectors.
5. Turn it over and drive the four M2.5 screws up through the base and the board into the shell. They hold everything together.

## Connecting the fan

**Use the board's fan header (recommended).** The ROCK 4D has a 2-pin, 1.25 mm, 5 V fan header with speed control (PWM), so the fan can run slow and quiet when the board is cool. LayerHound does this automatically; adjust it in **Settings → Cooling fan**. See [Radxa's fan page](https://docs.radxa.com/en/rock4/rock4d/hardware-use/fan).
- The plug must be the small **1.25 mm** kind. A standard 3-pin PC fan plug (like Noctua's) won't fit. Splice on a 1.25 mm pigtail if needed.
- **Check the polarity before plugging in.** Pre-made plugs aren't always wired the same way. Match the fan's red wire to the header's + side shown on Radxa's page.

**Or use the 40-pin header.** Red to pin 4 (5 V), black to pin 6 (ground), using female jumper wires. The fan then always runs at full speed. Check Radxa's ROCK 4D pinout first.

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

## License

The case design is covered by LayerHound's [AGPL-3.0 license](../../LICENSE), except the LayerHound emblem and wordmark (`emblem.py`, `case-logo-*.stl`), which are trademarks; see [TRADEMARKS.md](../../TRADEMARKS.md).
