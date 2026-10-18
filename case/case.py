"""Voice label printer case: parametric model built with manifold3d.

Run:  python3 case.py      -> writes STL files and preview PNGs in ./out

Parts (each exported in its print orientation, no supports needed):
  1. housing      screen housing, printed face-down (best finish on the bezel)
  2. back_plate   flat back of the housing, vents and cable notch
  3. clamp x4     small tabs that hold the screen board in the housing
  4. base         console with the button deck in front and the housing seat
  5. deck         flat button plate with TALK / PRINT labels

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

SIDE_GAP = 22.0                # room beside the board for USB plugs, mic socket
TOP_GAP = 12.0                 # room above the board for the power cable to bend
INNER_DEPTH = 40.0             # front plate to back plate (Pi + plugs)
BACK_T = 2.5                   # back plate thickness
CORNER_R = 5.0

# Mic: the USB extension's female end sits in a sleeve in a side wall, with
# the mic plugged in from outside. The Pi's USB ports also face the user's
# right, so on that side the socket sits above the Pi, clear of its plugs.
MIC_SIDE = "right"                # "right" or "left", as seen from the front
SOCKET_W, SOCKET_H = 18.0, 10.0   # female end housing (W along depth, H across)
SOCKET_CLR = 0.3
SOCKET_Y_ON_PCB = 83.0            # height of socket centre above board bottom
SOCKET_Z = 26.0                   # depth of socket centre from the front face
SLEEVE_LEN = 12.0

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

    # Mic socket sleeve with a 45-degree gusset underneath (printable).
    sy = PCB_Y0 + SOCKET_Y_ON_PCB
    hw, hh = (SOCKET_W + SOCKET_CLR) / 2, (SOCKET_H + SOCKET_CLR) / 2
    # Built on the +X wall (user-left), then mirrored for the right side.
    wall_x = W / 2 - WALL
    sleeve_outer = Manifold.batch_hull([
        box(wall_x - SLEEVE_LEN, wall_x + 0.1, sy - hh - 2, sy + hh + 2,
            SOCKET_Z - hw - 2, SOCKET_Z + hw + 2),
        box(wall_x - 0.1, wall_x + 0.1, sy - hh - 2, sy + hh + 2,
            SOCKET_Z - hw - 2 - SLEEVE_LEN, SOCKET_Z + hw + 2),
    ])
    mic_mirror = MIC_SIDE == "right"            # user-right is print -X
    if mic_mirror:
        sleeve_outer = sleeve_outer.mirror([1, 0, 0])
    shell = union([shell] + rails + ribs + bosses + [sleeve_outer])
    socket_hole = box(wall_x - SLEEVE_LEN - 1, W / 2 + 1, sy - hh, sy + hh,
                      SOCKET_Z - hw, SOCKET_Z + hw)
    if mic_mirror:
        socket_hole = socket_hole.mirror([1, 0, 0])

    holes = [socket_hole]
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

BASE_SCREW_Z = [10.0, 26.0]     # depth positions of the housing-to-base screws
KO_W = 7.0                      # breakaway tab width (cable up to ~6 mm)
KO_DEPTH = 10.0                 # how far the notch reaches in from the back rim
KO_SLIT = 0.5
KO_WEB = 0.8                    # thickness left at the hinge (2 perimeters)
KNOCKOUT_YS = [WALL + RIB + 9.0,                      # low: printer cable
               WALL + INNER_H - RIB - 6.0]            # high: power cable

def back_plate():
    plate = rrect(W, H, CORNER_R).translate([0, H / 2]).extrude(BACK_T)
    cut = []
    for sx in (-1, 1):
        for y in (WALL + RIB / 2, WALL + INNER_H - RIB / 2):
            cut.append(cyl(CLEAR_R, BACK_T + 2, sx * RIB_X, y, -1))
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
BASE_LEN = B[0] + B[1] / T(math.radians(REAR_SLOPE))

def profile_xs(points):
    """Extrude a (y, z) side profile across the base width (world X)."""
    pts = list(points)
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    if area < 0:
        pts = pts[::-1]                                  # manifold wants CCW
    cs = CrossSection([pts])
    # CrossSection is in (u, v); extrude along +Z then rotate so u->Y, v->Z, Z->X.
    return cs.extrude(W).rotate([90, 0, 90]).translate([-W / 2, 0, 0])

def base():
    prof = [(0, 0), (0, FRONT_H), (DECK_LEN, FRONT_H + DECK_LEN * T(DA)),
            (DECK_LEN, E[1]), (B[0], B[1]), (BASE_LEN, 0)]
    solid = profile_xs(prof)
    # Inner cavity: open top, keeps floor, front wall and rear slope wall.
    rs = math.radians(REAR_SLOPE)
    y_rear_inner = BASE_LEN - BASE_WALL / math.sin(rs)
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
    # Feet recesses under the floor.
    for x in (-W / 2 + 16, W / 2 - 16):
        for y in (16, BASE_LEN - 22):
            cuts.append(cyl(6.5, 1.2, x, y, -0.2))
    return body - union(cuts), deck_posts

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
        "5_deck": d.mirror([0, 0, 1]),                    # top face on the bed
    }
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
    import pickle
    allm = union(list(asm.values()))
    x0, y0, z0, x1, y1, z1 = allm.bounding_box()
    print(f"assembled size: {x1-x0:.0f} W x {y1-y0:.0f} D x {z1-z0:.0f} H mm")
    to_trimesh(allm).export(Path(__file__).with_name("out") / "assembly_preview.stl")
