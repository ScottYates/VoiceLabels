"""Voice label printer case: parametric model built with manifold3d.

Run:  python3 case.py      -> writes STL files and preview PNGs in ./out

Parts (each exported in its print orientation, no supports needed):
  1. housing      screen housing, printed face-down (best finish on the bezel)
  2. back_plate   flat back of the housing, vents and cable notch
  3. clamp x4     small tabs that hold the screen board in the housing
  4. base         console with the button deck in front and the housing seat
  5. deck         flat button plate with TALK / PRINT labels
  6. power_pod    closed box behind the base for the USB power brick, with a
                  switched, fused IEC power socket in its back wall
  7. pod_lid      screw-on lid for the power pod

Coordinates for the housing ("print" frame): X across, Y up the face,
Z depth (0 = front face on the bed). Viewed from the FRONT, user-right = -X.
World frame for the assembly: X user-right, Y toward the back, Z up.
"""
import math
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold, OpType

# ------------------------------------------------------------------ settings
SEG = 64                       # circle smoothness
WALL = 2.4                     # side wall thickness
FRONT = 2.0                    # bezel (front plate) thickness
CLR = 0.4                      # clearance around the screen board

# Hosyond 7" DSI (from the maker's drawing)
PCB_W, PCB_H = 164.9, 102.0    # board / backlight outline
LENS_W, LENS_H = 164.28, 99.17 # glass; top edge flush with the board top
VA_L, VA_R = 3.2, 6.5          # visible area inset from glass edges, front view
VA_T, VA_B = 3.7, 8.5
STACK = 8.25                   # glass front to back of the board
WINDOW_MARGIN = 1.0            # window larger than the visible area by this
WINDOW_CHAMFER = 1.5

SIDE_GAP = 22.0                # room beside the board for USB plugs
TOP_GAP = 12.0                 # room above the board for the power cable to bend
INNER_DEPTH = 40.0             # front plate to back plate (Pi + plugs)
BACK_T = 2.5                   # back plate thickness
CORNER_R = 5.0

# Mic: it plugs straight into one of the Pi's USB ports through an opening in
# the side wall. The Pi's ports face the user's right, near the bottom of the
# case (the GPIO header is at the bottom). The opening lines up with the
# outer port of the stack nearest the GPIO header.
MIC_SIDE = "right"                # side the Pi's USB ports face, seen from the front
PI_STANDOFF = 8.0                 # gap between the screen board and the Pi board
PI_TOP_EDGE = 31.69               # Pi board top edge, mm below the screen board top
MIC_PORT_FROM_GPIO = 9.0          # USB stack centre, mm in from the Pi's GPIO edge
MIC_PORT_ABOVE_PI = 12.8          # outer port centre above the Pi board's top face
MIC_PLUG_W, MIC_PLUG_T = 19.0, 10.0   # mic plug body: width (up-down) x thickness
MIC_HOLE_CLR = 3.0                # extra room around the plug body

# Base and deck
RECLINE = 20.0                 # screen tilt back from vertical, degrees
DECK_ANGLE = 8.0               # button deck rises toward the screen
DECK_LEN = 62.0                # deck depth (horizontal)
DECK_T = 3.0                   # deck thickness (snap-in buttons like ~3 mm)
FRONT_H = 46.0                 # height of the deck underside at the front edge
REAR_SLOPE = 50.0              # rear wall angle from horizontal (>45 = no supports)
BUTTON_HOLE = 30.4             # 30 mm arcade buttons (print-tested holes run small)
BUTTON_PANEL_T = 2.0           # deck thinned to this around each button, for snap-in clips
BUTTON_RECESS_D = 38.0         # diameter of the thinned area (underside)
BUTTON_SPACING = 84.0
BASE_WALL = 2.4

PILOT_R = 1.3                  # M3 screw into plastic
CLEAR_R = 1.7                  # M3 clearance
HEAD_R = 3.3                   # M3 pan head counterbore

# Derived housing sizes
INNER_W = PCB_W + 2 * CLR + 2 * SIDE_GAP
INNER_H = PCB_H + 2 * CLR + TOP_GAP
W = INNER_W + 2 * WALL
H = INNER_H + 2 * WALL
DEPTH = FRONT + INNER_DEPTH            # shell depth (without back plate)
PCB_X0 = -PCB_W / 2                    # board edges (print X)
PCB_Y0 = WALL + CLR                    # board bottom edge (print Y)
PCB_BACK_Z = FRONT + STACK             # back face of the board
RIB = 8.0                              # corner rib size
RIB_X = INNER_W / 2 - RIB / 2          # rib centres
CLAMP_X = PCB_W / 2 + CLR + 6.0
CLAMP_YS = [PCB_Y0 + 15.0, PCB_Y0 + 87.0]

# ------------------------------------------------------------------ helpers
def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])

def cyl(r, h, x=0, y=0, z=0):
    return Manifold.cylinder(h, r, circular_segments=SEG).translate([x, y, z])

def rrect(w, h, r):
    """Rounded rectangle centred at the origin (X width, Y height)."""
    core = CrossSection.square([w - 2 * r, h - 2 * r], center=True)
    return core.offset(r, join_type=__import__("manifold3d").JoinType.Round, circular_segments=SEG)

def union(parts):
    return Manifold.batch_boolean(parts, OpType.Add)

def text_cross_section(s, size):
    """Text outline as a CrossSection, centred, using DejaVu Sans Bold."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    tp = TextPath((0, 0), s, size=size, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = [p for p in tp.to_polygons() if len(p) >= 3]
    cs = CrossSection(polys, FillRule.EvenOdd)
    (x0, y0), (x1, y1) = cs.bounds()[:2], cs.bounds()[2:]
    return cs.translate([-(x0 + x1) / 2, -(y0 + y1) / 2])

# ------------------------------------------------------------------ housing
def mic_port_yz():
    """Height (print Y) and depth (print Z) of the mic's USB port centre."""
    pi_top = PCB_Y0 + PCB_H - PI_TOP_EDGE        # Pi board edge toward the case top
    pi_gpio_edge = pi_top - 56.0                  # GPIO edge, toward the case bottom
    y = pi_gpio_edge + MIC_PORT_FROM_GPIO
    z = PCB_BACK_Z + PI_STANDOFF + 1.6 + MIC_PORT_ABOVE_PI
    return y, z


def housing():
    outer = rrect(W, H, CORNER_R).translate([0, H / 2]).extrude(DEPTH)
    inner = box(-INNER_W / 2, INNER_W / 2, WALL, WALL + INNER_H, FRONT, DEPTH + 1)
    shell = outer - inner

    # Window over the visible area. Front view right = -X, so swap L/R.
    lens_x0, lens_x1 = -LENS_W / 2, LENS_W / 2
    lens_y1 = PCB_Y0 + PCB_H
    lens_y0 = lens_y1 - LENS_H
    va_x0, va_x1 = lens_x0 + VA_R, lens_x1 - VA_L     # print X (mirrored)
    va_y0, va_y1 = lens_y0 + VA_B, lens_y1 - VA_T
    m, c = WINDOW_MARGIN, WINDOW_CHAMFER
    win = box(va_x0 - m, va_x1 + m, va_y0 - m, va_y1 + m, -1, FRONT + 1)
    bevel = Manifold.batch_hull([
        box(va_x0 - m - c, va_x1 + m + c, va_y0 - m - c, va_y1 + m + c, -1, 0),
        box(va_x0 - m, va_x1 + m, va_y0 - m, va_y1 + m, c, c + 0.01),
    ])
    shell = shell - win - bevel

    # Side rails that locate the board left/right.
    rails = []
    for sx in (-1, 1):
        x_in = sx * (PCB_W / 2 + CLR)
        rails.append(box(min(x_in, x_in + sx * 2), max(x_in, x_in + sx * 2),
                         PCB_Y0 + 25, PCB_Y0 + 75, FRONT, FRONT + STACK - 1.5))
    # Corner ribs: back-plate screws (along Z) and base screws (along Y, bottom).
    ribs = []
    for sx in (-1, 1):
        x0, x1 = sx * RIB_X - RIB / 2, sx * RIB_X + RIB / 2
        ribs.append(box(x0, x1, WALL, WALL + RIB, FRONT, DEPTH))
        ribs.append(box(x0, x1, WALL + INNER_H - RIB, WALL + INNER_H, FRONT, DEPTH))
    # Clamp bosses beside the board.
    bosses = [cyl(3.5, STACK, sx * CLAMP_X, y, FRONT) for sx in (-1, 1) for y in CLAMP_YS]

    shell = union([shell] + rails + ribs + bosses)

    # Mic opening: a tall rectangle lined up with the Pi's USB port.
    my, mz = mic_port_yz()
    hy, hz = (MIC_PLUG_W + MIC_HOLE_CLR) / 2, (MIC_PLUG_T + MIC_HOLE_CLR) / 2
    mic_hole = box(W / 2 - WALL - 1, W / 2 + 1, my - hy, my + hy, mz - hz, mz + hz)
    if MIC_SIDE == "right":                     # user-right is print -X
        mic_hole = mic_hole.mirror([1, 0, 0])

    holes = [mic_hole]
    # Back-plate screw pilots (from the back rim, 10 mm deep).
    for sx in (-1, 1):
        for y in (WALL + RIB / 2, WALL + INNER_H - RIB / 2):
            holes.append(cyl(PILOT_R, 10.5, sx * RIB_X, y, DEPTH - 10))
    # Base screw pilots: up into the bottom ribs from the outside.
    for sx in (-1, 1):
        for z in BASE_SCREW_Z:
            holes.append(cyl(PILOT_R, 10, 0, 0, 0).rotate([-90, 0, 0])
                         .translate([sx * RIB_X, -0.5, z]))
    # Clamp pilots.
    for sx in (-1, 1):
        for y in CLAMP_YS:
            holes.append(cyl(PILOT_R, 7.5, sx * CLAMP_X, y, FRONT + STACK - 7))
    # Wire pass-through in the bottom wall (button wires to the GPIO header).
    holes.append(box(-20, 20, -1, WALL + 1, 8, 30))
    # Breakaway cable tabs: a notch at the back rim of each side wall, filled
    # by a tab held on by a thin web. Snap out the ones you need; the back
    # plate closes over the cable.
    for y in KNOCKOUT_YS:
        for sx in (-1, 1):
            x_out, x_in = sx * W / 2, sx * (W / 2 - WALL)
            xa, xb = min(x_out, x_in) - 0.01, max(x_out, x_in) + 0.01
            y0, y1 = y - KO_W / 2, y + KO_W / 2
            z0 = DEPTH - KO_DEPTH
            # slits down both long sides of the tab
            holes.append(box(xa - 1, xb + 1, y0 - KO_SLIT, y0, z0, DEPTH + 1))
            holes.append(box(xa - 1, xb + 1, y1, y1 + KO_SLIT, z0, DEPTH + 1))
            # thin the hinge line at the bottom of the tab from the inside
            hinge_in = (xa, xb - KO_WEB) if sx > 0 else (xa + KO_WEB, xb)
            holes.append(box(hinge_in[0], hinge_in[1], y0, y1, z0 - 0.01, z0 + 1.2))
    return shell - union(holes)

USBC_X = 31.4                   # Pi USB-C port across the housing (print X)
USBC_NOTCH_W = 7.5              # cable notch in the back plate (cable up to ~6.5 mm)
USBC_NOTCH_D = 10.0             # notch depth below the inside top of the housing

BASE_SCREW_Z = [10.0, 26.0]     # depth positions of the housing-to-base screws
KO_W = 7.0                      # breakaway tab width (cable up to ~6 mm)
KO_DEPTH = 10.0                 # how far the notch reaches in from the back rim
KO_SLIT = 0.5
KO_WEB = 0.8                    # thickness left at the hinge (2 perimeters)
KNOCKOUT_YS = [PCB_Y0 + 52.0,                         # low: printer cable
               WALL + INNER_H - RIB - 6.0]            # high: power cable

def back_plate():
    plate = rrect(W, H, CORNER_R).translate([0, H / 2]).extrude(BACK_T)
    cut = []
    for sx in (-1, 1):
        for y in (WALL + RIB / 2, WALL + INNER_H - RIB / 2):
            cut.append(cyl(CLEAR_R, BACK_T + 2, sx * RIB_X, y, -1))
    # Notch at the top edge for the USB-C power cable (from the power pod up
    # the back to the Pi's USB-C port, which points up at the top of the case).
    cut.append(box(USBC_X - USBC_NOTCH_W / 2, USBC_X + USBC_NOTCH_W / 2,
                   WALL + INNER_H - USBC_NOTCH_D, H + 1, -1, BACK_T + 1))
    # Vent slots over the Pi.
    for i in range(9):
        y = PCB_Y0 + 22 + i * 7
        cut.append(box(-55, 45, y, y + 3, -1, BACK_T + 1))
    return plate - union(cut)

def clamp():
    tab = Manifold.cube([14, 8, 3]).translate([-4, -4, 0])
    return tab - cyl(CLEAR_R, 5, 0, 0, -1)

# ------------------------------------------------------------------ base (world frame)
T = math.tan
DA, RA = math.radians(DECK_ANGLE), math.radians(RECLINE)
DECK_TOP_BACK = FRONT_H + DECK_LEN * T(DA) + DECK_T / math.cos(DA)
E = np.array([DECK_LEN, DECK_TOP_BACK])            # housing front-bottom edge (y, z)
HOUSING_DEPTH = DEPTH + BACK_T
DOWN_BACK = np.array([math.cos(RA), -math.sin(RA)])  # housing depth direction (y, z)
UP_FACE = np.array([math.sin(RA), math.cos(RA)])     # housing height direction (y, z)
B = E + HOUSING_DEPTH * DOWN_BACK                    # housing back-bottom edge
BASE_LEN = B[0] + B[1] / T(math.radians(REAR_SLOPE))   # without the power pod

# ------------------------------------------------------------------ power pod
# The USB power brick lives in a closed box behind the base, under the
# screen's lean. Mains comes in through a switched, fused IEC C14 socket
# (e.g. Amazon B0C2GHJGW2) in its back wall; inside, the cut-off socket end
# of a short 2-prong extension cord feeds the brick.
POWER_POD = True
PSU_L, PSU_H, PSU_T = 63.5, 63.5, 31.75   # brick: prong axis (X), height (Z), thickness (Y)
PSU_CLR = 0.8                      # room around the brick
POD_WALL = 2.4
TONGUE_T = 3.0                     # base floor extension the pod screws down onto
POD_GAP_V = 0.5                    # pod front to the base's rear wall
POD_GAP_S = 3.0                    # pod front to the screen's back plate (screw heads)
INLET_CUT = (47.6, 27.8)           # IEC socket panel cutout (W x H)
INLET_SCREW_SPACING = 40.0         # its two screws, above and below the cutout
INLET_DEPTH = 38.0                 # body + terminals behind the panel
INLET_X = -68.0                    # socket centre across the pod (world X, user-right +)
INLET_PANEL_T = 2.0                # back wall thinned to this around the socket (snap clips)
BRICK_X0 = -5.0                    # brick's prong end (world X); prongs face -X
LID_T = 2.4

def pod_geometry():
    z0 = TONGUE_T
    yf = B[0] + POD_GAP_V                                  # vertical part of the front
    c = POD_GAP_S / math.cos(RA)
    slant = lambda z: B[0] + c + (z - B[1]) * T(RA)       # front, parallel to the back plate
    z_v = B[1] + (yf - B[0] - c) / T(RA)                  # where the slant leaves the vertical
    front = lambda z: yf if z <= z_v else slant(z)        # outer front at height z
    brick_z1 = z0 + POD_WALL + PSU_H + PSU_CLR
    z_top = brick_z1 + 1.5                                 # top of the walls (lid sits on it)
    front_in_top = front(z_top) + POD_WALL / math.cos(RA)
    brick_y0 = front_in_top + PSU_CLR
    brick_y1 = brick_y0 + PSU_T
    yb = brick_y1 + PSU_CLR + POD_WALL                     # outer back
    return dict(z0=z0, yf=yf, z_v=z_v, front=front, z_top=z_top, yb=yb,
                brick=(BRICK_X0, BRICK_X0 + PSU_L, brick_y0, brick_y1,
                       z0 + POD_WALL, z0 + POD_WALL + PSU_H))

POD = pod_geometry()
TOTAL_LEN = POD["yb"] if POWER_POD else BASE_LEN

def profile_xs(points, width=None):
    """Extrude a (y, z) side profile across the base width (world X), centred."""
    width = W if width is None else width
    pts = list(points)
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    if area < 0:
        pts = pts[::-1]                                  # manifold wants CCW
    cs = CrossSection([pts])
    # CrossSection is in (u, v); extrude along +Z then rotate so u->Y, v->Z, Z->X.
    return cs.extrude(width).rotate([90, 0, 90]).translate([-width / 2, 0, 0])

def pod_screw_points():
    """Screws up through the base tongue into pads in the pod floor (world x, y)."""
    g = POD
    xb0, xb1, yb0, yb1, _, _ = g["brick"]
    ymid = (g["yf"] + g["yb"]) / 2
    return [(-(W / 2 - 12), ymid), (W / 2 - 12, ymid),
            ((xb0 + xb1) / 2 - 22, g["yf"] + 7), (INLET_X + 30, g["yf"] + 7)]

def base():
    if POWER_POD:   # straight rear wall under the housing; the pod sits behind it
        prof = [(0, 0), (0, FRONT_H), (DECK_LEN, FRONT_H + DECK_LEN * T(DA)),
                (DECK_LEN, E[1]), (B[0], B[1]), (B[0], 0)]
    else:
        prof = [(0, 0), (0, FRONT_H), (DECK_LEN, FRONT_H + DECK_LEN * T(DA)),
                (DECK_LEN, E[1]), (B[0], B[1]), (BASE_LEN, 0)]
    solid = profile_xs(prof)
    # Inner cavity: open top, keeps floor, front wall and rear wall.
    rs = math.radians(90.0 if POWER_POD else REAR_SLOPE)
    rear_outer = B[0] if POWER_POD else BASE_LEN
    y_rear_inner = rear_outer - BASE_WALL / math.sin(rs)
    top = 400
    cav = [(BASE_WALL, BASE_WALL), (y_rear_inner - BASE_WALL / T(rs), BASE_WALL),
           (y_rear_inner - top / T(rs), top), (BASE_WALL, top)]
    cav_cs = CrossSection([cav])
    cavity = cav_cs.extrude(W - 2 * BASE_WALL).rotate([90, 0, 90]).translate(
        [-W / 2 + BASE_WALL, 0, 0])
    body = solid - cavity

    adds, cuts = [], []
    # Seat pillars: slanted cylinders along the housing's height axis, under
    # each housing screw, trimmed to the seat plane.
    axis = np.array([0.0, UP_FACE[0], UP_FACE[1]])            # world direction up the face
    seat_n = np.array([0.0, -DOWN_BACK[1], DOWN_BACK[0]])     # not used, for clarity
    for sx in (-1, 1):
        for d in BASE_SCREW_Z:
            p = E + d * DOWN_BACK                                # seat point (y, z)
            top_pt = np.array([sx * RIB_X, p[0], p[1]])
            # pillar from far below the floor up to the seat point along the axis
            L = 120.0
            tilt = -RECLINE                                     # rotate about X
            pillar = cyl(6.5, L, 0, 0, -L).rotate([tilt, 0, 0]).translate(top_pt.tolist())
            adds.append(pillar)
            screw = cyl(CLEAR_R, L + 5, 0, 0, -L).rotate([tilt, 0, 0]).translate(top_pt.tolist())
            head = cyl(HEAD_R, L, 0, 0, -L - 6).rotate([tilt, 0, 0]).translate(top_pt.tolist())
            cuts += [screw, head]
    # Deck screw posts (vertical), top trimmed to the deck underside.
    # rear posts sit forward and inboard of the slanted housing-screw tunnels
    deck_posts = [(sx * (W / 2 - 9), 9.0) for sx in (-1, 1)] + \
                 [(sx * (W / 2 - 13), DECK_LEN - 17.0) for sx in (-1, 1)]
    for x, y in deck_posts:
        ztop = FRONT_H + y * T(DA)
        adds.append(cyl(4.5, ztop + 5, x, y, 0))
        cuts.append(cyl(PILOT_R, 11, x, y, ztop - 10))
    body = union([body] + adds)
    # Trim everything to the outside profile (pillars and posts stay inside).
    body = body ^ solid
    rear_feet_y = BASE_LEN - 22
    if POWER_POD:
        # Floor tongue under the pod, with countersunk screws up into the pod.
        body = body + box(-W / 2, W / 2, B[0] - 1, TOTAL_LEN, 0, TONGUE_T)
        for x, y in pod_screw_points():
            cuts.append(cyl(CLEAR_R, TONGUE_T + 2, x, y, -1))
            cuts.append(Manifold.cylinder(1.8, HEAD_R + 0.3, CLEAR_R, SEG).translate([x, y, -0.01]))
        rear_feet_y = TOTAL_LEN - 14
    # Feet recesses under the floor.
    for x in (-W / 2 + 16, W / 2 - 16):
        for y in (16, rear_feet_y):
            cuts.append(cyl(6.5, 1.2, x, y, -0.2))
    return body - union(cuts), deck_posts

def power_pod():
    """Closed box for the brick, modelled in world coordinates (print as is)."""
    g = POD
    w = POD_WALL
    z0, z_top, yb, yf = g["z0"], g["z_top"], g["yb"], g["yf"]
    front = g["front"]
    outer = profile_xs([(yf, z0), (yf, g["z_v"]), (front(z_top), z_top), (yb, z_top), (yb, z0)])
    # Inside: walls of thickness w (the slanted part measured square to its face).
    c_in = POD_GAP_S / math.cos(RA) + w / math.cos(RA)
    slant_in = lambda z: B[0] + c_in + (z - B[1]) * T(RA)
    yf_in = yf + w
    z_vi = B[1] + (yf_in - B[0] - c_in) / T(RA)
    zi0 = z0 + w
    zt = z_top + 5
    inner = profile_xs([(yf_in, zi0), (yf_in, z_vi), (slant_in(zt), zt), (yb - w, zt), (yb - w, zi0)],
                       W - 2 * w)
    pod = outer - inner
    fin = lambda z: yf_in if z <= z_vi else slant_in(z)

    adds, cuts = [], []
    xb0, xb1, yb0, yb1, zb0, zb1 = g["brick"]
    # Floor pads for the screws from below (blind holes: nothing reaches the inside air).
    for x, y in pod_screw_points():
        adds.append(cyl(5.0, 6.0, x, y, zi0 - 0.01))
        cuts.append(cyl(PILOT_R, w + 6.0 - 1.0, x, y, z0 - 0.01))
    # Lid screw bosses in the four inside corners.
    lid_pts = pod_lid_points()
    for x, y in lid_pts:
        adds.append(cyl(4.5, z_top - zi0, x, y, zi0))
        cuts.append(cyl(PILOT_R, 11, x, y, z_top - 10))
    # Brick locators: a low rib in front of it and a short stop past its cable end.
    adds.append(box(xb0 + 6, xb1 - 6, yb0 - 3.0 - PSU_CLR, yb0 - PSU_CLR, zi0, zi0 + 5))
    # IEC socket in the back wall: cutout, two screw holes, wall thinned around it.
    iw, ih = INLET_CUT
    izc = zi0 + 5 + INLET_SCREW_SPACING / 2 + 2       # keep the lower screw clear of the floor
    cuts.append(box(INLET_X - iw / 2, INLET_X + iw / 2, yb - w - 1, yb + 1, izc - ih / 2, izc + ih / 2))
    for dz in (-INLET_SCREW_SPACING / 2, INLET_SCREW_SPACING / 2):
        cuts.append(cyl(1.75, 10, 0, 0, -5).rotate([90, 0, 0]).translate([INLET_X, yb, izc + dz]))
    cuts.append(box(INLET_X - iw / 2 - 6, INLET_X + iw / 2 + 6, yb - w - 1, yb - INLET_PANEL_T,
                    izc - ih / 2 - 3, izc + ih / 2 + 3))
    # Zip-tie anchors (a bar with a tunnel) for the cord socket and the cords.
    for x, y in [(xb0 - 20, (yb0 + yb1) / 2), (INLET_X + 30, g["yf"] + 16),
                 (xb1 + 22, yb1 - 6)]:
        adds.append(box(x - 5, x + 5, y - 4, y + 4, zi0, zi0 + 6))
        cuts.append(box(x - 6, x + 6, y - 2, y + 2, zi0 + 1.2, zi0 + 3.8))
    # USB-C cable exit: notch in the top of the front wall, closed by the lid.
    nx = min(max(-USBC_X, xb1 + 8), W / 2 - 20)    # near the Pi's USB-C, clear of the brick
    cuts.append(box(nx - 4, nx + 4, g["front"](z_top) - 5, fin(z_top) + 6, z_top - 7, z_top + 1))
    # Vent slots in the back wall above the cable coil (away from the mains side).
    for i in range(6):
        x = xb1 + 6 + i * 6
        if x + 2.5 < W / 2 - 14:
            cuts.append(box(x, x + 2.5, yb - w - 1, yb + 1, z_top - 30, z_top - 8))
    pod = union([pod] + adds) - union(cuts)
    return pod

def pod_lid_points():
    g = POD
    yfront = g["front"](g["z_top"]) + POD_WALL / math.cos(RA) + 5.0
    yback = g["yb"] - POD_WALL - 5.0
    xs = (-(W / 2 - POD_WALL - 5.0), W / 2 - POD_WALL - 5.0)
    return [(x, y) for x in xs for y in (yfront, yback)]

def pod_lid():
    g = POD
    y0, y1 = g["front"](g["z_top"]), g["yb"]
    lid = box(-W / 2, W / 2, y0, y1, 0, LID_T)
    cuts = []
    for x, y in pod_lid_points():
        cuts.append(cyl(CLEAR_R, LID_T + 2, x, y, -1))
        cuts.append(cyl(HEAD_R, 2, x, y, LID_T - 1.2))
    # Vent slots over the brick and cable coil only (never over the mains side).
    xb0, xb1, yb0, yb1, _, _ = g["brick"]
    for i in range(10):
        x = xb0 + 4 + i * 6
        if x + 2.5 < W / 2 - 14:
            cuts.append(box(x, x + 2.5, yb0 + 4, yb1 - 4, -1, LID_T + 1))
    # A lip under the lid that keeps it centred (and the brick pressed down).
    w = POD_WALL
    yi0, yi1 = y0 + w / math.cos(RA) + 0.4, y1 - w - 0.4
    ring = (box(-W / 2 + w + 0.4, W / 2 - w - 0.4, yi0, yi1, -2.0, 0.01)
            - box(-W / 2 + w + 2.4, W / 2 - w - 2.4, yi0 + 2, yi1 - 2, -3, 1))
    ring = ring - union([cyl(5.5, 4, x, y, -3) for x, y in pod_lid_points()])   # clear the bosses
    return (lid + ring) - union(cuts)

def deck(deck_posts):
    L = DECK_LEN / math.cos(DA)               # length along the slope
    plate = Manifold.cube([W, L, DECK_T]).translate([-W / 2, 0, 0])
    cuts = []
    for x, y in deck_posts:
        cuts.append(cyl(CLEAR_R, DECK_T + 2, x, y / math.cos(DA), -1))
        cuts.append(cyl(HEAD_R, 2, x, y / math.cos(DA), DECK_T - 1.2))  # shallow head recess
    s_mid = L / 2 + 4
    for sx, label in ((-1, "TALK"), (1, "PRINT")):
        cuts.append(cyl(BUTTON_HOLE / 2, DECK_T + 2, sx * BUTTON_SPACING / 2, s_mid, -1))
        # thin the plate around the hole from underneath so snap-in clips can grip
        cuts.append(cyl(BUTTON_RECESS_D / 2, DECK_T - BUTTON_PANEL_T + 1,
                        sx * BUTTON_SPACING / 2, s_mid, -1))
        txt = text_cross_section(label, 7.0).extrude(1.0)
        cuts.append(txt.translate([sx * BUTTON_SPACING / 2, s_mid - BUTTON_HOLE / 2 - 8,
                                   DECK_T - 0.6]))
    return plate - union(cuts), s_mid

# ------------------------------------------------------------------ assembly transforms
def housing_world(m):
    # Explicit affine: world = R * p + t, columns are images of X, Y, Z.
    ex = [-1, 0, 0]
    ey = [0, UP_FACE[0], UP_FACE[1]]
    ez = [0, DOWN_BACK[0], DOWN_BACK[1]]
    mat = [[ex[0], ey[0], ez[0], 0], [ex[1], ey[1], ez[1], E[0]], [ex[2], ey[2], ez[2], E[1]]]
    return m.transform(mat)

def deck_world(m):
    ca, sa = math.cos(DA), math.sin(DA)
    mat = [[1, 0, 0, 0], [0, ca, -sa, 0], [0, sa, ca, FRONT_H]]
    return m.transform(mat)

# ------------------------------------------------------------------ export
def to_trimesh(m):
    import trimesh
    mesh = m.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3],
                           faces=np.asarray(mesh.tri_verts), process=True)

def place_on_bed(m):
    (x0, y0, z0, x1, y1, z1) = m.bounding_box()
    return m.translate([-(x0 + x1) / 2, -(y0 + y1) / 2, -z0])

def build():
    out = Path(__file__).with_name("out")
    out.mkdir(exist_ok=True)
    h = housing()
    bp = back_plate()
    cl = clamp()
    b, posts = base()
    d, s_mid = deck(posts)
    parts = {
        "1_housing": h,                                   # face-down as modelled
        "2_back_plate": bp,
        "3_clamp_x4": union([cl.translate([i * 18, 0, 0]) for i in range(4)]),
        "4_base": b,
        "5_deck": d,                                      # top face up: labels print last, crisp
    }
    if POWER_POD:
        parts["6_power_pod"] = power_pod()                # as modelled: floor down
        parts["7_pod_lid"] = pod_lid().mirror([0, 0, 1])  # top face down, lip up
    report = {}
    for name, m in parts.items():
        m = place_on_bed(m)
        x0, y0, z0, x1, y1, z1 = m.bounding_box()
        report[name] = (round(x1 - x0, 1), round(y1 - y0, 1), round(z1 - z0, 1),
                        m.status().name, m.genus())
        to_trimesh(m).export(out / f"{name}.stl")
    # Assembly in world coordinates.
    hw = housing_world(h)
    bpw = housing_world(bp.translate([0, 0, DEPTH]))
    dw = deck_world(d)
    asm = {"housing": hw, "back_plate": bpw, "base": b, "deck": dw}
    if POWER_POD:
        asm["power_pod"] = power_pod()
        asm["pod_lid"] = pod_lid().translate([0, 0, POD["z_top"]])
    return report, asm, s_mid

if __name__ == "__main__":
    rep, asm, _ = build()
    for k, v in rep.items():
        print(f"{k:14s} {v[0]:6.1f} x {v[1]:6.1f} x {v[2]:6.1f} mm  {v[3]} genus={v[4]}")
    # Interference checks between assembled parts
    names = list(asm)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            v = (asm[names[i]] ^ asm[names[j]]).volume()
            print(f"overlap {names[i]} / {names[j]}: {v:.1f} mm^3")
    if POWER_POD:
        xb0, xb1, yb0, yb1, zb0, zb1 = POD["brick"]
        brick = box(xb0, xb1, yb0, yb1, zb0, zb1)
        print(f"brick vs pod: {(brick ^ asm['power_pod']).volume():.1f} mm^3,"
              f" brick vs lid: {(brick ^ asm['pod_lid']).volume():.1f} mm^3")
        print("pod: front y %.1f, back y %.1f, top z %.1f" % (POD["yf"], POD["yb"], POD["z_top"]))
    allm = union(list(asm.values()))
    x0, y0, z0, x1, y1, z1 = allm.bounding_box()
    print(f"assembled size: {x1-x0:.0f} W x {y1-y0:.0f} D x {z1-z0:.0f} H mm")
    to_trimesh(allm).export(Path(__file__).with_name("out") / "assembly_preview.stl")
