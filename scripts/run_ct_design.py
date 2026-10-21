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
import pandas as pd

from ctdesign import thermal_design, plots, sizing, report, structure, bom   # noqa: E402
from ctdesign import drawings_dxf                                          # noqa: E402

STAGES = ["basis", "thermal", "size", "structure", "drawings", "model", "report"]
IMPLEMENTED = {"basis", "thermal", "size", "structure", "drawings", "report"}


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


def stage_size(b: specmod.Basis, out: Path, quick: bool, params: str | None) -> dict:
    cand = out / "data" / "candidates.csv.gz"
    df = sizing.optimise(b, quick)
    df.to_csv(cand, index=False)
    print(f"[size] {len(df):,} candidates, {int(df.feasible.sum()):,} feasible")
    if params:
        p = json.loads(params)
    else:
        best = sizing.select(df)
        if best is None:
            msg = df.violations.str.split("; ").explode().value_counts().head(8).to_string()
            print("[size] NO FEASIBLE DESIGN. Most common rejection reasons:\n" + msg)
            print("Relax the binding limits or widen the grid, and rerun.")
            sys.exit(2)
        p = {k: best[k].item() if hasattr(best[k], "item") else best[k] for k in sizing.PARAM_KEYS}
    d = sizing.finalize(b, p)
    d["candidates"] = df
    t, g, fn = d["thermal"], d["geom"], d["fan"]
    plots.demand_supply(t, out / "plots" / "01_demand_supply.svg")
    plots.performance(t, out / "plots" / "02_performance_curves.svg")
    plots.poppe_profile(t, b.P_atm, out / "plots" / "03_poppe_profile.svg")
    plots.pressure_breakdown(d, out / "plots" / "04_pressure_breakdown.svg")
    if df.feasible.any():
        sel = df[(df[sizing.PARAM_KEYS] == pd.Series(p)).all(axis=1)]
        plots.optimisation(df, sel.iloc[0] if len(sel) else sizing.select(df), out / "plots" / "05_optimisation.svg")
    res = {k: d[k] for k in ("params", "summary", "air", "fan", "hyd", "cost", "water_balance", "basin",
                             "warnings", "violations")}
    res.update(geometry=g.to_dict(), thermal={"selected": t["selected"], "ratings": t["ratings"],
                                              "performance": t["performance"], "design_check": t["design_check"]},
               basis={"V_w_m3_h": b.V_w, "T_hot": b.T_hot, "T_cold": b.T_cold, "T_wb": b.T_wb, "Q_W": b.Q,
                      "P_atm": b.P_atm})
    (out / "data" / "design_results.json").write_text(json.dumps(_jsonable(res), indent=2), encoding="utf-8")
    print(f"[size] {g.cells} cells x {g.L} x {g.W} m, fill {g.depth} m, inlet {g.H_inlet} m, height {g.z['stack_top']:.2f} m, "
          f"L/G {t['selected']['LG']:.3f}")
    print(f"[size] fans {g.cells} x {fn['D']} m, {fn['motor_kW']} kW, static {fn['dP_fan_static']:.0f} Pa; pump head "
          f"{d['hyd']['pump_head_m']:.2f} m; makeup {d['water_balance']['makeup_m3_h']:.1f} m3/h; "
          f"capex {d['cost']['capex_total']:,.0f}, TPC {d['cost']['total_present_cost']:,.0f}; "
          f"violations {d['violations'] or 'none'}")
    return d


def _reload(b: specmod.Basis, out: Path) -> dict:
    """Rebuild the selected design from design_results.json (for stage-by-stage runs)."""
    res = json.loads((out / "data" / "design_results.json").read_text(encoding="utf-8"))
    d = sizing.finalize(b, res["params"])
    cand = out / "data" / "candidates.csv.gz"
    d["candidates"] = pd.read_csv(cand) if cand.exists() else pd.DataFrame()
    return d


def stage_structure(b: specmod.Basis, out: Path, d: dict | None) -> dict:
    d = d or _reload(b, out)
    st = structure.design(d, b, b.spec)
    B = bom.build(d, b, b.spec, st)
    summ = bom.summary(B)
    bom.apply_cost(d, b.spec, summ)
    d["structure"], d["bom"], d["bom_summary"] = st, B, summ
    tag = b.spec["project"]["tag"]
    B.to_csv(out / "data" / f"{tag}_BOM.csv", index=False)
    with pd.ExcelWriter(out / "data" / f"{tag}_BOM.xlsx") as xw:
        B.to_excel(xw, sheet_name="BOM", index=False)
        pd.DataFrame([{"group": g, **v} for g, v in st["groups"].items()]).to_excel(xw, sheet_name="Member groups", index=False)
        pd.DataFrame([{"group": g, **v} for g, v in st["connections"].items()]).to_excel(xw, sheet_name="Connections", index=False)
    (out / "data" / "structure.json").write_text(
        json.dumps(_jsonable({k: v for k, v in st.items() if k != "members"}), indent=2, default=str), encoding="utf-8")
    plots.structure_ur(st, out / "plots" / "06_structure_utilisation.svg")
    print(f"[structure] {st['n_members']} members analysed ({st['grid']['cells_modelled']} cell block), "
          f"max UR {max(v['UR_max'] for v in st['groups'].values()):.2f}; FRP {summ['frp_structure_kg'] / 1e3:.1f} t + "
          f"connections {summ['connections_kg'] / 1e3:.1f} t; seismic Cs {st['seismic']['Cs']:.3f}; "
          f"violations {st['violations'] or 'none'}")
    return d


def stage_drawings(b: specmod.Basis, out: Path, d: dict | None) -> dict:
    if d is None:
        d = _reload(b, out)
        if (out / "data" / "structure.json").exists():
            d = stage_structure(b, out, d)
    sheets = drawings_dxf.make_all(d, b, out / "drawings")
    d["drawings"] = sheets
    (out / "data" / "drawing_register.json").write_text(json.dumps(sheets, indent=2), encoding="utf-8")
    print(f"[drawings] {len(sheets)} sheets (DXF + SVG + PDF + PNG) and "
          f"{b.spec['project']['tag']}_drawing_set.pdf in {(out / 'drawings').resolve()}")
    return d


def stage_report(b: specmod.Basis, out: Path, d: dict | None) -> None:
    if d is None:                                         # report-only run: rebuild from the saved selection
        d = _reload(b, out)
        if (out / "data" / "structure.json").exists():
            d = stage_structure(b, out, d)
    tag = b.spec["project"]["tag"]
    files = {"REPORT.md": "Technical design report", "DATASHEET.md": "CTI-style datasheet",
             f"data/{tag}_datasheet.xlsx": "Datasheet (Excel)", "data/design_results.json": "Every computed value",
             "data/candidates.csv.gz": "All optimiser candidates with rejection reasons",
             "plots/01_demand_supply.svg": "Demand vs tower characteristic", "plots/02_performance_curves.svg": "Performance curves",
             "plots/03_poppe_profile.svg": "Poppe profile and air path", "plots/04_pressure_breakdown.svg": "Air-side losses",
             "plots/05_optimisation.svg": "Optimisation trade-off"}
    for sh in d.get("drawings", []):
        rel = Path(sh[".dxf"]).relative_to(out).as_posix()
        files[rel.replace(".dxf", ".dxf / .svg / .pdf")] = f"{sh['number']} {sh['title'].title()} ({sh['scale']})"
    if d.get("drawings"):
        files[f"drawings/{tag}_drawing_set.pdf"] = "Complete drawing set (PDF, A1)"
    if "structure" in d:
        files.update({f"data/{tag}_BOM.xlsx": "Fabrication BOM, member groups, connections (Excel)",
                      f"data/{tag}_BOM.csv": "Fabrication BOM (CSV)", "data/structure.json": "Structural results",
                      "plots/06_structure_utilisation.svg": "FRP frame coloured by utilisation"})
    report.write_datasheet(d, b, out / "DATASHEET.md", out / "data" / f"{tag}_datasheet.xlsx")
    report.write_report(d, b, d["candidates"], out / "REPORT.md", files)
    print(f"[report] {out.resolve() / 'REPORT.md'}")


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

    d = None
    for st in (STAGES if a.stage == "all" else [a.stage]):
        if st not in IMPLEMENTED:
            print(f"[{st}] not implemented yet")
            continue
        if st == "basis":
            stage_basis(b, out)
        elif st == "thermal" and a.stage == "thermal":      # `all` gets the thermal design from `size`
            stage_thermal(b, out)
        elif st == "size":
            d = stage_size(b, out, a.quick, a.params)
        elif st == "structure":
            d = stage_structure(b, out, d)
        elif st == "drawings":
            d = stage_drawings(b, out, d)
        elif st == "report":
            stage_report(b, out, d)


if __name__ == "__main__":
    main()
