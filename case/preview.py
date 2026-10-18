"""Clearance check against stand-in parts, plus preview renders."""
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import case as C
from case import box, union

OUT = Path(__file__).with_name("out")

def dummies():
    """Screen, Pi and plugs in the housing print frame (X: user-right = -X)."""
    top = C.PCB_Y0 + C.PCB_H
    pi_y0, pi_y1 = top - 87.69, top - 31.69
    d = {
        "glass": box(-C.LENS_W / 2, C.LENS_W / 2, top - C.LENS_H, top, C.FRONT, C.FRONT + 5.15),
        "board": box(-C.PCB_W / 2, C.PCB_W / 2, C.PCB_Y0, top, C.FRONT + 6.65, C.PCB_BACK_Z),
        "pi": box(-45.6, 39.4, pi_y0, pi_y1, C.PCB_BACK_Z + 8, C.PCB_BACK_Z + 8 + 1.6),
        "pi_parts": box(-45.6, 30, pi_y0 + 2, pi_y1 - 2, C.PCB_BACK_Z + 9.6, C.PCB_BACK_Z + 9.6 + 16.5),
        "usb_plugs": box(-45.6 - 40, -45.6, pi_y0 + 2, pi_y1 - 2, C.PCB_BACK_Z + 10, C.PCB_BACK_Z + 26),
        "usb_c": box(31.4 - 6, 31.4 + 6, pi_y1, pi_y1 + 26, C.PCB_BACK_Z + 9, C.PCB_BACK_Z + 17),
        # mic plug body on its way in through the side wall to the port
        "mic_plug": (lambda m: m.mirror([1, 0, 0]) if C.MIC_SIDE == "right" else m)(
            box(48.0, C.W / 2 + 10, C.mic_port_yz()[0] - C.MIC_PLUG_W / 2,
                C.mic_port_yz()[0] + C.MIC_PLUG_W / 2,
                C.mic_port_yz()[1] - C.MIC_PLUG_T / 2, C.mic_port_yz()[1] + C.MIC_PLUG_T / 2)),
    }
    return d

def faces(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    t = np.asarray(mesh.tri_verts)
    return v[t]

def shade(tris, base, light=(0.4, -0.6, 0.7)):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    l = np.array(light) / np.linalg.norm(light)
    k = 0.45 + 0.55 * np.clip(n @ l, 0, 1)
    return np.clip(np.array(base)[None, :] * k[:, None], 0, 1)

def render(items, fname, elev, azim, title, size=(9, 7)):
    fig = plt.figure(figsize=size, dpi=110)
    ax = fig.add_subplot(projection="3d")
    allt, allc = [], []
    for m, color in items:
        tris = faces(m)
        if len(tris) == 0:
            continue
        allt.append(tris); allc.append(shade(tris, color))
    tris, cols = np.concatenate(allt), np.concatenate(allc)
    # one collection so every triangle is depth-sorted together
    ax.add_collection3d(Poly3DCollection(tris, facecolors=cols, edgecolor="none"))
    v = tris.reshape(-1, 3)
    mn, mx = v.min(0), v.max(0)
    c, r = (mn + mx) / 2, (mx - mn).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(OUT / fname)
    plt.close(fig)

if __name__ == "__main__":
    rep, asm, _ = C.build()
    h = C.housing()
    bp = C.back_plate().translate([0, 0, C.DEPTH])
    print("Clearance check (stand-in parts vs housing and back plate):")
    ok = True
    for name, m in dummies().items():
        for pname, part in (("housing", h), ("back plate", bp)):
            v = (m ^ part).volume()
            if v > 0.5:
                ok = False
                print(f"  CLASH {name} with {pname}: {v:.0f} mm^3")
    print("  all clear" if ok else "  see clashes above")
    # Assembly with stand-ins in world coordinates
    dw = {k: C.housing_world(m) for k, m in dummies().items()}
    case_col, deck_col, glass_col = (0.86, 0.86, 0.88), (0.30, 0.32, 0.36), (0.08, 0.10, 0.14)
    items = [(asm["base"], case_col), (asm["deck"], deck_col), (asm["housing"], case_col),
             (asm["back_plate"], case_col), (dw["glass"], glass_col)]
    # buttons as simple discs on the deck
    da = math.radians(C.DECK_ANGLE)
    s_mid = C.DECK_LEN / math.cos(da) / 2 + 4
    for sx, col in ((-1, (0.85, 0.2, 0.2)), (1, (0.95, 0.75, 0.15))):
        btn = C.cyl(14, 6, 0, 0, 0).translate([sx * C.BUTTON_SPACING / 2, s_mid, C.DECK_T])
        items.append((C.deck_world(btn), col))
    render(items, "view_front.png", 18, -62, "Front three-quarter")
    render(items, "view_side.png", 0, 0, "Side (screen reclined 20 degrees)")
    render(items, "view_back.png", 25, 130, "Back three-quarter")
    # Inside view: housing without back plate, with stand-ins
    inside = [(asm["housing"], case_col)] + [(dw[k], c) for k, c in (
        ("board", (0.15, 0.25, 0.6)), ("pi", (0.1, 0.5, 0.2)), ("pi_parts", (0.6, 0.6, 0.6)),
        ("usb_plugs", (0.2, 0.2, 0.2)), ("usb_c", (0.95, 0.95, 0.95)), ("mic_plug", (0.1, 0.1, 0.1)))]
    render(inside, "view_inside.png", 30, 150, "Inside the housing (back removed)")
    print("renders written")
