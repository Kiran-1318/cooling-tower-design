"""Fabrication bill of materials for the whole tower (all cells).

The member sizes come from the analysed block (structure.design) and are applied to the framing of
the full row of cells. Beams are continuous per ASCE 74 and are cut from stock lengths
(structure.stock_length_m) spliced at columns; columns run floor-to-deck in one piece when the stock
allows. Connections: a pair of FRP clip angles at every beam end, through-bolted brace ends, a bolted
splice (two FRP plates, 2 x 4 bolts) at every beam joint, one SS anchor bracket per column base.
Weights of non-structural items are estimates and flagged as such.
"""
from __future__ import annotations

import math
from collections import Counter

import pandas as pd

from . import frp, structure

G = 9.81


def _row(cat, item, spec, qty, unit, unit_kg=0.0, note=""):
    return {"category": cat, "item": item, "specification": spec, "qty": round(qty, 2), "unit": unit,
            "unit_kg": round(unit_kg, 2), "total_kg": round(qty * unit_kg, 1), "note": note}


def build(d: dict, b, s: dict, st_res: dict) -> pd.DataFrame:
    g, st, t = d["geom"], s["structure"], s["tower"]
    secs, mat, sizes = st_res["_sections"], st_res["_mat"], st_res["sizes"]
    full = structure.framing(d, {**s, "structure": {**st, "model_cells_max": g.cells}})
    rows = []
    stock, col_stock = st["stock_length_m"], st["column_stock_length_m"]

    # ---- columns: one per grid point, floor to deck
    cols = Counter()
    for mb in full["members"]:
        if mb["kind"] == "column":
            key = mb["i"].rsplit("_", 1)[0]
            cols[key] += mb["L"]
    H = next(iter(cols.values()))
    sec = secs["column"]
    pieces = math.ceil(H / col_stock - 1e-9)
    rows.append(_row("FRP structure", "Column", f"{sec.name} pultruded, {mat.name}", len(cols) * pieces, "pc",
                     sec.mass_per_m(mat.rho) * H / pieces, f"cut length {H / pieces:.3f} m"
                     + (f", {pieces - 1} splice(s) each" if pieces > 1 else "")))

    # ---- beams: continuous lines cut into stock pieces spliced at columns
    splices = 0
    beam_ends = 0
    lines = {}
    for mb in full["members"]:
        if mb["kind"] == "beam":
            key = (mb["group"], mb["dir"], mb["tier"], mb["line"])
            lines.setdefault(key, []).append(mb["L"])
    per_group = Counter()
    for (grp, _, _, _), bays in lines.items():
        sec = secs[grp]
        total = sum(bays)
        bay = max(bays)
        per_piece = max(1, int(stock / bay + 1e-3))          # grid coordinates are rounded to 0.1 mm
        n_pieces = math.ceil(len(bays) / per_piece)
        splices += n_pieces - 1
        beam_ends += 2 * len(bays)
        per_group[(grp, round(min(per_piece, len(bays)) * bay, 3))] += n_pieces - (1 if len(bays) % per_piece else 0)
        if len(bays) % per_piece:
            per_group[(grp, round((len(bays) % per_piece) * bay, 3))] += 1
    for (grp, cut), qty in sorted(per_group.items()):
        sec = secs[grp]
        rows.append(_row("FRP structure", grp.replace("_", " ").capitalize(), f"{sec.name} pultruded", qty, "pc",
                         sec.mass_per_m(mat.rho) * cut, f"cut length {cut:.3f} m"))

    # ---- braces
    sec_b, sec_c = secs["brace"], secs["column"]
    braces = Counter(round(mb["L"] - sec_c.bf - 0.05, 3) for mb in full["members"] if mb["kind"] == "brace")
    for cut, qty in sorted(braces.items()):
        rows.append(_row("FRP structure", "Diagonal brace", f"{sec_b.name} pultruded", qty, "pc",
                         sec_b.mass_per_m(mat.rho) * cut, f"cut length {cut:.3f} m (centre-to-centre less column)"))

    # ---- connections
    con = st_res["connections"]
    clip = frp.make_section("L", [3.0, 3.0, 0.25])
    clip_len = 0.15
    n_clip = 2 * beam_ends
    rows.append(_row("Connections", "Clip angle", f"FRP L3x3x1/4, {clip_len * 1e3:.0f} mm long", n_clip, "pc",
                     clip.A * mat.rho * clip_len, "pair at every beam end"))
    bolts = Counter()
    for grp, c in con.items():
        n_members = sum(1 for mb in full["members"] if mb["group"] == grp)
        if grp == "brace":                       # gusset plate at each end: brace-to-gusset and gusset-to-column
            bolts[(c["d_mm"], round(secs["brace"].bf * 1e3 + 12 + 25))] += 2 * c["bolts"] * n_members
            bolts[(c["d_mm"], round(sec_c.bf * 1e3 + 12 + 25))] += 2 * c["bolts"] * n_members
            rows.append(_row("Connections", "Brace gusset plate", "FRP plate 12 mm, 250 x 250 mm", 2 * n_members, "pc",
                             mat.rho * 0.012 * 0.25 * 0.25))
        else:
            grip = secs[grp].t * 1e3 + 2 * clip.t * 1e3 + 25
            bolts[(c["d_mm"], round(grip))] += 2 * c["bolts"] * n_members          # beam web through both clips
            bolts[(c["d_mm"], round(sec_c.bf * 1e3 + clip.t * 1e3 + 25))] += 4 * c["bolts"] * n_members  # each clip to column
    for (dmm, Lmm), qty in sorted(bolts.items()):
        rows.append(_row("Connections", "Hex bolt + nut + 2 washers", f"{st['fastener_material']} M{dmm} x {Lmm} mm",
                         qty, "set", 7850 * math.pi / 4 * (dmm / 1e3) ** 2 * Lmm / 1e3 * 1.4))
    if splices:
        rows.append(_row("Connections", "Beam splice plate", "FRP plate 10 mm, 2 per splice", 2 * splices, "pc",
                         mat.rho * 0.01 * 0.15 * 0.6, "develop 50 % flexure / 25 % tension of the beam (ASCE 74)"))
        rows.append(_row("Connections", "Splice bolt set", f"{st['fastener_material']} M16", 8 * splices, "set", 0.35))
    rows.append(_row("Connections", "Column base anchor bracket", f"{st['fastener_material']} bracket + 2 anchors M16",
                     len(cols), "set", 6.0, f"max uplift {st_res['base_reactions']['max_uplift_kN']:.1f} kN, "
                     f"shear {st_res['base_reactions']['max_shear_kN']:.1f} kN per column"))

    # ---- envelope
    two = t["air_inlets"] == "two_sides"
    wall_h = g.z["fan_deck"] - g.z["inlet_top"]
    end_h = g.z["fan_deck"] - g.z["curb"]
    casing = (2 * g.cells * g.L * wall_h + 2 * g.W * end_h) if two else 2 * (g.L + g.W) * wall_h
    rows.append(_row("Envelope", "Casing panel", "FRP corrugated, fire-retardant", casing, "m2", 8.0, "side walls above inlet, end walls full height"))
    if g.cells > 1:
        part = (g.cells - 1) * g.W * (g.z["fan_deck"] - g.z["elim_top"])
        rows.append(_row("Envelope", "Partition wall panel", "FRP flat, plenum height", part, "m2", 8.0, "isolates each cell's plenum"))
    fan_open = g.cells * math.pi / 4 * (d["fan"]["D"] + 0.2) ** 2
    rows.append(_row("Envelope", "Fan deck panel", "FRP deck, 2.4 kPa", g.plan_area - fan_open, "m2", 30.0))
    if t["inlet_louvers"]:
        rows.append(_row("Envelope", "Inlet louver", "PVC/FRP rain-trap", 2 * g.cells * g.L * g.H_inlet, "m2", 6.0))

    # ---- heat transfer and water
    ch = d["thermal"]["selected"]["_char"]
    mod = ch.fill.get("module_m", [0.305, 0.305, 1.219])
    fill_v = g.plan_area * g.depth
    rows.append(_row("Fill & eliminators", "Fill pack", f"{ch.fill_type}: {ch.fill['description']}", fill_v, "m3",
                     ch.fill.get("density_dry_kg_m3", 35.0), f"~{math.ceil(fill_v / (mod[0] * mod[1] * mod[2] if len(mod) == 3 else 1)):,} modules of {mod} m"))
    rows.append(_row("Fill & eliminators", "Drift eliminator", f"{t['drift_eliminator']}, drift {t['drift_rate_pct']} %", g.plan_area, "m2", 8.0))
    hy = d["hyd"]
    rows.append(_row("Water distribution", "Spray nozzle", f"low-pressure, {hy['orifice_mm']} mm orifice, {hy['q_nozzle_m3_h']:.1f} m3/h @ {hy['dp_nozzle_kPa']:.0f} kPa",
                     g.cells * hy["nozzles_per_cell"], "pc", 0.4))
    rows.append(_row("Water distribution", "Header pipe", f"FRP DN{hy['header_DN']}", g.cells * g.W, "m", 0.0, "weight by pipe class"))
    rows.append(_row("Water distribution", "Lateral pipe", f"PVC/FRP DN{hy['lateral_DN']}", g.cells * hy["laterals_per_cell"] * g.L / 2, "m"))
    rows.append(_row("Water distribution", "Riser + isolation valve", f"FRP DN{hy['riser_DN']} + butterfly valve", g.cells, "set"))

    # ---- mechanical
    fn = d["fan"]
    rows.append(_row("Mechanical", "Axial fan", f"{fn['D']:.1f} m, {fn['fan_rpm']:.0f} rpm, FRP blades, adjustable pitch", g.cells, "set",
                     st_res["equipment_kg_per_cell"] * 0.55, "vendor selection"))
    rows.append(_row("Mechanical", "Right-angle gear reducer", f"ratio {fn['gear_ratio']:.2f}:1, CTI STD-111 service factor", g.cells, "pc",
                     st_res["equipment_kg_per_cell"] * 0.3))
    rows.append(_row("Mechanical", "Motor", f"{fn['motor_kW']} kW, {t['motor_poles']}-pole, {t['power_supply']}, TEFC, IP55", g.cells, "pc",
                     st_res["equipment_kg_per_cell"] * 0.15))
    rows.append(_row("Mechanical", "Drive shaft + couplings", "composite, non-lubricated", g.cells, "set"))
    rows.append(_row("Mechanical", "Vibration switch + oil level gauge", "", g.cells, "set"))
    rows.append(_row("Mechanical", "Fan stack", f"FRP, {fn['stack'].replace('_', ' ')}, {fn['stack_H']:.1f} m, exit {fn['stack_exit_D']:.2f} m",
                     g.cells, "pc", st_res["stack_kg_per_cell"]))

    # ---- access and basin
    rows.append(_row("Access", "Handrail + toe board", "FRP, fan deck perimeter", 2 * (g.cells * g.L + g.W), "m", 4.0))
    rows.append(_row("Access", "Caged ladder", "FRP, grade to fan deck", 1, "pc", 12.0 * (g.z["fan_deck"] + 1)))
    rows.append(_row("Access", "Casing access door", "FRP, 0.9 x 1.5 m", g.cells, "pc", 25.0))
    bs = d["basin"]
    for k, v in bs["connections"].items():
        rows.append(_row("Basin (civil by others)", k.replace("_DN", "").capitalize() + " connection", f"DN{v}", 1, "pc"))
    rows.append(_row("Basin (civil by others)", "Sump suction screen", f"SS, for {bs['pumps_duty']}+{bs['pumps_standby']} pumps", bs["pumps_duty"] + bs["pumps_standby"], "pc"))
    return pd.DataFrame(rows)


def apply_cost(d: dict, s: dict, summ: dict) -> None:
    """Replace the Phase-2 volumetric FRP estimate with the BOM weight (framing + connections)."""
    c = d["cost"]
    old = c["capex"]["frp_structure"]
    c["capex"]["frp_structure"] = (summ["frp_structure_kg"] + summ["connections_kg"]) * s["costs"]["frp_per_kg"]
    c["capex_total"] = sum(c["capex"].values())
    c["total_present_cost"] = c["capex_total"] + c["energy_pv"]
    c["frp_kg_bom"] = summ["frp_structure_kg"] + summ["connections_kg"]
    c["frp_structure_estimate_was"] = old


def summary(bom: pd.DataFrame) -> dict:
    frp_kg = bom.loc[bom.category == "FRP structure", "total_kg"].sum()
    con_kg = bom.loc[bom.category == "Connections", "total_kg"].sum()
    return {"frp_structure_kg": float(frp_kg), "connections_kg": float(con_kg),
            "total_kg": float(bom.total_kg.sum()), "by_category_kg": bom.groupby("category").total_kg.sum().round(0).to_dict()}
