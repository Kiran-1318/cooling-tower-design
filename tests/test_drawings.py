"""Phase 4: drawing framework and the full DXF/SVG/PDF drawing set."""
import sys
from pathlib import Path

import ezdxf
import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import spec, sizing, structure, bom, drawings_dxf  # noqa: E402
from ctdesign.dxfsheet import Sheet, View, SCALES  # noqa: E402


def test_pick_scale_is_smallest_standard_that_fits():
    v = View("x", 30000.0, 10000.0, lambda *a: None, (20, 20, 10, 20))
    S = Sheet.pick_scale([[v]])
    assert S in SCALES
    assert 30000 / S <= 811 - 40 + 1e-6                      # fits the view area
    smaller = [s for s in SCALES if s < S]
    assert not smaller or 30000 / smaller[-1] > 811 - 40 or 10000 / smaller[-1] > 506 - 30


def test_level_labels_do_not_overlap():
    sh = Sheet("T-1", "TEST", {}, 50.0)
    sh.levels(0, [("A", 0.0, 0.0), ("B", 100.0, 0.1), ("C", 150.0, 0.15)])
    ys = sorted(t.dxf.insert.y for t in sh.msp.query("TEXT"))
    assert all(b - a >= sh.P(5.0) - 1e-6 for a, b in zip(ys, ys[1:]))


@pytest.fixture(scope="module")
def drawing_set(tmp_path_factory):
    b = spec.load(ROOT / "examples" / "hvac_2cell.json")
    d = sizing.finalize(b, {"cells": 2, "L": 7.3, "W": 7.3, "depth": 1.2, "fan_D": 4.3})
    d["structure"] = structure.design(d, b, b.spec, log=lambda *a: None)
    d["bom"] = bom.build(d, b, b.spec, d["structure"])
    out = tmp_path_factory.mktemp("dwg")
    return b, d, out, drawings_dxf.make_all(d, b, out)


def test_all_sheets_and_formats(drawing_set):
    _, _, out, files = drawing_set
    assert [f["number"] for f in files] == ["GA-001", "GA-002", "ME-003", "WD-004", "CV-005", "ST-006", "ST-007", "DS-008"]
    for f in files:
        for ext in (".dxf", ".svg", ".pdf", ".png"):
            assert Path(f[ext]).stat().st_size > 1000
        assert Path(f[".svg"]).read_text(encoding="utf-8").lstrip().startswith("<?xml")
    with fitz.open(next(out.glob("*_drawing_set.pdf"))) as pdf:
        assert pdf.page_count == 8
        w, h = pdf[0].rect.width / 72 * 25.4, pdf[0].rect.height / 72 * 25.4
        assert (round(w), round(h)) == (841, 594)                   # A1 landscape


def test_dxf_valid_and_metric(drawing_set):
    _, _, _, files = drawing_set
    for f in files:
        doc = ezdxf.readfile(f[".dxf"])
        assert len(doc.audit().errors) == 0
        assert doc.header["$INSUNITS"] == 4
        assert {"OUTLINE", "STRUCT", "PIPE", "DIM", "CENTER"} <= {l.dxf.name for l in doc.layers}


def test_ga_dimensions_equal_model(drawing_set):
    _, d, _, files = drawing_set
    g = d["geom"]
    doc = ezdxf.readfile(files[0][".dxf"])
    dims = {round(e.get_measurement()) for e in doc.modelspace().query("DIMENSION")}
    assert round(g.cells * g.L * 1000) in dims and round(g.W * 1000) in dims
    assert round(g.z["stack_top"] * 1000) in dims                  # water level to stack top
    assert round(g.H_inlet * 1000) in dims


def test_framing_marks_cover_every_beam(drawing_set):
    _, d, _, files = drawing_set
    st = d["structure"]
    n_x = len([x for x in st["grid"]["xs"] if x <= d["geom"].L + 1e-6])
    n_z = len(st["grid"]["zs"])
    per_tier = n_z * (n_x - 1) + n_x * (n_z - 1)
    doc = ezdxf.readfile(next(f for f in files if f["number"] == "ST-006")[".dxf"])
    texts = [t.dxf.text for t in doc.modelspace().query("TEXT")]
    B = d["bom"]
    for mark, item in (("TB1", "Tie beam"), ("FB1", "Fill beam"), ("DB1", "Dist beam"), ("EB1", "Elim beam"), ("KB1", "Deck beam")):
        schedule_rows = int((B.item == item).sum())                 # the member schedule lists each cut length
        assert texts.count(mark) == per_tier + schedule_rows
