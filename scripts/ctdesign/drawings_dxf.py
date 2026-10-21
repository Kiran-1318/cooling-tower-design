"""Fabrication-oriented drawing set (DXF + SVG + PDF + PNG) built with ezdxf.

  GA-001  General arrangement: plan at fan deck, side (inlet face) elevation, end elevation
  GA-002  Sections A-A (across a cell) and B-B (along the row) with all zones and elevations
  ME-003  Fan deck and mechanical: deck plan of a typical cell, fan stack detail, fan/drive data
  WD-004  Water distribution: typical cell nozzle/lateral/header layout, schedules, pump head
  CV-005  Basin: plan with column bases, sump and connections, sump section, base reactions
  ST-006  FRP framing plans per tier of a typical cell with member marks, member schedule
  ST-007  FRP framing elevations of a typical cell with member marks, connection schedule
  DS-008  Datasheet

Coordinates: tower x along the row, z across a cell, y = elevation above the basin operating
water level (EL 0.000). All model dimensions in mm.
"""
from __future__ import annotations

import math
import string
from pathlib import Path

import fitz

from .dxfsheet import Sheet, View
from .report import datasheet_rows

M = 1000.0
MARK = {"column": "C1", "tie_beam": "TB1", "fill_beam": "FB1", "dist_beam": "DB1", "elim_beam": "EB1",
        "deck_beam": "KB1", "brace": "BR1"}
TIER_GROUP = {"tie": "tie_beam", "fill": "fill_beam", "dist": "dist_beam", "elim": "elim_beam", "deck": "deck_beam"}
TIER_NAME = {"tie": "BASIN TIE", "fill": "FILL SUPPORT", "dist": "DISTRIBUTION SUPPORT", "elim": "ELIMINATOR SUPPORT",
             "deck": "FAN DECK"}


def zlabel(i: int) -> str:
    return string.ascii_uppercase[i] if i < 26 else string.ascii_uppercase[i // 26 - 1] + string.ascii_uppercase[i % 26]


class Ctx:
    def __init__(self, d: dict, b):
        self.d, self.b, self.s = d, b, b.spec
        g = d["geom"]
        self.g, self.n = g, g.cells
        self.L, self.W = g.L * M, g.W * M
        self.nL = self.n * self.L
        self.z = {k: v * M for k, v in g.z.items()}
        fn = d["fan"]
        self.fan = fn
        self.D, self.Dx, self.Hs = fn["D"] * M, fn["stack_exit_D"] * M, fn["stack_H"] * M
        bs = d["basin"]
        self.bs = bs
        self.floor = -bs["water_depth_m"] * M
        self.curb = max(self.z["curb"], bs["freeboard_m"] * M)
        self.slab = 300.0
        self.wall = 300.0
        st = d.get("structure")
        self.st = st
        if st:
            self.xs = [x * M for x in st["grid"]["xs"] if x <= g.L + 1e-6]
            self.zs = [z * M for z in st["grid"]["zs"]]
            self.tiers = [(n, y * M) for n, y in st["grid"]["tiers"]]
            self.colb = st["groups"]["column"]["bf_mm"]
        else:
            from .structure import _grid
            lo, hi = self.s["structure"]["column_bay_m"]
            self.xs = [x * M for x in _grid(g.L, lo, hi)]
            self.zs = [z * M for z in _grid(g.W, lo, hi)]
            self.tiers = []
            self.colb = 100.0
        self.all_xs = sorted({round(c * self.L + x, 1) for c in range(self.n) for x in self.xs})
        hy = d["hyd"]
        self.hy = hy
        self.hdr = hy["header_DN"]
        self.lat = hy["lateral_DN"]
        self.ris = hy["riser_DN"]
        self.two = self.s["tower"]["air_inlets"] == "two_sides"
        self.base = self.floor - self.slab
        self.top = self.z["stack_top"]

    def meta(self, sheet_no: str, total: int) -> dict:
        p = self.s["project"]
        return {"project": p["name"], "client": p.get("client", ""), "site": p.get("site_name", ""), "tag": p["tag"],
                "equipment": f"{self.n}-cell counterflow cooling tower", "rev": p.get("revision", "A"),
                "date": p.get("date", ""), "sheet": f"{sheet_no} of {total}"}


GENERAL_NOTES = ["Dimensions in mm; elevations in m relative to the basin operating water level (EL 0.000).",
                 "Mechanical induced-draft counterflow cooling tower, pultruded FRP structure (ASCE/SEI 74).",
                 "Thermal design CTI (Merkel/Poppe); loads ASCE 7; see the design report for all assumptions.",
                 "Fill, eliminator and fan data are indicative until vendor selections are made.",
                 "Basin is civil works by others; dimensions shown are hydraulic minimums."]


# ============================================================================ shared elements
def stack_poly(c: Ctx, xc: float, X, Y):
    r0, r1 = c.D / 2 + 100, c.Dx / 2
    return [(X(xc - r0), Y(c.z["fan_deck"])), (X(xc - r1), Y(c.top)), (X(xc + r1), Y(c.top)), (X(xc + r0), Y(c.z["fan_deck"]))]


def handrail(sh: Sheet, c: Ctx, x0, x1, X, Y):
    yd = c.z["fan_deck"]
    sh.line((X(x0), Y(yd + 1070)), (X(x1), Y(yd + 1070)), "THIN")
    sh.line((X(x0), Y(yd + 530)), (X(x1), Y(yd + 530)), "THIN")
    n = max(1, math.ceil((x1 - x0) / 1800))
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        sh.line((X(x), Y(yd)), (X(x), Y(yd + 1070)), "THIN")


def basin_profile(sh: Sheet, c: Ctx, a0, a1, X, Y, hidden=False):
    """Basin walls/slab in section or elevation over horizontal extent a0..a1 (inner faces)."""
    lay = "HIDDEN" if hidden else "CONCRETE"
    w, sl = c.wall, c.slab
    outer = [(X(a0 - w), Y(c.curb)), (X(a0 - w), Y(c.floor - sl)), (X(a1 + w), Y(c.floor - sl)), (X(a1 + w), Y(c.curb)),
             (X(a1), Y(c.curb)), (X(a1), Y(c.floor)), (X(a0), Y(c.floor)), (X(a0), Y(c.curb))]
    sh.pline(outer, lay, close=True)
    if not hidden:
        sh.hatch(outer, "ANSI31", 2.5, "HATCH")
    sh.line((X(a0), Y(0)), (X(a1), Y(0)), "WATER")
    for i in range(3):
        xx = a0 + (a1 - a0) * (0.2 + 0.25 * i)
        sh.line((X(xx), Y(-120)), (X(xx + 600), Y(-120)), "WATER")


# ============================================================================ GA-001
def plan_view(c: Ctx) -> View:
    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Z = lambda z: oy + z
        P = sh.P
        sh.rect(X(0), Z(0), X(c.nL), Z(c.W), "OUTLINE")
        for k in range(1, c.n):
            sh.line((X(k * c.L), Z(0)), (X(k * c.L), Z(c.W)), "OUTLINE")
        for i, x in enumerate(c.all_xs):
            sh.line((X(x), Z(-P(4))), (X(x), Z(c.W + P(20))), "CENTER")
            sh.bubble(X(x), Z(c.W + P(24)), str(i + 1))
        for k, z in enumerate(c.zs):
            sh.line((X(-P(9)), Z(z)), (X(c.nL + P(4)), Z(z)), "CENTER")
            sh.bubble(X(-P(13)), Z(z), zlabel(k))
            for x in c.all_xs:
                h = c.colb / 2
                sh.rect(X(x - h), Z(z - h), X(x + h), Z(z + h), "STRUCT")
        for k in range(c.n):
            xc, zc = (k + 0.5) * c.L, c.W / 2
            sh.circle((X(xc), Z(zc)), c.Dx / 2, "OUTLINE")
            sh.circle((X(xc), Z(zc)), c.D / 2 + 100, "THIN")
            sh.circle((X(xc), Z(zc)), c.D / 2, "HIDDEN")
            sh.circle((X(xc), Z(zc)), max(c.D * 0.1, 250), "EQUIP")
            for j in range(8):
                a = j * math.pi / 4 + 0.2
                sh.line((X(xc + 0.12 * c.D * math.cos(a)), Z(zc + 0.12 * c.D * math.sin(a))),
                        (X(xc + 0.48 * c.D * math.cos(a)), Z(zc + 0.48 * c.D * math.sin(a))), "EQUIP")
            sh.text(X(xc), Z(zc - c.Dx / 2 - P(4)), f"CELL {k + 1}", 3.0, align="C")
            sh.circle((X(xc), Z(-600)), c.ris / 2, "PIPE")
            for zz, z1 in ((-P(16), -P(4)), (c.W + P(16), c.W + P(4))) if c.two else ():
                for dx in (-c.L / 4, c.L / 4):
                    sh.arrow((X(xc + dx), Z(zz)), (X(xc + dx), Z(z1)))
        sh.text(X(c.L / 2 + c.ris / 2 + P(2)), Z(-600), f"RISER DN{c.ris} (TYP.)", 2.2, align="L")
        if c.two:
            sh.text(X(c.L / 4 + P(2)), Z(-P(12)), "AIR INLET", 2.2, align="L")
        lx = c.nL + 400
        sh.rect(X(lx), Z(c.W / 2 - 350), X(lx + 600), Z(c.W / 2 + 350), "THIN")
        sh.text(X(lx + 300), Z(c.W / 2 + 350 + P(2)), "LADDER", 2.2, align="BC")
        sh.dim_h(X(0), X(c.nL), Z(-P(26)), Z(0))
        sh.dim_h(X(0), X(c.L), Z(-P(19)), Z(0))
        sh.dim_v(Z(0), Z(c.W), X(-P(22)), X(0))
    return View("PLAN AT FAN DECK", c.nL + 1200, c.W, draw, (32, 18, 34, 40))


def side_elevation(c: Ctx) -> View:
    y0 = c.base

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Y = lambda y: oy + (y - y0)
        P = sh.P
        z = c.z
        sh.line((X(-P(8)), Y(0)), (X(c.nL + P(8)), Y(0)), "THIN")
        sh.text(X(-P(8)), Y(0) + P(1), "GRADE (ASSUMED)", 1.8, align="BL")
        basin_profile(sh, c, 0, c.nL, X, Y, hidden=True)
        for x in c.all_xs:
            sh.line((X(x), Y(c.curb)), (X(x), Y(z["inlet_top"])), "STRUCT")
        sh.rect(X(0), Y(z["inlet_top"]), X(c.nL), Y(z["fan_deck"]), "OUTLINE")
        sh.rect(X(0), Y(z["fill_bottom"]), X(c.nL), Y(z["fill_top"]), "HIDDEN")
        sh.rect(X(0), Y(z["elim_bottom"]), X(c.nL), Y(z["elim_top"]), "HIDDEN")
        sh.line((X(0), Y(z["fan_deck"] + 100)), (X(c.nL), Y(z["fan_deck"] + 100)), "OUTLINE")
        handrail(sh, c, 0, c.nL, X, Y)
        for k in range(c.n):
            xc = (k + 0.5) * c.L
            sh.pline(stack_poly(c, xc, X, Y), "OUTLINE")
            sh.rect(X(xc - c.ris / 2), Y(-600), X(xc + c.ris / 2), Y(z["header_cl"]), "PIPE")
            sh.text(X(xc + c.L / 4), Y((c.curb + z["inlet_top"]) / 2), "AIR INLET", 2.5, align="C")
        sh.text(X(c.L / 2 + c.ris / 2 + P(1)), Y(z["header_cl"] - 300), f"RISER DN{c.ris}", 2.0, align="L")
        sh.text(X(c.L * 0.08), Y((z["fill_bottom"] + z["fill_top"]) / 2), "FILL (HIDDEN)", 2.0, align="L")
        lx = c.nL + 400
        for xx in (lx, lx + 450):
            sh.line((X(xx), Y(0)), (X(xx), Y(z["fan_deck"] + 1100)), "THIN")
        for i in range(int((z["fan_deck"] + 1100) // 300)):
            sh.line((X(lx), Y(300 * (i + 1))), (X(lx + 450), Y(300 * (i + 1))), "THIN")
        sh.levels(X(c.nL + 1200), [("STACK TOP", Y(c.top), c.top / M), ("FAN DECK", Y(z["fan_deck"]), z["fan_deck"] / M),
                                   ("ELIMINATOR", Y(z["elim_bottom"]), z["elim_bottom"] / M),
                                   ("FILL TOP", Y(z["fill_top"]), z["fill_top"] / M),
                                   ("FILL BOTTOM", Y(z["fill_bottom"]), z["fill_bottom"] / M),
                                   ("INLET TOP", Y(z["inlet_top"]), z["inlet_top"] / M),
                                   ("BASIN CURB", Y(c.curb), c.curb / M), ("WATER LEVEL", Y(0), 0.0),
                                   ("BASIN FLOOR", Y(c.floor), c.floor / M)])
        sh.dim_v(Y(c.curb), Y(z["inlet_top"]), X(-P(10)), X(0))
        sh.dim_v(Y(z["inlet_top"]), Y(z["fan_deck"]), X(-P(10)), X(0))
        sh.dim_v(Y(z["fan_deck"]), Y(c.top), X(-P(10)), X(c.L / 2 - c.Dx / 2))
        sh.dim_v(Y(0), Y(c.top), X(-P(19)), X(0))
        sh.dim_h(X(0), X(c.nL), Y(c.base) - P(10), Y(c.base))
    return View("SIDE ELEVATION (AIR INLET FACE)", c.nL + 1700, c.top - y0, draw, (30, 58, 10, 26))


def end_elevation(c: Ctx) -> View:
    y0, x0 = c.base, -1200.0

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + (x - x0)
        Y = lambda y: oy + (y - y0)
        P = sh.P
        z = c.z
        sh.line((X(x0), Y(0)), (X(c.W + P(6)), Y(0)), "THIN")
        basin_profile(sh, c, 0, c.W, X, Y, hidden=True)
        bottom = c.curb if c.two else z["inlet_top"]
        sh.rect(X(0), Y(bottom), X(c.W), Y(z["fan_deck"]), "OUTLINE")
        if not c.two:
            for zz in c.zs:
                sh.line((X(zz), Y(c.curb)), (X(zz), Y(z["inlet_top"])), "STRUCT")
        sh.line((X(0), Y(z["fan_deck"] + 100)), (X(c.W), Y(z["fan_deck"] + 100)), "OUTLINE")
        handrail(sh, c, 0, c.W, X, Y)
        sh.pline(stack_poly(c, c.W / 2, X, Y), "OUTLINE")
        r = c.ris / 2
        sh.pline([(X(-600 - r), Y(-600)), (X(-600 - r), Y(z["header_cl"] + r)), (X(0), Y(z["header_cl"] + r))], "PIPE")
        sh.pline([(X(-600 + r), Y(-600)), (X(-600 + r), Y(z["header_cl"] - r)), (X(0), Y(z["header_cl"] - r))], "PIPE")
        sh.text(X(-600 - r - P(1)), Y(z["header_cl"] / 2), f"RISER DN{c.ris}", 2.0, align="R", rot=0)
        sh.dim_h(X(0), X(c.W), Y(c.base) - P(10), Y(c.base))
        sh.dim_h(X(c.W / 2 - c.Dx / 2), X(c.W / 2 + c.Dx / 2), Y(c.top) + P(8), Y(c.top))
        sh.text(X(c.W / 2), Y(z["inlet_top"] / 2 + c.curb / 2), "END WALL (CASED)" if c.two else "AIR INLET", 2.5, align="C")
    return View("END ELEVATION", c.W - x0, c.top - y0, draw, (25, 15, 18, 26))


# ============================================================================ GA-002 sections
def section_cross(c: Ctx) -> View:
    """Section A-A across a cell (z-y) at the cell centre."""
    y0, x0 = c.base, -1500.0

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + (x - x0)
        Y = lambda y: oy + (y - y0)
        P = sh.P
        z, W = c.z, c.W
        basin_profile(sh, c, 0, W, X, Y)
        for zz in c.zs:
            sh.line((X(zz), Y(c.floor)), (X(zz), Y(z["fan_deck"])), "STRUCT")
        for name, ty in c.tiers[1:]:
            sh.line((X(0), Y(ty)), (X(W), Y(ty)), "STRUCT")
        if c.two:
            for zz in (0.0, W):
                sh.line((X(zz), Y(z["inlet_top"])), (X(zz), Y(z["fan_deck"])), "OUTLINE")
        sh.rect(X(0), Y(z["fill_bottom"]), X(W), Y(z["fill_top"]), "FILLPACK")
        sh.hatch([(X(0), Y(z["fill_bottom"])), (X(W), Y(z["fill_bottom"])), (X(W), Y(z["fill_top"])), (X(0), Y(z["fill_top"]))],
                 "ANSI37", 3.0, "FILLPACK")
        sh.rect(X(0), Y(z["elim_bottom"]), X(W), Y(z["elim_top"]), "FILLPACK")
        sh.hatch([(X(0), Y(z["elim_bottom"])), (X(W), Y(z["elim_bottom"])), (X(W), Y(z["elim_top"])), (X(0), Y(z["elim_top"]))],
                 "ANSI31", 1.5, "FILLPACK")
        hr = c.hdr / 2
        sh.rect(X(0), Y(z["header_cl"] - hr), X(W), Y(z["header_cl"] + hr), "PIPE")
        lat_z = sorted({p[1] * M for p in c.hy["nozzle_xy"]})
        for lz in lat_z:
            sh.circle((X(lz), Y(z["header_cl"])), max(c.lat / 2, 30), "PIPE")
            sh.pline([(X(lz), Y(z["nozzle"])), (X(lz - 90), Y(z["nozzle"] - 140)), (X(lz + 90), Y(z["nozzle"] - 140))], "PIPE", close=True)
        r = c.ris / 2
        sh.pline([(X(-600 - r), Y(-600)), (X(-600 - r), Y(z["header_cl"] + r)), (X(0), Y(z["header_cl"] + r))], "PIPE")
        sh.pline([(X(-600 + r), Y(-600)), (X(-600 + r), Y(z["header_cl"] - r)), (X(0), Y(z["header_cl"] - r))], "PIPE")
        # fan deck with fan opening, stack, fan, mechanical
        zc = W / 2
        rt = c.D / 2 + 100
        sh.line((X(0), Y(z["fan_deck"])), (X(zc - rt), Y(z["fan_deck"])), "OUTLINE")
        sh.line((X(zc + rt), Y(z["fan_deck"])), (X(W), Y(z["fan_deck"])), "OUTLINE")
        for sgn in (-1, 1):
            sh.line((X(zc + sgn * rt), Y(z["fan_deck"])), (X(zc + sgn * c.Dx / 2), Y(c.top)), "OUTLINE")
        sh.line((X(zc - c.D / 2 + 50), Y(z["fan"])), (X(zc + c.D / 2 - 50), Y(z["fan"])), "EQUIP")
        hub = max(0.1 * c.D, 250)
        sh.rect(X(zc - hub), Y(z["fan"] - 120), X(zc + hub), Y(z["fan"] + 120), "EQUIP")
        sh.rect(X(zc - 350), Y(z["fan_deck"] - 50), X(zc + 350), Y(z["fan"] - 150), "EQUIP")
        mz = zc + rt + 900
        sh.line((X(zc + 350), Y(z["fan_deck"] + 250)), (X(mz - 350), Y(z["fan_deck"] + 250)), "EQUIP")
        sh.rect(X(mz - 350), Y(z["fan_deck"]), X(mz + 350), Y(z["fan_deck"] + 550), "EQUIP")
        sh.line((X(zc - rt - 300), Y(z["fan_deck"] - 300)), (X(zc + rt + 300), Y(z["fan_deck"] - 300)), "EQUIP")
        handrail(sh, c, 0, W, X, Y)
        # flows and zone labels
        for zz, sgn in ((0.0, 1), (W, -1)) if c.two else ():
            sh.arrow((X(zz - sgn * P(14)), Y((c.curb + z["inlet_top"]) / 2)), (X(zz + sgn * P(3)), Y((c.curb + z["inlet_top"]) / 2)))
        sh.arrow((X(zc), Y(z["fan_deck"] - 900)), (X(zc), Y(c.top + P(10))))
        for lz in lat_z[::max(1, len(lat_z) // 3)]:
            sh.arrow((X(lz), Y(z["nozzle"] - 250)), (X(lz), Y(z["fill_top"] + 80)), "WATER", 2.0)
        lab = [(f"VELOCITY RECOVERY STACK, EXIT DIA {c.Dx:.0f}" if c.fan["stack"] == "velocity_recovery" else "FAN STACK",
                (z["fan_deck"] + c.top) / 2),
               (f"PLENUM", (z["elim_top"] + z["fan_deck"]) / 2 - 400),
               ("DRIFT ELIMINATOR", (z["elim_bottom"] + z["elim_top"]) / 2),
               (f"HEADER DN{c.hdr} / LATERALS DN{c.lat}", z["header_cl"] + c.hdr / 2 + 200),
               ("SPRAY ZONE", (z["fill_top"] + z["nozzle"]) / 2 - 60),
               (f"FILL {c.g.depth * M:.0f} DEEP", (z["fill_bottom"] + z["fill_top"]) / 2),
               ("RAIN ZONE", (z["inlet_top"] + z["fill_bottom"]) / 2 + 300),
               ("COLD WATER BASIN", -0.45 * c.bs["water_depth_m"] * M)]
        last = None
        for t, y in sorted(lab, key=lambda it: it[1]):          # push labels apart, no overlaps
            yy = Y(y) if last is None else max(Y(y), last + P(4.0))
            sh.text(X(W + P(4)), yy, t, 2.2, align="L")
            last = yy
        sh.text(X(-600), Y(-600) - P(3), "HOT WATER IN", 2.0, align="TC")
        sh.text(X(zc - c.D / 2 - P(2)), Y(z["fan"] + 250), f"FAN DIA {c.D:.0f}", 2.0, align="R")
        sh.text(X(mz), Y(z["fan_deck"] + 550) + P(1), "MOTOR", 2.0, align="BC")
        # dimensions
        xd = X(W) + P(78)
        chain = [0.0, c.curb, z["inlet_top"], z["fill_bottom"], z["fill_top"], z["nozzle"], z["elim_bottom"], z["fan_deck"], c.top]
        for a, b2 in zip(chain[:-1], chain[1:]):
            if b2 - a > 1:
                sh.dim_v(Y(a), Y(b2), xd, X(W))
        sh.dim_h(X(0), X(W), Y(c.base) - P(10), Y(c.base))
        sh.levels(X(-1500) - P(2), [("FAN DECK", Y(z["fan_deck"]), z["fan_deck"] / M), ("STACK TOP", Y(c.top), c.top / M),
                                    ("WATER LEVEL", Y(0), 0.0), ("BASIN FLOOR", Y(c.floor), c.floor / M)], side="L")
    return View("SECTION A-A (ACROSS CELL)", c.W - x0 + 300, c.top - y0, draw, (45, 100, 16, 26))


def section_long(c: Ctx) -> View:
    """Section B-B along the row (x-y) at the cell centre line."""
    n_draw = min(c.n, 2)
    y0, x0 = c.base, -300.0
    w = n_draw * c.L + 300

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + (x - x0)
        Y = lambda y: oy + (y - y0)
        P = sh.P
        z = c.z
        x1 = n_draw * c.L
        basin_profile(sh, c, 0, x1 if c.n <= 2 else x1 + 200, X, Y)
        for x in c.all_xs:
            if x <= x1 + 1:
                sh.line((X(x), Y(c.floor)), (X(x), Y(z["fan_deck"])), "STRUCT")
        for name, ty in c.tiers[1:]:
            sh.line((X(0), Y(ty)), (X(x1), Y(ty)), "STRUCT")
        sh.line((X(0), Y(c.curb)), (X(0), Y(z["fan_deck"])), "OUTLINE")
        if c.n <= 2:
            sh.line((X(x1), Y(c.curb)), (X(x1), Y(z["fan_deck"])), "OUTLINE")
        for k in range(n_draw):
            a = k * c.L
            if k:
                sh.line((X(a), Y(z["elim_top"])), (X(a), Y(z["fan_deck"])), "OUTLINE")
            sh.rect(X(a), Y(z["fill_bottom"]), X(a + c.L), Y(z["fill_top"]), "FILLPACK")
            sh.hatch([(X(a), Y(z["fill_bottom"])), (X(a + c.L), Y(z["fill_bottom"])), (X(a + c.L), Y(z["fill_top"])),
                      (X(a), Y(z["fill_top"]))], "ANSI37", 3.0, "FILLPACK")
            sh.rect(X(a), Y(z["elim_bottom"]), X(a + c.L), Y(z["elim_top"]), "FILLPACK")
            sh.line((X(a + 150), Y(z["header_cl"])), (X(a + c.L - 150), Y(z["header_cl"])), "PIPE")
            sh.circle((X(a + c.L / 2), Y(z["header_cl"])), c.hdr / 2, "PIPE")
            for nx in sorted({p[0] * M for p in c.hy["nozzle_xy"]}):
                sh.pline([(X(a + nx), Y(z["nozzle"])), (X(a + nx - 90), Y(z["nozzle"] - 140)), (X(a + nx + 90), Y(z["nozzle"] - 140))],
                         "PIPE", close=True)
            xc = a + c.L / 2
            sh.pline(stack_poly(c, xc, X, Y), "OUTLINE")
            sh.line((X(a), Y(z["fan_deck"])), (X(xc - c.D / 2 - 100), Y(z["fan_deck"])), "OUTLINE")
            sh.line((X(xc + c.D / 2 + 100), Y(z["fan_deck"])), (X(a + c.L), Y(z["fan_deck"])), "OUTLINE")
            sh.line((X(xc - c.D / 2 + 50), Y(z["fan"])), (X(xc + c.D / 2 - 50), Y(z["fan"])), "EQUIP")
            sh.rect(X(xc - 350), Y(z["fan_deck"] - 50), X(xc + 350), Y(z["fan"] - 150), "EQUIP")
            sh.text(X(xc), Y(z["fan_deck"] - 700), f"CELL {k + 1}", 3.0, align="C")
            sh.arrow((X(xc), Y(z["inlet_top"] - 300)), (X(xc), Y(c.top + P(10))))
        handrail(sh, c, 0, x1, X, Y)
        if c.n > 2:
            xb = x1 + 150
            sh.pline([(X(xb), Y(c.base)), (X(xb), Y(3000)), (X(xb + 200), Y(3300)), (X(xb - 200), Y(3700)), (X(xb), Y(4000)),
                      (X(xb), Y(c.top))], "THIN")
            sh.text(X(xb) + P(2), Y(c.top), f"CELLS 3 TO {c.n} SIMILAR", 2.5, align="TL")
        sh.text(X(150), Y((c.curb + z["inlet_top"]) / 2), "AIR INLETS ON BOTH LONG FACES (BEYOND)" if c.two else "", 2.0, align="L")
        sh.dim_h(X(0), X(c.L), Y(c.base) - P(10), Y(c.base))
        sh.dim_h(X(c.L / 2 - c.D / 2), X(c.L / 2 + c.D / 2), Y(z["fan"]) + P(12), Y(z["fan"]), text=f"FAN DIA {c.D:.0f}")
    return View("SECTION B-B (ALONG ROW)", w, c.top - y0, draw, (16, 22, 16, 26))


# ============================================================================ tables as views
def table_view(title: str, rows: list, widths: list, h: float = 2.5) -> View:
    """A table sized in paper mm (independent of the sheet scale)."""
    W = sum(widths)
    H = len(rows) * h * 2.2

    def draw(sh: Sheet, ox, oy):
        sh.table(ox, oy + sh.P(H), rows, widths, h)
    v = View(title, 0.0, 0.0, draw, (0.0, W, H + 9, 4))
    v.paper = True
    return v


def cell_grid(sh: Sheet, c: Ctx, X, Z, bubbles=True):
    P = sh.P
    for i, x in enumerate(c.xs):
        sh.line((X(x), Z(-P(3))), (X(x), Z(c.W + P(9))), "CENTER")
        if bubbles:
            sh.bubble(X(x), Z(c.W + P(13)), str(i + 1))
    for k, z in enumerate(c.zs):
        sh.line((X(-P(9)), Z(z)), (X(c.L + P(3)), Z(z)), "CENTER")
        if bubbles:
            sh.bubble(X(-P(13)), Z(z), zlabel(k))
        for x in c.xs:
            h = c.colb / 2
            sh.rect(X(x - h), Z(z - h), X(x + h), Z(z + h), "STRUCT")


# ============================================================================ ME-003
def deck_plan(c: Ctx) -> View:
    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Z = lambda z: oy + z
        P = sh.P
        L, W = c.L, c.W
        sh.rect(X(0), Z(0), X(L), Z(W), "OUTLINE")
        sh.rect(X(100), Z(100), X(L - 100), Z(W - 100), "HIDDEN")
        cell_grid(sh, c, X, Z)
        xc, zc = L / 2, W / 2
        rt = c.D / 2 + 100
        sh.circle((X(xc), Z(zc)), rt + 150, "OUTLINE")
        sh.circle((X(xc), Z(zc)), rt, "OUTLINE")
        sh.circle((X(xc), Z(zc)), c.Dx / 2, "THIN")
        hub = max(0.1 * c.D, 250)
        sh.circle((X(xc), Z(zc)), hub, "EQUIP")
        for j in range(8):
            a = j * math.pi / 4 + 0.2
            sh.line((X(xc + hub * math.cos(a)), Z(zc + hub * math.sin(a))),
                    (X(xc + 0.48 * c.D * math.cos(a)), Z(zc + 0.48 * c.D * math.sin(a))), "EQUIP")
        sh.rect(X(xc - 350), Z(zc - 350), X(xc + 350), Z(zc + 350), "EQUIP")
        mz = zc + rt + 900
        sh.line((X(xc), Z(zc + 350)), (X(xc), Z(mz - 350)), "EQUIP")
        sh.rect(X(xc - 275), Z(mz - 350), X(xc + 275), Z(mz + 350), "EQUIP")
        for dx in (-150, 150):
            sh.line((X(xc + dx), Z(zc - rt - 300)), (X(xc + dx), Z(min(W - 100, mz + 450))), "HIDDEN")
        sh.rect(X(300), Z(300), X(1100), Z(1100), "THIN")
        sh.text(X(1100) + P(1.5), Z(700), "ACCESS HATCH", 2.0, align="L")
        sh.text(X(xc + 275) + P(1.5), Z(mz), f"MOTOR {c.fan['motor_kW']} kW", 2.2, align="L")
        sh.text(X(xc + 350) + P(1.5), Z(zc - 200), f"GEAR REDUCER {c.fan['gear_ratio']:.2f}:1", 2.2, align="L")
        sh.text(X(xc - 150) - P(1.5), Z(zc - rt - 150), "MECHANICAL EQUIPMENT SUPPORT (BELOW)", 2.0, align="R")
        sh.text(X(xc), Z(zc + rt + 150) + P(1.5), f"FAN STACK (BASE DIA {2 * (rt + 150):.0f})", 2.2, align="BC")
        sh.text(X(L - 150), Z(W - 150) - P(2), "HANDRAIL ON DECK PERIMETER", 2.0, align="TL" if False else "BR")
        sh.dim_h(X(0), X(L), Z(-P(16)), Z(0))
        sh.dim_v(Z(0), Z(W), X(L + P(12)), X(L))
        sh.dim_h(X(xc - c.D / 2), X(xc + c.D / 2), Z(zc - c.D / 4), text=f"FAN DIA {c.D:.0f}")
        sh.dim_v(Z(zc), Z(mz), X(xc - c.D / 2 - P(4)), X(xc))
    return View("FAN DECK PLAN - TYPICAL CELL", c.L, c.W, draw, (30, 30, 30, 30))


def stack_detail(c: Ctx) -> View:
    R = c.D / 2 + 1200
    y0 = c.z["fan_deck"] - 900

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + (x + R)
        Y = lambda y: oy + (y - y0)
        P = sh.P
        z = c.z
        rt = c.D / 2 + 100
        sh.line((X(-R), Y(z["fan_deck"])), (X(-rt - 150), Y(z["fan_deck"])), "OUTLINE")
        sh.line((X(rt + 150), Y(z["fan_deck"])), (X(R), Y(z["fan_deck"])), "OUTLINE")
        sh.line((X(-R), Y(z["fan_deck"] - 150)), (X(R), Y(z["fan_deck"] - 150)), "THIN")
        for sg in (-1, 1):
            sh.pline([(X(sg * (rt + 150)), Y(z["fan_deck"])), (X(sg * rt), Y(z["fan_deck"] + 150)),
                      (X(sg * rt), Y(z["fan"] + 300)), (X(sg * c.Dx / 2), Y(c.top))], "OUTLINE")
        sh.line((X(-c.D / 2 + 50), Y(z["fan"])), (X(c.D / 2 - 50), Y(z["fan"])), "EQUIP")
        hub = max(0.1 * c.D, 250)
        sh.rect(X(-hub), Y(z["fan"] - 120), X(hub), Y(z["fan"] + 120), "EQUIP")
        sh.rect(X(-350), Y(z["fan_deck"] - 50), X(350), Y(z["fan"] - 150), "EQUIP")
        sh.line((X(-rt - 300), Y(z["fan_deck"] - 300)), (X(rt + 300), Y(z["fan_deck"] - 300)), "EQUIP")
        sh.dim_h(X(-c.Dx / 2), X(c.Dx / 2), Y(c.top) + P(8), Y(c.top))
        sh.dim_h(X(-rt), X(rt), Y(z["fan"]) - P(8), Y(z["fan"]))
        sh.dim_v(Y(z["fan_deck"]), Y(c.top), X(R) + P(6), X(c.Dx / 2))
        sh.dim_v(Y(z["fan_deck"]), Y(z["fan"]), X(-R) - P(6), X(-c.D / 2))
        sh.text(X(c.D / 2) + P(1), Y(z["fan"]) + P(1), "FAN BLADE PLANE", 2.0, align="BL")
        sh.text(X(0), Y(z["fan_deck"] - 300) - P(1.5), "TORQUE TUBE / MECHANICAL SUPPORT", 2.0, align="TC")
        sh.text(X(-R), Y(z["fan_deck"]) + P(1), "FAN DECK", 2.0, align="BL")
        kind = "VELOCITY RECOVERY" if c.fan["stack"] == "velocity_recovery" else "STRAIGHT"
        sh.text(X(0), Y((z["fan"] + c.top) / 2 + 400), f"{kind} FRP STACK", 2.5, align="C")
        sh.text(X(0), Y((z["fan"] + c.top) / 2 - 200), f"TIP CLEARANCE {100:.0f} MAX", 2.0, align="C")
    return View("FAN STACK DETAIL", 2 * R, c.top - y0, draw, (25, 25, 18, 24))


def fan_table(c: Ctx) -> View:
    fn, d = c.fan, c.d
    rows = [("ITEM", "VALUE"), ("Fans", f"{c.n} x {fn['D']:.1f} m, {fn['fan_rpm']:.0f} rpm, tip {fn['tip_speed']:.0f} m/s"),
            ("Air flow per fan", f"{fn['Q']:.1f} m3/s"), ("Fan static / total pressure", f"{fn['dP_fan_static']:.0f} / {fn['dP_total']:.0f} Pa"),
            ("Shaft power per fan", f"{fn['P_shaft_kW']:.1f} kW"),
            ("Motor", f"{fn['motor_kW']} kW, {c.s['tower']['motor_poles']}-pole, {c.s['tower']['power_supply']}"),
            ("Gear reducer ratio", f"{fn['gear_ratio']:.2f} : 1"),
            ("Stack", f"{fn['stack'].replace('_', ' ')}, {fn['stack_H']:.1f} m, exit {fn['stack_exit_D']:.2f} m")]
    if c.st:
        rows += [("Equipment mass per cell (est.)", f"{c.st['equipment_kg_per_cell']:.0f} kg"),
                 ("Stack mass per cell (est.)", f"{c.st['stack_kg_per_cell']:.0f} kg")]
    rows.append(("Note", "Fan, gear and motor by vendor (indicative)"))
    return table_view("FAN AND DRIVE DATA", rows, [62, 80])


# ============================================================================ WD-004
def dist_plan(c: Ctx) -> View:
    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Z = lambda z: oy + 600 + c.ris / 2 + z
        P = sh.P
        L, W = c.L, c.W
        sh.rect(X(0), Z(0), X(L), Z(W), "OUTLINE")
        cell_grid(sh, c, X, Z)
        hr = c.hdr / 2
        sh.rect(X(L / 2 - hr), Z(-600), X(L / 2 + hr), Z(W - 150), "PIPE")
        sh.circle((X(L / 2), Z(-600)), c.ris / 2, "PIPE")
        pts = [(x * M, z * M) for x, z in c.hy["nozzle_xy"]]
        lat_z = sorted({p[1] for p in pts})
        for lz in lat_z:
            sh.line((X(150), Z(lz)), (X(L / 2 - hr), Z(lz)), "PIPE")
            sh.line((X(L / 2 + hr), Z(lz)), (X(L - 150), Z(lz)), "PIPE")
        for x, z in pts:
            sh.circle((X(x), Z(z)), 70, "PIPE")
        xs_n = sorted({p[0] for p in pts})
        sh.dim_h(X(xs_n[0]), X(xs_n[1]), Z(lat_z[-1]) + P(8), Z(lat_z[-1]))
        sh.dim_h(X(0), X(xs_n[0]), Z(lat_z[-1]) + P(8), Z(c.W), Z(lat_z[-1]))
        if len(lat_z) > 1:
            sh.dim_v(Z(lat_z[0]), Z(lat_z[1]), X(L) + P(10), X(xs_n[-1]))
        sh.dim_v(Z(0), Z(lat_z[0]), X(L) + P(10), X(L), X(xs_n[-1]))
        sh.dim_h(X(0), X(L / 2), Z(-600 - c.ris / 2) - P(8), Z(0))
        sh.dim_h(X(0), X(L), Z(-600 - c.ris / 2) - P(16), Z(0))
        sh.text(X(L / 2 + c.ris / 2) + P(2), Z(-600), f"RISER DN{c.ris} FROM SUPPLY MAIN", 2.2, align="L")
        sh.text(X(L / 2 + hr) + P(1), Z(W - 150) - P(3), f"HEADER DN{c.hdr}", 2.2, align="TL")
        sh.text(X(150), Z(lat_z[0]) - P(2.5), f"LATERAL DN{c.lat} (TYP.)", 2.0, align="TL")
        sh.text(X(xs_n[0]) + P(2), Z(lat_z[0]) + P(1.5), f"NOZZLE {c.hy['orifice_mm']} mm ORIFICE (TYP.)", 2.0, align="BL")
    return View("WATER DISTRIBUTION PLAN - TYPICAL CELL", c.L, c.W + 600 + c.ris / 2, draw, (30, 40, 30, 36))


def dist_tables(c: Ctx) -> list[View]:
    hy = c.hy
    noz = [("ITEM", "VALUE"), ("Nozzles per cell / total", f"{hy['nozzles_per_cell']} / {c.n * hy['nozzles_per_cell']}"),
           ("Type", "low-pressure spray, square pattern"), ("Orifice", f"{hy['orifice_mm']} mm"),
           ("Flow per nozzle", f"{hy['q_nozzle_m3_h']:.2f} m3/h"), ("Pressure at nozzle", f"{hy['dp_nozzle_kPa']:.1f} kPa"),
           ("Nozzle to fill top", f"{c.s['tower']['nozzle_clearance_m'] * M:.0f} mm")]
    pipes = [("PIPE", "DN", "VELOCITY m/s", "LOSS kPa"),
             ("Riser (per cell)", f"{hy['riser_DN']}", f"{hy['v_riser']:.2f}", f"{hy['dp_riser_kPa']:.2f}"),
             ("Header", f"{hy['header_DN']}", f"{hy['v_header']:.2f}", f"{hy['dp_header_kPa']:.2f}"),
             ("Laterals", f"{hy['lateral_DN']}", f"{hy['v_lateral']:.2f}", f"{hy['dp_lateral_kPa']:.2f}")]
    head = [("PUMP HEAD AT TOWER", "VALUE"), ("Static lift to nozzle", f"{c.z['nozzle'] / M:.2f} m"),
            ("Total head (static + dynamic)", f"{hy['pump_head_m']:.2f} m"), ("Pressure at header inlet", f"{hy['inlet_pressure_kPa']:.0f} kPa(g)"),
            ("Flow per cell", f"{hy['Q_cell_m3_h']:.0f} m3/h"), ("Tower pumping power", f"{hy['pump_kW']:.1f} kW")]
    return [table_view("NOZZLE SCHEDULE", noz, [52, 62]), table_view("PIPE SCHEDULE", pipes, [40, 18, 30, 26]),
            table_view("HYDRAULICS", head, [56, 40])]


# ============================================================================ CV-005
def basin_plan(c: Ctx) -> View:
    bs = c.bs
    Db = bs["bell_D_m"] * M
    nb = bs["pumps_duty"] + bs["pumps_standby"]
    bay_w, bay_l = 2 * Db, 5 * Db
    sump_w = nb * bay_w + (nb - 1) * 300

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Z = lambda z: oy + z
        P = sh.P
        w, L, W = c.wall, c.nL, c.W
        sh.rect(X(0), Z(0), X(L), Z(W), "CONCRETE")
        sh.rect(X(-w), Z(-w), X(L + w), Z(W + w), "CONCRETE")
        for strip in ([(-w, -w), (L + w, -w), (L + w, 0), (-w, 0)], [(-w, W), (L + w, W), (L + w, W + w), (-w, W + w)],
                      [(-w, 0), (0, 0), (0, W), (-w, W)], [(L, 0), (L + w, 0), (L + w, W), (L, W)]):
            sh.hatch([(X(a), Z(b2)) for a, b2 in strip], "ANSI31", 2.5, "HATCH")
        h = c.colb / 2
        for x in c.all_xs:
            for z in c.zs:
                sh.rect(X(x - h), Z(z - h), X(x + h), Z(z + h), "STRUCT")
        # pump sump bays at the far end
        z0 = W / 2 - sump_w / 2
        x0 = L + w
        sh.rect(X(x0), Z(z0 - w), X(x0 + bay_l + w), Z(z0 + sump_w + w), "CONCRETE")
        for i in range(nb):
            a = z0 + i * (bay_w + 300)
            sh.rect(X(x0), Z(a), X(x0 + bay_l), Z(a + bay_w), "CONCRETE")
            sh.circle((X(x0 + bay_l - Db), Z(a + bay_w / 2)), Db / 2, "EQUIP")
            sh.line((X(x0 + 300), Z(a)), (X(x0 + 300), Z(a + bay_w)), "HIDDEN")
            sh.text(X(x0 + bay_l / 2), Z(a + bay_w / 2), f"P{i + 1}", 2.5, align="C")
        sh.text(X(x0 + bay_l / 2), Z(z0 + sump_w + w) + P(2), "PUMP SUCTION BAYS (HI 9.8)", 2.2, align="BC")
        sh.text(X(x0 + 300), Z(z0) - P(2), "SCREEN", 2.0, align="TC")
        con = bs["connections"]
        for label, x, z, dn in (("MAKEUP", -w, W - 800, con["makeup_DN"]), ("OVERFLOW", -w, 800, con["overflow_DN"]),
                                ("BLOWDOWN", x0 + bay_l + w, z0 - w - 400, con["blowdown_DN"]),
                                ("DRAIN", L / 2, W / 2, con["drain_DN"])):
            sh.circle((X(x), Z(z)), max(dn / 2, 80), "PIPE")
            sh.text(X(x) + P(2), Z(z) + P(1.5), f"{label} DN{dn}", 2.2, align="BL")
        sh.dim_h(X(0), X(L), Z(-w) - P(14), Z(-w), Z(0))
        sh.dim_v(Z(0), Z(W), X(-w) - P(14), X(0))
        sh.dim_h(X(x0), X(x0 + bay_l), Z(z0 - w) - P(8), Z(z0 - w))
        sh.dim_v(Z(z0), Z(z0 + bay_w), X(x0 + bay_l + w) + P(8), X(x0 + bay_l))
    return View("BASIN PLAN", c.nL + 2 * c.wall + 5 * Db + c.wall, c.W + 2 * c.wall, draw, (34, 30, 18, 30))


def sump_section(c: Ctx) -> View:
    bs = c.bs
    Db = bs["bell_D_m"] * M
    S_sub = bs["submergence_m"] * M
    pit = bs["sump_floor_below_water_m"] * M
    bay_l = 5 * Db
    x0 = -1500.0
    y0 = -pit - c.slab
    w_tot = 1500 + c.wall + bay_l + c.wall

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + (x - x0)
        Y = lambda y: oy + (y - y0)
        P = sh.P
        fl = c.floor
        pf = -pit
        outline = [(X(x0), Y(c.curb)), (X(x0), Y(fl)), (X(0), Y(fl)), (X(0), Y(min(fl, pf))), (X(bay_l), Y(min(fl, pf))),
                   (X(bay_l), Y(c.curb))]
        sh.pline(outline, "CONCRETE")
        sh.line((X(x0), Y(0)), (X(bay_l), Y(0)), "WATER")
        bx = bay_l - Db
        sh.rect(X(bx - Db / 2), Y(-S_sub), X(bx + Db / 2), Y(-S_sub + 150), "EQUIP")
        sh.line((X(bx), Y(-S_sub + 150)), (X(bx), Y(c.curb + 1500)), "EQUIP")
        sh.dim_v(Y(-S_sub), Y(0), X(bx + Db / 2) + P(8), X(bx + Db / 2), X(bay_l))
        sh.dim_v(Y(min(fl, pf)), Y(-S_sub), X(bx + Db / 2) + P(8), X(bx + Db / 2))
        sh.dim_v(Y(fl), Y(0), X(x0) - P(8), X(x0))
        sh.text(X(bx), Y(c.curb + 1500) + P(1.5), "PUMP SUCTION", 2.0, align="BC")
        sh.text(X(x0 / 2), Y(fl) + P(2), "BASIN FLOOR", 2.0, align="BC")
        sh.levels(X(x0) - P(20), [("WATER LEVEL", Y(0), 0.0), ("BASIN FLOOR", Y(fl), fl / M),
                                  ("SUMP FLOOR", Y(min(fl, pf)), min(fl, pf) / M)], side="L")
        sh.text(X(bx + Db / 2) + P(10), Y(-S_sub / 2), "SUBMERGENCE S = D(1+2.3Fr)", 2.0, align="L")
    return View("SECTION THROUGH PUMP SUMP", w_tot, c.curb + 1500 + pit + c.slab, draw, (55, 55, 14, 26))


def basin_tables(c: Ctx) -> list[View]:
    bs, wb = c.bs, c.d["water_balance"]
    data = [("ITEM", "VALUE"), ("Inside plan", f"{bs['plan_L']:.2f} x {bs['plan_W']:.2f} m"),
            ("Depth, curb to floor", f"{bs['depth_m']:.2f} m"),
            ("Operating water depth / volume", f"{bs['water_depth_m']:.2f} m / {bs['volume_operating_m3']:,.0f} m3"),
            ("Drain-down volume", f"{bs['drain_down_m3']:.1f} m3"), ("Pumps", f"{bs['pumps_duty']} duty + {bs['pumps_standby']} standby, {bs['pump_flow_m3_h']:.0f} m3/h each"),
            ("Bell dia / submergence", f"{bs['bell_D_m']:.2f} m / {bs['submergence_m']:.2f} m"),
            ("Makeup / blowdown", f"{wb['makeup_m3_h']:.1f} / {wb['blowdown_m3_h']:.1f} m3/h")]
    out = [table_view("BASIN DATA", data, [58, 66])]
    if c.st:
        r = c.st["base_reactions"]
        out.append(table_view("COLUMN BASE REACTIONS (FACTORED, PER COLUMN)",
                              [("REACTION", "kN"), ("Max compression", f"{r['max_down_kN']:.1f}"),
                               ("Max uplift", f"{r['max_uplift_kN']:.1f}"), ("Max horizontal shear", f"{r['max_shear_kN']:.1f}")],
                              [50, 24]))
    return out


# ============================================================================ ST-006 / ST-007 framing
def tier_plan(c: Ctx, tname: str, ty: float) -> View:
    grp = TIER_GROUP[tname]
    mark = MARK[grp]
    sec = c.st["groups"][grp]["section"]

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Z = lambda z: oy + z
        P = sh.P
        cell_grid(sh, c, X, Z)
        for z in c.zs:
            for a, b2 in zip(c.xs[:-1], c.xs[1:]):
                sh.line((X(a), Z(z)), (X(b2), Z(z)), "STRUCT")
                sh.text(X((a + b2) / 2), Z(z) + P(1.2), mark, 1.8, align="BC")
        for x in c.xs:
            for a, b2 in zip(c.zs[:-1], c.zs[1:]):
                sh.line((X(x), Z(a)), (X(x), Z(b2)), "STRUCT")
                sh.text(X(x) - P(1.2), Z((a + b2) / 2), mark, 1.8, align="R")
        sh.text(X(0), Z(-P(6)), f"{mark} = {sec}; C1 = {c.st['groups']['column']['section']}", 2.2, align="TL")
    return View(f"{TIER_NAME[tname]} FRAMING  EL {ty / M:+.3f}", c.L, c.W, draw, (24, 12, 22, 24))


def member_schedule(c: Ctx) -> View | None:
    B = c.d.get("bom")
    if B is None:
        return None
    item_mark = {"Column": "C1", "Tie beam": "TB1", "Fill beam": "FB1", "Dist beam": "DB1", "Elim beam": "EB1",
                 "Deck beam": "KB1", "Diagonal brace": "BR1"}
    rows = [("MARK", "MEMBER", "SECTION", "QTY", "CUT LENGTH", "kg/pc", "TOTAL kg")]
    seen = {}
    for r in B[B.category == "FRP structure"].itertuples():
        mk = item_mark.get(r.item, "")
        seen[mk] = seen.get(mk, 0) + 1
        mk2 = mk if r.item != "Diagonal brace" else f"{mk}-{seen[mk]}"
        cut = r.note.split("cut length ")[1].split(" ")[0] if "cut length" in r.note else ""
        rows.append((mk2, r.item, r.specification.replace(" pultruded", "").split(",")[0], f"{r.qty:g}", f"{cut} m",
                     f"{r.unit_kg:.1f}", f"{r.total_kg:,.0f}"))
    tot = B.loc[B.category == "FRP structure", "total_kg"].sum()
    rows.append(("", "TOTAL FRP FRAMING (WHOLE TOWER)", "", "", "", "", f"{tot:,.0f}"))
    return table_view("MEMBER SCHEDULE", rows, [16, 48, 34, 14, 24, 16, 22], 2.2)


def _plane_members(c: Ctx, prefix: str, fixed_idx: int, coord: int, limit: float):
    """Braces of the analysed model lying in one grid plane of the first cell."""
    fr = c.st["_fr"]
    out = []
    for mb in c.st["members"]:
        if mb["kind"] != "brace" or not mb["name"].startswith(prefix):
            continue
        parts = mb["name"][2:].split("_")
        idx = int(parts[1]) if prefix == "DX" else int(parts[0])
        if idx != fixed_idx:
            continue
        pi, pj = fr["nodes"][mb["i"]], fr["nodes"][mb["j"]]
        if max(pi[coord], pj[coord]) * M <= limit + 1:
            out.append((pi, pj))
    return out


def frame_elevation(c: Ctx, along: str) -> View:
    """Elevation of grid line A (along x) or grid line 1 (along z) of the first cell."""
    u = c.xs if along == "x" else c.zs
    span = c.L if along == "x" else c.W
    y0 = c.tiers[0][1] if c.tiers else c.floor
    yt = c.z["fan_deck"]
    coord = 0 if along == "x" else 2
    braces = _plane_members(c, "DX" if along == "x" else "DZ", 0, coord, span)

    def draw(sh: Sheet, ox, oy):
        X = lambda x: ox + x
        Y = lambda y: oy + (y - y0)
        P = sh.P
        for i, a in enumerate(u):
            sh.line((X(a), Y(y0)), (X(a), Y(yt)), "STRUCT")
            sh.bubble(X(a), Y(yt) + P(10), str(i + 1) if along == "x" else zlabel(i))
            sh.line((X(a), Y(yt)), (X(a), Y(yt) + P(6)), "CENTER")
        sh.text(X(u[0]) + P(1), Y((y0 + c.tiers[1][1]) / 2), "C1", 1.8, align="L")
        for tn, ty in c.tiers[1:]:
            mk = MARK[TIER_GROUP[tn]]
            for a, b2 in zip(u[:-1], u[1:]):
                sh.line((X(a), Y(ty)), (X(b2), Y(ty)), "STRUCT")
                sh.text(X((a + b2) / 2), Y(ty) + P(1), mk, 1.8, align="BC")
        for pi, pj in braces:
            a, b2 = (pi[coord] * M, pj[coord] * M)
            sh.line((X(a), Y(pi[1] * M)), (X(b2), Y(pj[1] * M)), "BRACE")
        for k, (pi, pj) in enumerate(braces[:1]):
            sh.text(X((pi[coord] + pj[coord]) * M / 2) + P(1), Y((pi[1] + pj[1]) * M / 2), "BR1", 1.8, align="L")
        sh.pline([(X(-P(4)), Y(y0)), (X(span + P(4)), Y(y0))], "THIN")
        for i in range(int(span // 400) + 1):
            sh.line((X(i * 400), Y(y0)), (X(i * 400 - 250), Y(y0) - P(2)), "THIN")
        sh.levels(X(span) + P(10), [(TIER_NAME.get(n, "BASE (PINNED)"), Y(y), y / M) for n, y in c.tiers])
        for a, b2 in zip(u[:-1], u[1:]):
            sh.dim_h(X(a), X(b2), Y(y0) - P(10), Y(y0))
    name = "GRID LINE A" if along == "x" else "GRID LINE 1"
    return View(f"FRAMING ELEVATION - {name} (CELL 1)", span, yt - y0, draw, (16, 62, 22, 26))


def connection_schedule(c: Ctx) -> View:
    rows = [("MARK", "CONNECTION", "BOLTS", "DEMAND/lambda kN", "UR", "GOVERNS")]
    for g, cn in c.st["connections"].items():
        rows.append((MARK[g], cn["type"], f"{cn['bolts']} x M{cn['d_mm']}", f"{cn.get('force_over_lambda_kN', cn['force_kN']):.1f}",
                     f"{cn['UR']:.2f}", cn["governs"]))
    return table_view("CONNECTION SCHEDULE", rows, [14, 88, 20, 34, 12, 22], 2.2)


def datasheet_sheet(sh: Sheet, c: Ctx):
    rows = datasheet_rows(c.d, c.b)
    S = sh.P
    left = [("SECTION", "ITEM", "VALUE")] + [(a if (i == 0 or rows[i - 1][0] != a) else "", b2, v)
                                              for i, (a, b2, v) in enumerate(rows)]
    half = (len(left) + 1) // 2
    cut = next((i for i in range(half, len(left)) if left[i][0]), half)
    sh.text(S(25), S(578), f"COOLING TOWER DATASHEET - {c.s['project']['tag']}", 5.0, align="TL")
    sh.table(S(25), S(565), left[:cut], [44, 92, 122], 2.9)
    sh.table(S(420), S(565), [left[0]] + left[cut:], [44, 92, 122], 2.9)


# ============================================================================ assembly
def sheet_specs(c: Ctx) -> list[tuple]:
    """(number, title, view rows, extra notes, extra drawer) for every sheet."""
    out = [("GA-001", "GENERAL ARRANGEMENT", [[plan_view(c)], [side_elevation(c), end_elevation(c)]], [], None),
            ("GA-002", "SECTIONS A-A AND B-B", [[section_cross(c), section_long(c)]], [], None),
            ("ME-003", "FAN DECK AND MECHANICAL", [[deck_plan(c), stack_detail(c), fan_table(c)]],
             ["Fan, gear reducer, drive shaft and motor per vendor; CTI STD-111 gear service factor."], None),
            ("WD-004", "WATER DISTRIBUTION", [[dist_plan(c)] + dist_tables(c)[:1], dist_tables(c)[1:]],
             ["All cells identical. Nozzle layout clears columns by field adjustment of +-100 mm."], None),
            ("CV-005", "BASIN AND PUMP SUMP", [[basin_plan(c)], [sump_section(c)] + basin_tables(c)],
             ["Concrete design, reinforcement, waterproofing and anchors by the civil engineer.",
              "Pump sump geometry per ANSI/HI 9.8; confirm with the pump vendor."], None)]
    if c.st:
        plans = [tier_plan(c, n, y) for n, y in c.tiers[1:]]
        sched = member_schedule(c)
        rows = [plans[:3], plans[3:] + ([sched] if sched else [])]
        out += [("ST-006", "FRP FRAMING PLANS", rows,
                 ["All cells identical; plans show cell 1. Beams continuous, spliced at columns (ASCE 74).",
                  f"Pultruded {c.st['material']['name']} shapes; members sized per ASCE/SEI 74 (see report)."], None),
                ("ST-007", "FRP FRAMING ELEVATIONS", [[frame_elevation(c, "x"), frame_elevation(c, "z")], [connection_schedule(c)]],
                 ["Braces alternate between bays and lines; every column line is braced (ASCE 74 OBCT).",
                  f"Bolts {c.s['structure']['fastener_material']}; end distance 2d, pitch 4d; brace ends on 12 mm FRP gussets.",
                  "Column bases pinned on SS anchor brackets; see CV-005 for reactions."], None)]
    out.append(("DS-008", "DATASHEET", [], [], datasheet_sheet))
    return out


def make_all(d: dict, b, out: Path, only=None) -> list[dict]:
    c = Ctx(d, b)
    specs = sheet_specs(c)
    total = len(specs)
    files = []
    for i, (no, title, rows, notes, extra) in enumerate(specs, 1):
        if only and no not in only:
            continue
        S = Sheet.pick_scale(rows) if rows else 1.0
        sh = Sheet(no, title, c.meta(str(i), str(total)), S, GENERAL_NOTES + notes)
        sh.frame()
        if rows:
            sh.place(rows)
        if extra:
            extra(sh, c)
        base = Path(out) / f"{c.s['project']['tag']}-{no}_{title.lower().replace(' ', '_').replace('/', '-')}"
        paths = sh.save(base)
        files.append({"number": no, "title": title, "scale": f"1:{S:g}", **{k: str(v) for k, v in paths.items()}})
    if not only:
        merged = fitz.open()
        for f in files:
            with fitz.open(f[".pdf"]) as src:
                merged.insert_pdf(src)
        merged.save(Path(out) / f"{c.s['project']['tag']}_drawing_set.pdf")
    return files
