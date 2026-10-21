"""Drawing-sheet framework on ezdxf: A1 sheet, title block, layers, dimensions, tables, view layout,
and export to DXF, SVG, PDF and PNG.

Geometry is drawn 1:1 in millimetres in modelspace; the A1 frame, title block, text and dimension
styles are scaled by the sheet scale S (1:S), so the DXF opens at true size in any CAD program and
prints to A1 at 1:S. Paper sizes passed to the helpers are in paper millimetres.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import ezdxf
from ezdxf.enums import TextEntityAlignment

PAPER_W, PAPER_H = 841.0, 594.0
SCALES = [1, 2, 5, 10, 20, 25, 30, 40, 50, 60, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000]
FONT = "LiberationSans"
# area left for views (paper mm): above the notes / title strip, inside the border
AREA = (20.0, 78.0, 831.0, 584.0)

LAYERS = {  # name: (ACI colour, linetype, lineweight in 1/100 mm)
    "FRAME": (7, "Continuous", 70), "TITLE": (7, "Continuous", 25), "OUTLINE": (7, "Continuous", 50),
    "THIN": (7, "Continuous", 18), "HIDDEN": (8, "DASHED", 18), "CENTER": (1, "CENTER", 13),
    "DIM": (3, "Continuous", 13), "TEXT": (7, "Continuous", 18), "STRUCT": (5, "Continuous", 35),
    "BRACE": (150, "Continuous", 25), "WATER": (4, "Continuous", 25), "PIPE": (6, "Continuous", 35),
    "EQUIP": (30, "Continuous", 35), "HATCH": (8, "Continuous", 9), "FILLPACK": (42, "Continuous", 18),
    "AIR": (1, "Continuous", 25), "CONCRETE": (8, "Continuous", 35),
}

ALIGN = {"L": TextEntityAlignment.MIDDLE_LEFT, "C": TextEntityAlignment.MIDDLE_CENTER,
         "R": TextEntityAlignment.MIDDLE_RIGHT, "BL": TextEntityAlignment.BOTTOM_LEFT,
         "BC": TextEntityAlignment.BOTTOM_CENTER, "TL": TextEntityAlignment.TOP_LEFT,
         "TC": TextEntityAlignment.TOP_CENTER, "BR": TextEntityAlignment.BOTTOM_RIGHT}


@dataclass
class View:
    """A drawing view: model-space size (mm) and annotation margins (paper mm: left, right, top, bottom)."""
    title: str
    w: float
    h: float
    draw: Callable                      # draw(sheet, ox, oy) with (ox, oy) = model origin of the view's lower-left
    margins: tuple = (25.0, 25.0, 14.0, 22.0)


@dataclass
class Sheet:
    number: str
    title: str
    meta: dict
    scale: float = 1.0
    notes: list = field(default_factory=list)

    def __post_init__(self):
        self.doc = ezdxf.new("R2018", setup=True)
        self.doc.header["$INSUNITS"] = 4
        self.doc.header["$MEASUREMENT"] = 1
        self.doc.header["$LTSCALE"] = self.scale * 0.5
        for name, (col, lt, lw) in LAYERS.items():
            self.doc.layers.add(name, color=col, linetype=lt, lineweight=lw)
        ds = self.doc.dimstyles.new("CT")
        for k, v in {"dimtxt": 2.5, "dimasz": 2.0, "dimexo": 1.0, "dimexe": 1.5, "dimgap": 0.8, "dimscale": self.scale,
                     "dimtad": 1, "dimdec": 0, "dimtxsty": FONT, "dimclrd": 3, "dimclre": 3, "dimclrt": 7,
                     "dimlunit": 2, "dimtih": 0, "dimtoh": 0}.items():
            ds.set_dxf_attrib(k, v)
        self.msp = self.doc.modelspace()

    # ------------------------------------------------------------------ primitives (model mm)
    def P(self, paper_mm: float) -> float:
        return paper_mm * self.scale

    def line(self, p1, p2, layer="OUTLINE"):
        self.msp.add_line(p1, p2, dxfattribs={"layer": layer})

    def pline(self, pts, layer="OUTLINE", close=False):
        self.msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})

    def rect(self, x0, y0, x1, y1, layer="OUTLINE"):
        self.pline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, close=True)

    def circle(self, c, r, layer="OUTLINE"):
        self.msp.add_circle(c, r, dxfattribs={"layer": layer})

    def text(self, x, y, s, h=2.5, layer="TEXT", align="L", rot=0.0):
        t = self.msp.add_text(str(s), height=self.P(h), rotation=rot, dxfattribs={"layer": layer, "style": FONT})
        t.set_placement((x, y), align=ALIGN[align])
        return t

    def hatch(self, pts, pattern="ANSI31", spacing_paper=2.0, layer="HATCH", solid=False):
        h = self.msp.add_hatch(dxfattribs={"layer": layer})
        if solid:
            h.set_solid_fill(color=LAYERS[layer][0])
        else:
            h.set_pattern_fill(pattern, scale=self.P(spacing_paper) / 3.175)
        h.paths.add_polyline_path(pts, is_closed=True)

    def hatch_rect(self, x0, y0, x1, y1, **kw):
        self.hatch([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], **kw)

    def arrow(self, p1, p2, layer="AIR", head_paper=3.0):
        self.line(p1, p2, layer)
        a = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        h = self.P(head_paper)
        for da in (2.7, -2.7):
            self.line(p2, (p2[0] + h * math.cos(a + da), p2[1] + h * math.sin(a + da)), layer)

    def dim_h(self, x1, x2, y_line, y_ref1=None, y_ref2=None, text=None):
        y1 = y_line if y_ref1 is None else y_ref1
        y2 = y1 if y_ref2 is None else y_ref2
        d = self.msp.add_linear_dim(base=(x1, y_line), p1=(x1, y1), p2=(x2, y2), angle=0, dimstyle="CT",
                                    text=text or "<>", dxfattribs={"layer": "DIM"})
        d.render()

    def dim_v(self, y1, y2, x_line, x_ref1=None, x_ref2=None, text=None):
        x1 = x_line if x_ref1 is None else x_ref1
        x2 = x1 if x_ref2 is None else x_ref2
        d = self.msp.add_linear_dim(base=(x_line, y1), p1=(x1, y1), p2=(x2, y2), angle=90, dimstyle="CT",
                                    text=text or "<>", dxfattribs={"layer": "DIM"})
        d.render()

    def level(self, x, y, label, el_m, side="R"):
        """Level marker: triangle at (x, y) and 'LABEL EL +x.xxx' (elevation in m)."""
        s = self.P(2.5)
        self.pline([(x, y), (x - s / 2, y + s), (x + s / 2, y + s)], "DIM", close=True)
        self.line((x - s * 1.5, y), (x + s * 1.5, y), "DIM")
        txt = f"{label}  EL {el_m:+.3f}"
        if side == "R":
            self.text(x + s, y + s * 0.4, txt, 2.2, align="BL")
        else:
            self.text(x - s, y + s * 0.4, txt, 2.2, align="BR")

    def levels(self, x, items, side="R", gap_paper=5.0):
        """Several level markers on one vertical: items (label, y_model, el_m). Texts are pushed apart
        to at least gap_paper and tied back to their marker with a short leader."""
        items = sorted(items, key=lambda it: it[1])
        s, gap = self.P(2.5), self.P(gap_paper)
        ty = []
        for _, y, _ in items:
            ty.append(max(y, ty[-1] + gap) if ty else y)
        sign = 1 if side == "R" else -1
        for (label, y, el), t in zip(items, ty):
            self.pline([(x, y), (x - s / 2, y + s), (x + s / 2, y + s)], "DIM", close=True)
            self.line((x - s * 1.5, y), (x + s * 1.5, y), "DIM")
            xt = x + sign * s * 2.5
            if abs(t - y) > 1e-6:
                self.line((x + sign * s * 1.5, y), (xt, t), "DIM")
            self.text(xt + sign * s * 0.3, t + s * 0.2, f"{label}  EL {el:+.3f}", 2.2, align="BL" if side == "R" else "BR")

    def bubble(self, x, y, label):
        r = self.P(4.0)
        self.circle((x, y), r, "CENTER")
        self.text(x, y, label, 3.0, align="C")

    def view_title(self, x, y, title, scale=True):
        self.text(x, y, title, 4.0, align="BL")
        t = len(title) * self.P(4.0) * 0.62
        self.line((x, y - self.P(1.2)), (x + t, y - self.P(1.2)), "TITLE")
        if scale:
            self.text(x, y - self.P(5.5), f"SCALE 1:{self.scale:g}", 2.5, align="BL")

    def table(self, x, y_top, rows, widths_paper, h=2.5, header=True):
        """Grid table at paper-size widths; returns the model y of its bottom edge."""
        rh = self.P(h * 2.2)
        W = [self.P(w) for w in widths_paper]
        y = y_top
        for i, row in enumerate(rows):
            xx = x
            for j, cell in enumerate(row):
                self.rect(xx, y - rh, xx + W[j], y, "TITLE" if i or not header else "OUTLINE")
                self.text(xx + self.P(1.2), y - rh / 2, cell, h * (1.05 if (i == 0 and header) else 1.0), align="L")
                xx += W[j]
            y -= rh
        return y

    # ------------------------------------------------------------------ sheet furniture
    def frame(self):
        S = self.P
        self.rect(0, 0, S(PAPER_W), S(PAPER_H), "THIN")
        self.rect(S(15), S(8), S(PAPER_W - 8), S(PAPER_H - 8), "FRAME")
        # title block (bottom right) 200 x 66
        x0, y0, x1, y1 = S(PAPER_W - 8 - 200), S(8), S(PAPER_W - 8), S(74)
        self.rect(x0, y0, x1, y1, "FRAME")
        m = self.meta
        rows = [("PROJECT", m.get("project", "")), ("CLIENT / SITE", f"{m.get('client', '')} / {m.get('site', '')}"),
                ("EQUIPMENT", f"{m.get('tag', '')}  {m.get('equipment', '')}"), ("TITLE", self.title)]
        yy = y1
        for k, v in rows:
            self.line((x0, yy), (x1, yy), "TITLE")
            self.text(x0 + S(2), yy - S(3), k, 1.8, align="TL")
            self.text(x0 + S(30), yy - S(3.5), v, 3.2 if k == "TITLE" else 2.6, align="TL")
            yy -= S(10)
        self.line((x0, yy), (x1, yy), "TITLE")
        cols = [("DRAWING NO.", f"{m.get('tag', '')}-{self.number}"), ("REV", m.get("rev", "A")),
                ("SCALE", f"1:{self.scale:g}" if self.scale != 1 else "NTS"), ("DATE", m.get("date") or date.today().isoformat()),
                ("SHEET", m.get("sheet", ""))]
        widths = [64, 18, 30, 44, 44]
        xx = x0
        for (k, v), w in zip(cols, widths):
            self.line((xx, yy), (xx, y0 + S(10)), "TITLE")
            self.text(xx + S(2), yy - S(2.5), k, 1.8, align="TL")
            self.text(xx + S(2), yy - S(9), v, 3.0, align="TL")
            xx += S(w)
        self.line((x0, y0 + S(10)), (x1, y0 + S(10)), "TITLE")
        self.text(x0 + S(2), y0 + S(5), m.get("status", "PRELIMINARY - DESIGN AID - NOT FOR CONSTRUCTION"), 2.6, align="L")
        self.text(x1 - S(2), y0 + S(5), "cooling-tower-design skill", 1.8, align="R")
        # notes box (bottom left)
        nx0, nx1 = S(15), x0 - S(4)
        self.rect(nx0, S(8), nx1, S(74), "TITLE")
        self.text(nx0 + S(3), S(70), "NOTES", 3.0, align="TL")
        y = S(64)
        for i, n in enumerate(self.notes, 1):
            self.text(nx0 + S(3), y, f"{i}. {n}", 2.0, align="TL")
            y -= S(4.2)

    # ------------------------------------------------------------------ layout
    @staticmethod
    def pick_scale(rows: list[list[View]], min_scale: float = 1.0) -> float:
        aw, ah = AREA[2] - AREA[0], AREA[3] - AREA[1]
        need = min_scale
        for row in rows:                       # widths per row
            wm = sum(v.w for v in row)
            wp = sum(v.margins[0] + v.margins[1] for v in row) + 8 * (len(row) - 1)
            if aw - wp <= 0:
                raise ValueError("view margins exceed the sheet")
            need = max(need, wm / (aw - wp))
        hm = sum(max(v.h for v in row) for row in rows)
        hp = sum(max(v.margins[2] + v.margins[3] for v in row) for row in rows) + 6 * (len(rows) - 1)
        need = max(need, hm / (ah - hp))
        return next((s for s in SCALES if s >= need - 1e-9), SCALES[-1])

    def place(self, rows: list[list[View]]):
        """Draw the views row by row from the top of the view area, centred in each row."""
        S = self.P
        aw = AREA[2] - AREA[0]
        y_top = S(AREA[3])
        for row in rows:
            rh = max(v.h + S(v.margins[2] + v.margins[3]) for v in row)
            total = sum(v.w + S(v.margins[0] + v.margins[1]) for v in row) + S(8) * (len(row) - 1)
            x = S(AREA[0]) + max(0.0, (S(aw) - total) / 2)
            for v in row:
                ox = x + S(v.margins[0])
                oy = y_top - S(v.margins[2]) - v.h
                v.draw(self, ox, oy)
                if getattr(v, "paper", False):           # tables: title above the grid
                    self.view_title(ox, oy + S(v.margins[2]) - S(4), v.title, scale=False)
                else:
                    self.view_title(ox, oy - S(v.margins[3]) + S(9), v.title)
                x += v.w + S(v.margins[0] + v.margins[1] + 8)
            y_top -= rh + S(6)

    # ------------------------------------------------------------------ export
    def save(self, base: Path) -> dict:
        from ezdxf.addons.drawing import Frontend, RenderContext, config, layout, pymupdf, svg
        base = Path(base)
        self.doc.saveas(base.with_suffix(".dxf"))
        cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                                   color_policy=config.ColorPolicy.COLOR,
                                   lineweight_policy=config.LineweightPolicy.ABSOLUTE)
        page = layout.Page(PAPER_W, PAPER_H, layout.Units.mm, margins=layout.Margins.all(0))
        ctx = RenderContext(self.doc)
        sb = svg.SVGBackend()
        Frontend(ctx, sb, config=cfg).draw_layout(self.msp, finalize=True)
        base.with_suffix(".svg").write_text(sb.get_string(page), encoding="utf-8")
        pb = pymupdf.PyMuPdfBackend()
        Frontend(ctx, pb, config=cfg).draw_layout(self.msp, finalize=True)
        base.with_suffix(".pdf").write_bytes(pb.get_pdf_bytes(page))
        base.with_suffix(".png").write_bytes(pb.get_pixmap_bytes(page, fmt="png", dpi=110))
        return {ext: base.with_suffix(ext) for ext in (".dxf", ".svg", ".pdf", ".png")}
