"""Design a mechanical induced-draft counterflow cooling tower end-to-end from a JSON spec.

    python run_ct_design.py SPEC.json --out OUTDIR [--stage STAGE] [--quick] [--params JSON]

Stages (run in this order by `all`)
  basis     : load the spec, close the duty, print the design basis   (available)
  thermal   : Merkel/Poppe demand curve, fill supply curve, rating      (Phase 1)
  size      : cells, plan, fill depth, air side, fan, water side, basin (Phase 2)
  structure : FRP framing, ASCE 7 loads, PyNite frame FEA, BOM          (Phase 3)
  drawings  : DXF/SVG general arrangement and framing sheets            (Phase 4)
  model     : FreeCAD 3D model via freecadcmd (STEP + FCStd)            (Phase 5)
  report    : REPORT.md and CTI-style datasheet                         (Phase 2+)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctdesign import spec as specmod                                  # noqa: E402
from ctdesign import thermal_design, plots                            # noqa: E402

STAGES = ["basis", "thermal", "size", "structure", "drawings", "model", "report"]
IMPLEMENTED = {"basis", "thermal"}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


def stage_basis(b: specmod.Basis, out: Path) -> dict:
    s = b.spec
    basis = {"project": s["project"], "P_atm_Pa": b.P_atm, "T_wb_C": b.T_wb, "T_db_C": b.T_db,
             "T_hot_C": b.T_hot, "T_cold_C": b.T_cold, "range_K": b.range, "approach_K": b.approach,
             "m_w_kg_s": b.m_w, "V_w_m3_h": b.V_w, "rho_w": b.rho_w, "cp_w": b.cp_w, "Q_W": b.Q}
    (out / "data" / "basis.json").write_text(json.dumps(basis, indent=2), encoding="utf-8")
    print(f"[basis] {s['project']['tag']}: {b.V_w:,.0f} m3/h  {b.T_hot:.1f} -> {b.T_cold:.1f} C  "
          f"WB {b.T_wb:.1f} C  range {b.range:.1f} K  approach {b.approach:.1f} K  "
          f"Q {b.Q / 1e6:.2f} MW  P {b.P_atm / 1e3:.2f} kPa")
    return basis


def stage_thermal(b: specmod.Basis, out: Path) -> dict:
    t = thermal_design.run(b)
    (out / "data" / "thermal.json").write_text(json.dumps(_jsonable(t), indent=2), encoding="utf-8")
    print("[thermal] depth   L/G    Me_fill Me_rain  Me_tot  G dry(kg/s)  T_out  evap%  capab%")
    for p in t["points"]:
        if not p["feasible"]:
            print(f"[thermal] {p['depth']:5.2f}  infeasible: {p['reason']}")
            continue
        print(f"[thermal] {p['depth']:5.2f}  {p['LG']:5.3f}  {p['Me_fill']:6.3f}  {p['Me_rain']:6.3f}  "
              f"{p['Me_total']:6.3f}  {p['G_dry_kg_s']:10.1f}  {p['T_air_out']:5.1f}  {p['evap_pct']:5.2f}  "
              f"{p['capability_pct']:6.1f}")
    if not t["feasible"]:
        print("[thermal] NO FEASIBLE DEPTH: deepen the fill, choose a better fill or relax the approach.")
        return t
    s = t["selected"]
    print(f"[thermal] selected depth {s['depth']:.2f} m, L/G {s['LG']:.3f}, Poppe Me {s['Me_poppe']:.3f}, "
          f"exit air {s['T_air_out']:.1f} C RH {100 * s['RH_out']:.0f} %, evaporation {s['evap_kg_s']:.2f} kg/s "
          f"({s['evap_pct']:.2f} %), plume {'likely' if s['plume_visible'] else 'unlikely'} at design")
    print(f"[thermal] rating check at design: cold water {t['design_check']['T_cold']:.3f} C (target {b.T_cold:.2f})")
    for r in t["ratings"]:
        print(f"[thermal] rating '{r['label']}': WB {r['T_wb']:.1f}  cold {r['T_cold']:.2f} C  hot {r['T_hot']:.2f} C")
    for w in s["warnings"]:
        print(f"[thermal] WARNING: {w}")
    plots.demand_supply(t, out / "plots" / "01_demand_supply.svg")
    plots.performance(t, out / "plots" / "02_performance_curves.svg")
    plots.poppe_profile(t, b.P_atm, out / "plots" / "03_poppe_profile.svg")
    return t


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out", default="ct_results")
    ap.add_argument("--stage", choices=["all"] + STAGES, default="all")
    ap.add_argument("--quick", action="store_true", help="smaller grid for a fast first pass")
    ap.add_argument("--params", default=None, help="JSON geometry to use instead of the optimum")
    a = ap.parse_args(argv)

    out = Path(a.out)
    for sub in ("data", "plots", "drawings", "model"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    b = specmod.load(a.spec)
    (out / "data" / "spec_used.json").write_text(json.dumps(b.spec, indent=2), encoding="utf-8")

    for st in (STAGES if a.stage == "all" else [a.stage]):
        if st not in IMPLEMENTED:
            print(f"[{st}] not implemented yet")
            continue
        if st == "basis":
            stage_basis(b, out)
        elif st == "thermal":
            stage_thermal(b, out)


if __name__ == "__main__":
    main()
