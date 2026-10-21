"""Headless FreeCAD builder for the cooling-tower 3D model.

Run with FreeCAD's command-line interpreter (its own Python, stdlib + FreeCAD only):

    CT_DESIGN_JSON=<out>/data/design_results.json  CT_OUT_DIR=<out>/model  freecadcmd build_model.py

Reads the "model" block of design_results.json (millimetres; X along the row, Y across a cell,
Z up, Z = 0 at the basin operating water level) and builds:
  Basin (concrete shell + pump sump bays), Structure (every pultruded FRP member as its true
  I/W or square-tube section, one compound per member mark, or one object per member with
  CT_PER_MEMBER=1), Fill, Eliminators, Distribution (risers, headers, laterals, nozzles), Casing
  (side/end walls, plenum partitions), FanDeck (with fan openings), FanStacks, Mechanical (fan,
  hub, gear reducer, drive shaft, motor, support beam) and Access (handrails, ladder).
Writes <tag>_tower.FCStd, <tag>_tower.step, preview_mesh.json (coarse tessellation for a quick
render) and prints one line "CTMODEL {json summary}" for the caller.
"""
import json
import math
import os
import sys
import time

import FreeCAD
import Part
from FreeCAD import Vector as V

T0 = time.time()
DATA = json.load(open(os.environ["CT_DESIGN_JSON"], encoding="utf-8"))["model"]
OUT = os.environ["CT_OUT_DIR"]
PER_MEMBER = os.environ.get("CT_PER_MEMBER", "0") == "1"
os.makedirs(OUT, exist_ok=True)

n, L, W = DATA["cells"], DATA["L"], DATA["W"]
Z = DATA["z"]
nL = n * L
fan, bs, dist = DATA["fan"], DATA["basin"], DATA["distribution"]
doc = FreeCAD.newDocument(DATA["tag"].replace("-", "_"))
objects = []


def add(name, shapes, group=None):
    shp = shapes if isinstance(shapes, Part.Shape) else Part.makeCompound(shapes)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shp
    if group is not None:
        group.addObject(obj)
    objects.append(obj)
    return obj


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p1, p2):
    a, b = V(*p1), V(*p2)
    d = b - a
    return Part.makeCylinder(r, d.Length, a, d)


# ------------------------------------------------------------------ FRP members
def frame_matrix(p1, p2):
    a, b = V(*p1), V(*p2)
    ex = b - a
    length = ex.Length
    ex.normalize()
    ref = V(1, 0, 0) if abs(ex.z) > 0.99 else V(0, 0, 1)
    ey = ref.cross(ex)
    ey.normalize()
    ez = ex.cross(ey)
    m = FreeCAD.Matrix(ex.x, ey.x, ez.x, a.x, ex.y, ey.y, ez.y, a.y, ex.z, ey.z, ez.z, a.z, 0, 0, 0, 1)
    return m, length


PROFILES = {}


def profile_face(sec):
    """Cross-section face in the local Y-Z plane (one per section, reused): I/W outline or a square tube."""
    key = (sec["family"], round(sec["d"], 3), round(sec["bf"], 3), round(sec["t"], 3))
    if key not in PROFILES:
        d, bf, t = sec["d"], sec["bf"], sec["t"]
        if sec["family"] == "SQ":
            o, i = bf / 2, bf / 2 - t
            outer = Part.makePolygon([V(0, -o, -o), V(0, o, -o), V(0, o, o), V(0, -o, o), V(0, -o, -o)])
            inner = Part.makePolygon([V(0, -i, -i), V(0, i, -i), V(0, i, i), V(0, -i, i), V(0, -i, -i)])
            face = Part.Face(outer).cut(Part.Face(inner)).Faces[0]     # once per section size
        else:
            h, b, tw = d / 2, bf / 2, t / 2
            pts = [(-b, -h), (b, -h), (b, -h + t), (tw, -h + t), (tw, h - t), (b, h - t), (b, h), (-b, h),
                   (-b, h - t), (-tw, h - t), (-tw, -h + t), (-b, -h + t), (-b, -h)]
            face = Part.Face(Part.makePolygon([V(0, y, z) for y, z in pts]))
        PROFILES[key] = face
    return PROFILES[key]


def member_shape(sec, p1, p2):
    """One solid per member: the true section extruded along the member axis."""
    m, Lm = frame_matrix(p1, p2)
    shp = profile_face(sec).extrude(V(Lm, 0, 0))
    shp.transformShape(m)
    return shp


def g_part(name):
    p = doc.addObject("App::Part", "Sys_" + name)
    p.Label = name
    return p


# ------------------------------------------------------------------ build
summary = {}

# Basin --------------------------------------------------------------
basin = g_part("Basin")
w, sl, fl, cb = bs["wall"], bs["slab"], bs["floor"], bs["curb"]
shell = box(-w, -w, fl - sl, nL + w, W + w, cb).cut(box(0, 0, fl, nL, W, cb + 1))
nb, bw, bl = bs["sump_bays"], bs["bay_w"], bs["bay_l"]
sump_w = nb * bw + (nb - 1) * 300
sf = min(fl, bs["sump_floor"])
y0 = W / 2 - sump_w / 2
sump = box(nL + w, y0 - w, sf - sl, nL + w + bl + w, y0 + sump_w + w, cb)
for i in range(nb):
    a = y0 + i * (bw + 300)
    sump = sump.cut(box(nL - 1, a, sf, nL + w + bl, a + bw, cb + 1))
add("Basin_concrete", [shell, sump], basin)

# Structure ----------------------------------------------------------
struct = g_part("Structure")
by_mark = {}
frp_volume = 0.0
for i, mb in enumerate(DATA["members"]):
    sec = DATA["sections"][mb["group"]]
    shp = member_shape(sec, mb["p1"], mb["p2"])
    frp_volume += shp.Volume
    if PER_MEMBER:
        add(f"{mb['mark']}_{i:05d}", shp, struct)
    else:
        by_mark.setdefault(mb["mark"], []).append(shp)
for mark, shps in by_mark.items():
    add(f"Structure_{mark}", shps, struct)
frp_kg = frp_volume * 1e-9 * DATA["frp_density"]
summary["frp_volume_m3"] = frp_volume * 1e-9
summary["frp_kg_model"] = frp_kg
summary["members"] = len(DATA["members"])

# Fill and eliminators ----------------------------------------------
media = g_part("FillAndEliminators")
add("Fill", [box(c * L, 0, Z["fill_bottom"], (c + 1) * L, W, Z["fill_top"]) for c in range(n)], media)
add("Eliminators", [box(c * L, 0, Z["elim_bottom"], (c + 1) * L, W, Z["elim_top"]) for c in range(n)], media)

# Distribution -------------------------------------------------------
dsys = g_part("Distribution")
pipes = []
hr, lr, rr = dist["header_D"] / 2, dist["lateral_D"] / 2, dist["riser_D"] / 2
lat_y = sorted({p[1] for p in dist["nozzles"]})
for c in range(n):
    x0 = c * L
    xh = x0 + L / 2
    pipes.append(cyl(rr, (xh, -600, -600), (xh, -600, Z["header_cl"])))
    pipes.append(cyl(rr, (xh, -600, Z["header_cl"]), (xh, 0, Z["header_cl"])))
    pipes.append(cyl(hr, (xh, 0, Z["header_cl"]), (xh, W - 150, Z["header_cl"])))
    for y in lat_y:
        pipes.append(cyl(lr, (x0 + 150, y, Z["header_cl"]), (xh - hr, y, Z["header_cl"])))
        pipes.append(cyl(lr, (xh + hr, y, Z["header_cl"]), (x0 + L - 150, y, Z["header_cl"])))
    for nx, ny in dist["nozzles"]:
        pipes.append(cyl(40, (x0 + nx, ny, Z["header_cl"]), (x0 + nx, ny, Z["nozzle"])))
        pipes.append(Part.makeCone(40, 90, 120, V(x0 + nx, ny, Z["nozzle"]), V(0, 0, -1)))
add("Distribution", pipes, dsys)

# Casing -------------------------------------------------------------
cas = g_part("Casing")
tk = 10.0
lo_side = Z["inlet_top"] if DATA["two_sides"] else Z["inlet_top"]
lo_end = bs["curb"] if DATA["two_sides"] else Z["inlet_top"]
panels = [box(0, -tk, lo_side, nL, 0, Z["fan_deck"]), box(0, W, lo_side, nL, W + tk, Z["fan_deck"]),
          box(-tk, 0, lo_end, 0, W, Z["fan_deck"]), box(nL, 0, lo_end, nL + tk, W, Z["fan_deck"])]
for c in range(1, n):
    panels.append(box(c * L - tk / 2, 0, Z["elim_top"], c * L + tk / 2, W, Z["fan_deck"]))
add("Casing", panels, cas)

# Fan deck, stacks, mechanical ---------------------------------------
deck_p = g_part("FanDeck")
mech = g_part("Mechanical")
stacks = g_part("FanStacks")
rt = fan["D"] / 2 + 100
decks, stk, mec = [], [], []
for c in range(n):
    xc, yc = (c + 0.5) * L, W / 2
    decks.append(box(c * L, 0, Z["fan_deck"], (c + 1) * L, W, Z["fan_deck"] + 100)
                 .cut(Part.makeCylinder(rt, 300, V(xc, yc, Z["fan_deck"] - 100))))
    r1 = fan["Dx"] / 2
    outer = Part.makeCone(rt + 12, r1 + 12, fan["Hs"], V(xc, yc, Z["fan_deck"]))
    inner = Part.makeCone(rt, r1, fan["Hs"] + 1, V(xc, yc, Z["fan_deck"] - 0.5))
    stk.append(outer.cut(inner))
    zf = Z["fan"]
    mec.append(Part.makeCylinder(fan["hub"], 240, V(xc, yc, zf - 120)))
    blade_len = fan["D"] / 2 - 50 - fan["hub"]
    for j in range(8):
        bl_ = Part.makeBox(blade_len, 300, 20, V(xc + fan["hub"], yc - 150, zf - 10))
        bl_.rotate(V(xc, yc, zf), V(0, 0, 1), j * 45 + 11.5)
        mec.append(bl_)
    mec.append(box(xc - 350, yc - 350, Z["fan_deck"] - 50, xc + 350, yc + 350, zf - 150))
    my = yc + rt + 900
    mec.append(cyl(50, (xc, yc + 350, Z["fan_deck"] + 250), (xc, my - 350, Z["fan_deck"] + 250)))
    mec.append(cyl(250, (xc, my - 350, Z["fan_deck"] + 275), (xc, my + 350, Z["fan_deck"] + 275)))
    mec.append(box(xc - 150, yc - rt - 300, Z["fan_deck"] - 450, xc + 150, yc + rt + 300, Z["fan_deck"] - 150))
add("FanDeck", decks, deck_p)
add("FanStacks", stk, stacks)
add("Mechanical", mec, mech)

# Access: handrails and ladder ---------------------------------------
acc = g_part("Access")
rail = []
zd = Z["fan_deck"] + 100
edges = [((0, 0), (nL, 0)), ((nL, 0), (nL, W)), ((nL, W), (0, W)), ((0, W), (0, 0))]
for (xa, ya), (xb, yb) in edges:
    seg = math.hypot(xb - xa, yb - ya)
    k = max(1, math.ceil(seg / 1800))
    for i in range(k):
        x, y = xa + (xb - xa) * i / k, ya + (yb - ya) * i / k
        rail.append(cyl(25, (x, y, zd), (x, y, zd + 1070)))
    for h in (530, 1070):
        rail.append(cyl(20, (xa, ya, zd + h), (xb, yb, zd + h)))
lx = nL + 400
for xx in (lx, lx + 450):
    rail.append(cyl(25, (xx, W / 2, 0), (xx, W / 2, zd + 1100)))
for i in range(int((zd + 1000) // 300)):
    rail.append(cyl(15, (lx, W / 2, 300 * (i + 1)), (lx + 450, W / 2, 300 * (i + 1))))
add("Handrails_ladder", rail, acc)

doc.recompute()

# ------------------------------------------------------------------ export
tag = DATA["tag"]
fcstd = os.path.join(OUT, f"{tag}_tower.FCStd")
step = os.path.join(OUT, f"{tag}_tower.step")
doc.saveAs(fcstd)
import Import  # noqa: E402

Import.export([o for o in doc.Objects if o.TypeId == "App::Part"], step)

# coarse tessellation of the non-structural groups for a quick preview render
prev = {}
for o in objects:
    if o.Name.startswith("Structure") or o.Name[:3] in ("C1_", "TB1", "FB1", "DB1", "EB1", "KB1", "BR1"):
        continue
    pts, tris = o.Shape.tessellate(150.0 if o.Name.startswith("Distribution") else 60.0)
    prev[o.Name] = {"v": [[round(p.x), round(p.y), round(p.z)] for p in pts], "f": [list(t) for t in tris]}
prev["_members"] = [[m["p1"], m["p2"], m["mark"]] for m in DATA["members"]]
json.dump(prev, open(os.path.join(OUT, "preview_mesh.json"), "w"))

bb = None
vols = {}
for o in objects:
    s = o.Shape
    bb = s.BoundBox if bb is None else bb.united(s.BoundBox)
    key = o.Name if not o.Name[:3] in ("C1_", "TB1", "FB1", "DB1", "EB1", "KB1", "BR1") else "Structure_members"
    vols[key] = vols.get(key, 0.0) + s.Volume * 1e-9
summary.update({"fcstd": fcstd, "step": step, "objects": len(objects),
                "bbox_mm": [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax],
                "volumes_m3": vols, "seconds": time.time() - T0, "freecad": ".".join(FreeCAD.Version()[:3])})
print("CTMODEL " + json.dumps(summary))
sys.stdout.flush()
