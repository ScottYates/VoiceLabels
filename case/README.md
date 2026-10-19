# Voice Labels case

<p align="center">
  <img src="docs/case-front.png?v=3" alt="Front: reclined screen housing above the button deck" width="420">
  <img src="docs/case-back.png?v=3" alt="Back: the power pod under the screen's lean, with the switched power socket in its back wall" width="400">
</p>

A desk console for the voice label printer: the 7" screen (with the Pi on its back) sits in a housing reclined 20°. In front of it is a sloped deck with the **TALK** (left) and **PRINT** (right) buttons. The mic plugs straight into one of the Pi's USB ports through a tall opening in the right side wall. Cables leave through snap-out tabs on either side. Behind the base, tucked under the screen's lean, a closed **power pod** holds the USB power brick, with a switched, fused mains socket in its back wall.

Assembled size: about **215 W × 156 D × 170 H mm**. Every part fits the Snapmaker U1's 270 mm bed and prints **without supports**.

## Parts to print

| File | Print orientation | Size (mm) | Notes |
|---|---|---|---|
| `stl/1_housing.stl` | As exported: bezel face down | 215 × 120 × 42 | The bezel's first layers are the visible front, so use a smooth, clean plate |
| `stl/2_back_plate.stl` | Flat | 215 × 120 × 2.5 | Vents over the Pi |
| `stl/3_clamp_x4.stl` | Flat | four tabs | Hold the screen board in the housing |
| `stl/4_base.stl` | As exported: floor down | 215 × 156 × 58 | Use a brim if the corners lift. The floor carries on behind as a flat tongue the power pod screws onto |
| `stl/5_deck.stl` | As exported: top face up | 215 × 63 × 3 | TALK and PRINT are engraved 0.6 mm deep in the top, so they form in the last layers and stay crisp. For coloured letters, add a filament change at 2.4 mm on the U1, or paint them. Around each button hole the plate is thinned to 2 mm from underneath so the buttons' snap-in clips can grip |
| `stl/6_power_pod.stl` | As exported: floor down | 215 × 51 × 68 | **Print in PETG** (it holds mains wiring and a warm brick). Its front leans back 20° to follow the screen; that prints fine without supports |
| `stl/7_pod_lid.stl` | As exported: top face down | 215 × 38 × 4 | PETG. The lip on top locates it inside the pod |

Suggested settings: PLA or PETG, 0.4 mm nozzle, 0.2 mm layers, 3 walls, 15–20% gyroid infill, no supports.

## Hardware

| Qty | Item | Used for |
|---|---|---|
| 8 | M3 × 10 mm pan or button head screws | Back plate (4), deck (4) |
| 4 | M3 × 8 mm | Screen clamps |
| 4 | M3 × 16 mm | Housing to base (from underneath) |
| 4 | Rubber feet, up to 13 mm across | Recesses in the base floor |
| 4 | M3 × 10 mm flat (countersunk) head | Base tongue up into the power pod floor, from underneath |
| 4 | M3 × 8 mm | Pod lid |
| 1 | Switched, fused IEC C14 power socket, 47 × 27.4 mm cutout (e.g. Amazon B0C2GHJGW2) | Back of the pod; comes with its own screws and pre-crimped wires |
| 1 | 1 ft 2-prong extension cord (e.g. Amazon B08R63X8RZ) | Its socket end feeds the brick inside the pod |
| 2–3 | Wago 221 lever connectors | Joining the cord's wires to the socket's wires |
| 1 | 2 A time-delay (slow-blow) 5 × 20 mm fuse | Replaces the 10 A fuse that comes in the socket. It protects the small brick much better |
| 3 | Small zip ties | Cord socket and cables to the anchors in the pod |
| 1 | IEC C13 power cord (a standard PC cord) | Wall to the pod |

The screws thread straight into printed pilot holes. Don't overtighten them.

## Assembly

1. **Test the fit first.** Print the deck and push a button into one hole. Check that the mic's plug passes through the opening in the housing's right wall. If the holes are tight or loose, see Adjusting below.
2. **Snap out cable tabs.** The housing has four tabs on its back edge, a high and a low one on each side. Snap out the ones you need with pliers: a high tab for the power cable on whichever side you prefer, and the middle tab on the right side for the printer cable.
3. **Join the housing to the base.** Set the housing on the base's sloped seat, with its bezel edge against the back of the deck opening. From underneath, drive the four M3 × 16 screws up through the slanted holes in the base into the housing.
4. **Fit the buttons.** Push each button down through its hole from the top until its clips snap under the plate (TALK on the left, PRINT on the right). If your buttons came with a plastic nut instead, screw it on from underneath; the thinned area leaves room for it. Wire them as described in the main README ("Wiring the buttons"). Pass the wires up through the slot in the housing floor, then screw the deck to the base (4 × M3 × 10).
5. **Fit the screen.** Remove the black corner stands from the screen if they're still attached. Lower the screen and Pi face-first into the housing. The two side rails centre it, and the board sits on the housing floor. Screw the four clamps over the board edges (M3 × 8).
6. **Connect inside.** Connect the button wires to the GPIO header. Then, from outside, push the mic's plug through the opening in the right wall into the Pi's USB port behind it. Coil the spare cable. Plug in the printer cable and the keyboard's receiver.
7. **Wire the power pod** (see "Power pod wiring" below), with nothing plugged into the wall.
8. **Fit the pod.** Stand it on the base's tongue, its front against the base's back wall, and drive the four M3 × 10 flat-head screws up through the tongue into the pod floor.
9. **Route the USB-C cable.** It leaves the pod through the notch at the top of the pod's front wall, runs up the back of the screen housing, and enters through the notch at the top edge of the back plate, right behind the Pi's USB-C port. Plug it into the Pi. (You can still use a side tab instead, as before.)
10. **Close up.** Lay the cables in their notches and screw on the back plate (4 × M3 × 10) and the pod lid (4 × M3 × 8). Stick on the feet.

## Power pod wiring

**This is mains voltage. Do all of it unplugged, and if you've never wired a plug or a light fitting, have someone who has check it before you plug in.**

<p align="center"><img src="docs/case-open.png?v=1" alt="Looking down into the power pod with its lid off: the brick stands on edge against the back wall" width="420"></p>

The power socket in the pod's back wall has a fuse and a lighted rocker switch built in. It comes with short wires already crimped onto its back. Inside the pod:

1. **Prepare the cord.** Cut the plug off the 1 ft extension cord, keeping the **socket end** with about 15 cm of cord. Split the two wires apart for 4 cm and strip 11 mm of insulation from each.
2. **Identify the wires.** On a polarized US cord, the wire with **ridges or a stripe** on its insulation goes to the **wide** slot (neutral). The **smooth** wire goes to the **narrow** slot (live).
3. **Connect, with Wago 221 lever connectors:**

   | Power socket wire | Goes to |
   |---|---|
   | **L** (live, switched and fused; usually brown or black) | the cord's **smooth** wire |
   | **N** (neutral; usually blue or white) | the cord's **ridged/striped** wire |
   | **Earth** (green/yellow) | nothing: the brick has two prongs. Put it alone in its own Wago so its end is covered, or leave it off the socket |

4. **Swap the fuse** in the socket's drawer for a **2 A time-delay** fuse.
5. **Mount the parts.** Snap the power socket into the back-wall opening from outside and fit its two screws. Zip-tie the cord socket to the anchor next to the brick and the Wagos to the anchor near the front. Plug the brick into the cord socket, stand it on edge against the back wall (prongs toward the power socket), and coil the spare USB-C cable in the space beyond its cable end.
6. **Check before closing:** no bare copper visible anywhere, every lever down, nothing pulled tight. Screw on the lid.

Turning the switch off cuts power to everything. With power-off protection turned on in the software (see the main README), that's safe to do at any time.

## Adjusting

Everything is set by the numbers at the top of `case.py`. Ready-to-print copies are in `stl/`. To regenerate them, run `python3 case.py` with `manifold3d`, `trimesh` and `numpy` installed; it writes to `out/`. The settings you're most likely to change:

| Setting | Default | What it does |
|---|---|---|
| `BUTTON_HOLE` | 30.4 | Button hole diameter |
| `BUTTON_PANEL_T` | 2.0 | Deck thickness around each button. Raise to 3.0 for clips that need a thicker panel |
| `MIC_SIDE` | right | The side the Pi's USB ports face, where the mic opening goes |
| `MIC_PLUG_W`, `MIC_PLUG_T` | 19 × 10 | The mic's plug body, width (up and down) × thickness. The opening is 3 mm bigger each way |
| `PI_STANDOFF` | 8 | Gap between the screen board and the Pi. It sets how far back the mic opening sits |
| `RECLINE` | 20 | Screen tilt back from vertical, in degrees |
| `DECK_ANGLE` | 8 | Deck slope |
| `WINDOW_MARGIN` | 1.0 | How much the screen opening exceeds the picture area |
| `SIDE_GAP`, `TOP_GAP` | 22, 12 | Room beside and above the screen for plugs and cables |
| `INNER_DEPTH` | 40 | Room behind the screen for the Pi |
| `POWER_POD` | True | Set to False for the old base with a sloped back and no pod |
| `PSU_L`, `PSU_H`, `PSU_T` | 63.5, 63.5, 31.75 | The power brick: prong-to-cable length, height, thickness |
| `INLET_CUT`, `INLET_SCREW_SPACING` | 47.6 × 27.8, 40 | Power socket cutout and its screw spacing (screws above and below). Check against your socket before printing the pod |

`python3 preview.py` checks that the screen, Pi, plugs and the mic's path to its port clear the case. It also writes the preview images in `out/`.

## Measurements to confirm before printing the housing

- **Pi depth:** the case assumes the brass standoffs hold the Pi about 8 mm off the screen board, which leaves about 6 mm of space above the Pi's USB ports. If your standoffs are a different length, set `PI_STANDOFF` to match. If they're longer than 12 mm, also raise `INNER_DEPTH` by the difference.
- **Mic opening:** it lines up with the outer port of the Pi's USB stack nearest the GPIO header, the lower stack as the case stands. Hold the screen and Pi in the printed housing and check that the plug lines up before closing it. If the opening sits too far forward or back, adjust `PI_STANDOFF`.
- **Screen opening:** it comes from the maker's drawing. The picture sits closer to the left and top edges of the glass, and the opening matches that.
