# Voice Labels logo plaque

<p align="center"><img src="logo3d-preview.png?v=1" alt="The plaque from above: dark plate, yellow speech bubble with the sound wave and text lines, Voice in white, Labels in yellow, tagline in gray" width="560"></p>

The logo as a 3D-printable plaque, **190 × 60 × 4 mm**: a 3 mm dark plate with the logo raised 1 mm on top. The speech bubble's sound wave and text lines are cut through it, so the plate shows through them, as in the logo.

| File | What |
|---|---|
| `stl/logo_plaque.stl` | The whole plaque as one piece |
| `stl/logo_1_base_dark.stl` | The plate (dark gray or black) |
| `stl/logo_2_yellow.stl` | Speech bubble and "Labels" (yellow) |
| `stl/logo_3_white.stl` | "Voice" (white) |
| `stl/logo_4_gray.stl` | The tagline (light gray) |

**Four colours (e.g. the Snapmaker U1's four toolheads):** load the four numbered files together as one object with four parts (in Orca/Snapmaker Orca, select all four when importing and say yes to "load as a single object with multiple parts"), then give each part its filament. They're already in place.

**One colour at a time:** print `logo_plaque.stl` and add a filament change at **3.0 mm**: the plate prints in the first colour, everything raised in the second. Paint "Voice" and the tagline afterwards if you like.

Print flat as exported, 0.2 mm layers (0.1 mm for the top millimetre makes the lettering crisper). The tagline's strokes are 0.5–0.8 mm wide, fine for a 0.4 mm nozzle with the slicer's thin-wall handling (Arachne, the default in current slicers).

To change the size or heights, edit `MM` (mm per logo unit; 0.25 gives 190 mm wide), `BASE_T` and `RAISE` in `make_logo.py` and run `python3 make_logo.py` (needs manifold3d, trimesh and fontTools, and the Inter Display font).

The same logo, at 90% size, is inlaid in the case's front panel: see `case/stl/11a…11d` in the [case README](../case/README.md). `logo_2d()` in `make_logo.py` gives the coloured shapes for that.
