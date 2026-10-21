"""3D model: write the FreeCAD model input into design_results.json and run the headless builder.

The builder (scripts/freecad/build_model.py) runs under FreeCAD's own Python (freecadcmd), so it
reads a self-contained "model" block - plain numbers in millimetres - rather than importing this
package. Axes in the model block are FreeCAD's: X along the cell row, Y across a cell, Z up, with
Z = 0 at the basin operating water level.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import structure

M = 1000.0
BUILDER = Path(__file__).resolve().parents[1] / "freecad" / "build_model.py"
MARK = {"column": "C1", "tie_beam": "TB1", "fill_beam": "FB1", "dist_beam": "DB1", "elim_beam": "EB1",
        "deck_beam": "KB1", "brace": "BR1"}


def _fc(p):
    """Tower (x along row, y elevation, z across) in m -> FreeCAD (X, Y, Z) in mm."""
    return [round(p[0] * M, 1), round(p[2] * M, 1), round(p[1] * M, 1)]


def model_input(d: dict, b) -> dict:
    g, s, st = d["geom"], b.spec, d["structure"]
    full = structure.framing(d, {**s, "structure": {**s["structure"], "model_cells_max": g.cells}})
    secs = st["_sections"]
    members = [{"mark": MARK[mb["group"]], "group": mb["group"], "kind": mb["kind"],
                "p1": _fc(full["nodes"][mb["i"]]), "p2": _fc(full["nodes"][mb["j"]])} for mb in full["members"]]
    sections = {gname: {"family": sc.family, "d": sc.d * M, "bf": sc.bf * M, "t": sc.t * M, "name": sc.name}
                for gname, sc in secs.items()}
    bs, fn, hy = d["basin"], d["fan"], d["hyd"]
    Db = bs["bell_D_m"] * M
    nb = bs["pumps_duty"] + bs["pumps_standby"]
    return {
        "units": "mm", "axes": "X along row, Y across cell, Z up; Z=0 at basin operating water level",
        "tag": s["project"]["tag"], "project": s["project"]["name"], "cells": g.cells, "L": g.L * M, "W": g.W * M,
        "z": {k: v * M for k, v in g.z.items()}, "two_sides": s["tower"]["air_inlets"] == "two_sides",
        "fill_depth": g.depth * M,
        "fan": {"D": fn["D"] * M, "Dx": fn["stack_exit_D"] * M, "Hs": fn["stack_H"] * M,
                "stack": fn["stack"], "hub": max(0.1 * fn["D"] * M, 250.0), "motor_kW": fn["motor_kW"]},
        "basin": {"floor": -bs["water_depth_m"] * M, "curb": max(g.z["curb"], bs["freeboard_m"]) * M, "wall": 300.0,
                  "slab": 300.0, "sump_bays": nb, "bay_w": 2 * Db, "bay_l": 5 * Db,
                  "sump_floor": -bs["sump_floor_below_water_m"] * M},
        "distribution": {"header_D": hy["header_DN"], "lateral_D": hy["lateral_DN"], "riser_D": hy["riser_DN"],
                         "nozzles": [[x * M, y * M] for x, y in hy["nozzle_xy"]]},
        "sections": sections, "members": members,
        "frp_density": st["_mat"].rho,
        "bom_frp_kg": float(d["bom_summary"]["frp_structure_kg"]) if "bom_summary" in d else None,
    }


def find_freecadcmd(s: dict) -> str | None:
    cands = [os.environ.get("FREECADCMD"), s.get("freecad", {}).get("freecadcmd")]
    cands += sorted(glob.glob(r"C:\Program Files\FreeCAD*\bin\freecadcmd.exe"), reverse=True)
    cands += [shutil.which("freecadcmd"), shutil.which("FreeCADCmd"), "/usr/bin/freecadcmd",
              "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"]
    return next((c for c in cands if c and Path(c).exists()), None)


CHECKER = Path(__file__).resolve().parents[1] / "freecad" / "check_step.py"


def check_step(step: Path, freecadcmd: str, timeout: int = 900) -> dict:
    """Re-import the STEP in a fresh FreeCAD session: solids, volume, bounding box, validity."""
    env = dict(os.environ, CT_STEP=str(Path(step).resolve()))
    p = subprocess.run([freecadcmd, str(CHECKER)], env=env, capture_output=True, text=True, timeout=timeout)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("CTSTEP ")), None)
    if line is None:
        raise RuntimeError(f"STEP check failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return json.loads(line[len("CTSTEP "):])


def checks(model: dict, built: dict, step: dict) -> dict:
    """Cross-checks of the built model against the design data."""
    fill_expected = model["cells"] * model["L"] * model["W"] * model["fill_depth"] * 1e-9
    z_lo = min(model["basin"]["floor"], model["basin"]["sump_floor"]) - model["basin"]["slab"]
    z_hi = model["z"]["stack_top"]
    out = {"fill_volume_m3": built["volumes_m3"].get("Fill", 0.0), "fill_volume_expected_m3": fill_expected,
           "frp_kg_model": built["frp_kg_model"], "frp_kg_bom": model.get("bom_frp_kg"),
           "bbox_z_mm": [built["bbox_mm"][2], built["bbox_mm"][5]], "bbox_z_expected_mm": [z_lo, z_hi],
           "step_solids": step["solids"], "step_valid": step["valid"],
           "step_volume_m3": step["volume_m3"], "model_volume_m3": sum(built["volumes_m3"].values())}
    out["ok"] = bool(abs(out["fill_volume_m3"] / fill_expected - 1) < 1e-3
                     and (out["frp_kg_bom"] is None or abs(out["frp_kg_model"] / out["frp_kg_bom"] - 1) < 0.05)
                     and abs(out["bbox_z_mm"][0] - z_lo) < 1 and abs(out["bbox_z_mm"][1] - z_hi) < 1
                     and step["valid"] and abs(step["volume_m3"] / out["model_volume_m3"] - 1) < 1e-3)
    return out


def build(results_json: Path, out_dir: Path, freecadcmd: str, per_member: bool = False, timeout: int = 1800) -> dict:
    """Run the FreeCAD builder headlessly; return its summary (parsed from the CTMODEL line)."""
    env = dict(os.environ, CT_DESIGN_JSON=str(Path(results_json).resolve()), CT_OUT_DIR=str(Path(out_dir).resolve()),
               CT_PER_MEMBER="1" if per_member else "0")
    p = subprocess.run([freecadcmd, str(BUILDER)], env=env, capture_output=True, text=True, timeout=timeout)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("CTMODEL ")), None)
    if p.returncode != 0 or line is None:
        raise RuntimeError(f"FreeCAD builder failed (exit {p.returncode}):\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return json.loads(line[len("CTMODEL "):])
