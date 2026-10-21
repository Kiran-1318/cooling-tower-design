"""Sizing and cost optimisation of the tower, and finalisation of the selected design.

Each candidate (cells, cell L x W, fill depth, fan diameter) is screened with the Merkel
design point (cached per fill depth and rain-zone height), the air-inlet rule, the air-side
loss build-up, the fan, the water distribution and the cost model. The objective is the
total present cost = capital + present value of fan and tower-pump energy; capital is driven
by FRP weight (estimated per m3 of cell envelope until Phase 3), fill volume, eliminator,
casing, fan sets, basin and a fixed cost per cell, so the optimiser sees size, not just area.
The cheapest feasible candidate is then finalised with the full Poppe solution.
"""
from __future__ import annotations

import itertools
import math

import pandas as pd

from . import airside, basin, fan, geometry, hydraulics, psychro as ps, water_balance
from . import thermal_design
from .fill import load_library

PARAM_KEYS = ["cells", "L", "W", "depth", "fan_D"]


def _flows(b, tp: dict, cells: int, plan_area: float) -> dict:
    P, air = b.P_atm, tp["air_in"]
    g = tp["G_dry_kg_s"] / cells
    rho_in = air["rho"]
    rho_out = float(ps.rho_moist(tp["T_air_out"], tp["W_out"], P))
    W_m = 0.5 * (air["W"] + tp["W_out"])
    rho_m = float(ps.rho_moist(0.5 * (air["T_db"] + tp["T_air_out"]), W_m, P))
    return {"Q_in": g * (1 + air["W"]) / rho_in, "Q_mean": g * (1 + W_m) / rho_m,
            "Q_out": g * (1 + tp["W_out"]) / rho_out, "rho_in": rho_in, "rho_mean": rho_m, "rho_out": rho_out,
            "Gw": b.m_w / plan_area, "Ga": tp["G_dry_kg_s"] / plan_area, "g_dry_cell": g}


def costs(b, geom, fn: dict, hyd: dict, s: dict) -> dict:
    c, t = s["costs"], s["tower"]
    n, A = geom.cells, geom.plan_area
    env_h = geom.z["fan_deck"] - geom.z["curb"]
    frp_kg = c["frp_kg_per_m3"] * A * env_h
    wall_h = geom.z["fan_deck"] - geom.z["inlet_top"]
    if t["air_inlets"] == "two_sides":
        casing = 2 * n * geom.L * wall_h + 2 * geom.W * env_h
    else:
        casing = 2 * (geom.L + geom.W) * wall_h
    capex = {"frp_structure": frp_kg * c["frp_per_kg"], "fill": A * geom.depth * c["fill_per_m3"],
             "eliminators": A * c["eliminator_per_m2"], "casing_and_deck": (casing + A) * c["casing_per_m2"],
             "fan_sets": n * fn["motor_kW"] * c["fan_set_per_kW"], "basin": A * c["basin_per_m2"],
             "fixed": n * c["fixed_per_cell"]}
    kW = n * fn["P_input_kW"] + hyd["pump_kW"]
    r, y = c["rate"], c["years"]
    pv = (1 - (1 + r) ** -y) / r if r > 0 else y
    energy_pv = kW * c["hours_per_year"] * c["electricity_per_kWh"] * pv
    cap = sum(capex.values())
    return {"capex": capex, "capex_total": cap, "energy_kW": kW, "energy_pv": energy_pv,
            "total_present_cost": cap + energy_pv, "frp_kg_estimate": frp_kg, "casing_m2": casing}


def evaluate(b, cells, L, W, depth, fan_D, cache: dict, lib: dict, poppe: bool = False) -> dict:
    """Size one candidate. Returns a flat record with violations ('' if feasible) and the parts."""
    s = b.spec
    f, lim, t = s["fan"], s["limits"], s["tower"]
    rec = {"cells": cells, "L": L, "W": W, "depth": depth, "fan_D": fan_D}
    viol = []
    if fan_D + 2 * f["tip_clearance_m"] > min(L, W) + 1e-9:
        viol.append("fan does not fit the cell")
    if fan_D < f["min_cover"] * min(L, W) - 1e-9:
        viol.append("fan too small for the cell (air distribution)")
    if viol:
        return {**rec, "violations": "; ".join(viol), "feasible": False}

    # inlet height <-> rain zone <-> L/G fixed point (converges in 2-3 passes)
    H_in, rule = lim["inlet_height_min_m"], "minimum"
    tp = None
    for _ in range(5):
        H_rain = round(geometry.CURB + H_in + geometry.FILL_SUPPORT, 3)
        key = (depth, H_rain, poppe)
        if key not in cache:
            cache[key] = thermal_design.design_point(b, depth, lib, H_rain=H_rain, poppe=poppe)
        tp = cache[key]
        if not tp["feasible"]:
            return {**rec, "violations": "thermal: fill cannot meet the duty", "feasible": False}
        fl = _flows(b, tp, cells, cells * L * W)
        H_new, rule = geometry.inlet_height(L, W, fl["Q_in"], s)
        if abs(H_new - H_in) < 1e-6:
            break
        H_in = H_new

    header_D = hydraulics.pick_dn(b.V_w / 3600 / cells, s["water_system"]["header_velocity_max_m_s"]) / 1e3
    geom = geometry.build(cells, L, W, depth, fan_D, H_in, rule, header_D, s)
    ch = tp["_char"]
    air = airside.losses(geom, fl, ch, s)
    fn = fan.select(geom, air, fl["Q_out"], fl["rho_out"], s)
    hyd = hydraulics.design(geom, b, s)
    cost = costs(b, geom, fn, hyd, s) if fn["motor_kW"] else None

    loading = b.V_w / geom.plan_area
    lo, hi = lim["water_loading_m3_h_m2"]
    flo, fhi = ch.fill["water_loading_m3_h_m2"]
    if not max(lo, flo) <= loading <= min(hi, fhi):
        viol.append(f"water loading {loading:.1f} outside {max(lo, flo):.0f}-{min(hi, fhi):.0f} m3/h.m2")
    lo, hi = lim["fill_air_velocity_m_s"]
    if not lo <= air["v_fill"] <= hi:
        viol.append(f"fill air velocity {air['v_fill']:.2f} outside {lo}-{hi} m/s")
    if air["v_eliminator"] > lim["eliminator_velocity_max_m_s"]:
        viol.append(f"eliminator velocity {air['v_eliminator']:.2f} > {lim['eliminator_velocity_max_m_s']} m/s")
    if air["v_inlet"] > lim["air_inlet_velocity_max_m_s"] + 1e-6:
        viol.append(f"inlet velocity {air['v_inlet']:.2f} m/s too high")
    lo, hi = f["fan_velocity_m_s"]
    if not lo <= air["v_fan"] <= hi:
        viol.append(f"fan velocity {air['v_fan']:.1f} outside {lo}-{hi} m/s")
    if fn["dP_fan_static"] > lim["fan_static_max_Pa"]:
        viol.append(f"fan static {fn['dP_fan_static']:.0f} Pa > {lim['fan_static_max_Pa']:.0f}")
    if fn["tip_speed"] > lim["fan_tip_speed_max_m_s"]:
        viol.append("fan tip speed above limit")
    if fn["motor_kW"] is None:
        viol.append("motor above the largest standard size")
    if b.T_hot > ch.fill["max_hot_water_C"]:
        viol.append(f"hot water above the {ch.fill['material']} fill limit")
    viol += hyd["violations"]

    rec.update({"H_inlet": H_in, "inlet_rule": rule, "LG": tp["LG"], "height_m": geom.z["stack_top"],
                "loading_m3_h_m2": loading, "v_fill": air["v_fill"], "v_inlet": air["v_inlet"],
                "v_fan": air["v_fan"], "fan_static_Pa": fn["dP_fan_static"], "fan_input_kW_cell": fn["P_input_kW"],
                "motor_kW": fn["motor_kW"], "pump_head_m": hyd["pump_head_m"], "pump_kW": hyd["pump_kW"],
                "nozzle_kPa": hyd["dp_nozzle_kPa"],
                "capex": cost["capex_total"] if cost else math.nan, "energy_kW": cost["energy_kW"] if cost else math.nan,
                "TPC": cost["total_present_cost"] if cost else math.nan,
                "violations": "; ".join(viol), "feasible": not viol})
    rec["_parts"] = {"thermal": tp, "flows": fl, "geom": geom, "air": air, "fan": fn, "hyd": hyd, "cost": cost}
    return rec


def grid(s: dict, quick: bool = False):
    t, g = s["tower"], s["grid"]
    cells = [t["cells"]] if t["cells"] else g["cells"]
    plans = [[t["cell_length_m"], t["cell_width_m"]]] if t["cell_length_m"] and t["cell_width_m"] else g["cell_plan_m"]
    depths = [t["fill_depth_m"]] if t["fill_depth_m"] else g["fill_depth_m"]
    fans = [t["fan_diameter_m"]] if t["fan_diameter_m"] else g["fan_diameter_m"]
    if quick:
        depths = depths[::2] or depths
    return itertools.product(cells, plans, depths, fans)


def optimise(b, quick: bool = False) -> pd.DataFrame:
    lib, cache, rows = load_library(), {}, []
    for cells, (L, W), depth, D in grid(b.spec, quick):
        r = evaluate(b, cells, L, W, depth, D, cache, lib)
        r.pop("_parts", None)
        rows.append(r)
    return pd.DataFrame(rows)


def select(df: pd.DataFrame):
    ok = df[df.feasible.astype(bool)]
    return None if ok.empty else ok.nsmallest(1, "TPC").iloc[0]


def finalize(b, p: dict) -> dict:
    """Full design of one geometry with the Poppe solution, water balance, basin and curves."""
    lib = load_library()
    rec = evaluate(b, int(p["cells"]), float(p["L"]), float(p["W"]), float(p["depth"]), float(p["fan_D"]),
                   {}, lib, poppe=True)
    if "_parts" not in rec:
        raise ValueError(f"forced geometry is not workable: {rec['violations']}")
    parts = rec.pop("_parts")
    tp, geom = parts["thermal"], parts["geom"]
    evap_m3_h = tp["evap_kg_s"] / parts["hyd"]["rho"] * 3600
    wb = water_balance.balance(b.V_w, evap_m3_h, b.spec["tower"]["drift_rate_pct"],
                               b.spec["water"]["cycles_of_concentration"], b.range)
    bs = basin.design(geom, b, parts["hyd"], wb, b.spec)
    th = {"selected": tp, **thermal_design.curves(b, tp)}
    warnings = list(dict.fromkeys(tp["warnings"] + bs["notes"]))
    return {"params": {k: rec[k] for k in PARAM_KEYS}, "summary": rec, "thermal": th, "geom": geom,
            "flows": parts["flows"], "air": parts["air"], "fan": parts["fan"], "hyd": parts["hyd"],
            "cost": parts["cost"], "water_balance": wb, "basin": bs, "warnings": warnings,
            "violations": [v for v in rec["violations"].split("; ") if v]}
