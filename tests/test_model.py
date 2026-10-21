"""Phase 5: FreeCAD 3D model built headlessly; STEP re-import and cross-checks against the design."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import spec, sizing, structure, bom, model3d  # noqa: E402

FC = model3d.find_freecadcmd({})
pytestmark = pytest.mark.skipif(FC is None, reason="FreeCAD (freecadcmd) not installed")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    b = spec.load(ROOT / "examples" / "hvac_2cell.json")
    d = sizing.finalize(b, {"cells": 2, "L": 7.3, "W": 7.3, "depth": 1.2, "fan_D": 4.3})
    d["structure"] = structure.design(d, b, b.spec, log=lambda *a: None)
    d["bom"] = bom.build(d, b, b.spec, d["structure"])
    d["bom_summary"] = bom.summary(d["bom"])
    out = tmp_path_factory.mktemp("model")
    m = model3d.model_input(d, b)
    res = out / "design_results.json"
    res.write_text(json.dumps({"model": m}), encoding="utf-8")
    bt = model3d.build(res, out / "model", FC)
    st = model3d.check_step(Path(bt["step"]), FC)
    return d, m, bt, st


def test_model_input_is_self_contained(built):
    d, m, _, _ = built
    assert m["units"] == "mm" and m["cells"] == 2
    assert len(m["members"]) == d["structure"]["n_members"]          # 2 cells: analysed block = whole tower
    assert set(m["sections"]) == {"column", "fill_beam", "dist_beam", "elim_beam", "deck_beam", "tie_beam", "brace"}


def test_files_written(built):
    _, _, bt, _ = built
    assert Path(bt["step"]).stat().st_size > 100_000
    assert Path(bt["fcstd"]).stat().st_size > 10_000


def test_cross_checks(built):
    _, m, bt, st = built
    ck = model3d.checks(m, bt, st)
    assert ck["ok"], ck
    assert ck["frp_kg_model"] == pytest.approx(ck["frp_kg_bom"], rel=0.03)
    assert ck["fill_volume_m3"] == pytest.approx(14.6 * 7.3 * 1.2, rel=1e-6)


def test_step_reimport(built):
    _, _, bt, st = built
    assert st["valid"] and st["solids"] > 1000
    assert st["bbox_mm"] == pytest.approx(bt["bbox_mm"], abs=1.0)
