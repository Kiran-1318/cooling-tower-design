"""Thermal stage: from the design basis to a design L/G, exit air, evaporation and ratings.

For each candidate fill depth the design L/G is where the tower characteristic (fill + rain +
spray) meets the Merkel demand, reduced so the tower shows the required thermal capability
(CTI: capability C% means it cools C% of design flow at design conditions, so
L/G_design = L/G_intersection / (C/100)). Poppe is then run at the design point for the
exit air, evaporation and plume. Geometry (cells, plan, fan) is Phase 2; until then the rain
zone height is tower.air_inlet_height_m + 0.3 m, or 2.0 m flagged as provisional.
"""
from __future__ import annotations

import numpy as np

from . import psychro as ps
from . import thermal as th
from .fill import characteristic, load_library
from .spec import Basis


def rain_zone_height(tower: dict) -> tuple[float, str | None]:
    if tower.get("air_inlet_height_m"):
        return float(tower["air_inlet_height_m"]) + 0.3, None
    return 2.0, "rain-zone height provisional (2.0 m) until the air-inlet geometry is sized (Phase 2)"


def plume_visible(air_out: dict, air_amb: dict, P: float, n: int = 50) -> bool:
    """True if the mixing line of exit air with ambient air crosses the saturation curve."""
    x = np.linspace(0.0, 1.0, n)
    T = air_out["T"] + x * (air_amb["T_db"] - air_out["T"])
    W = air_out["W"] + x * (air_amb["W"] - air_out["W"])
    return bool(np.any(W[1:-1] > ps.W_sat(T[1:-1], P)))


def design_point(b: Basis, depth: float, lib: dict | None = None) -> dict:
    s, P = b.spec, b.P_atm
    cpw = b.cp_w
    H_rain, h_note = rain_zone_height(s["tower"])
    ch = characteristic(s["tower"], depth, H_rain, lib)
    air = ps.air_state(b.T_db, b.T_wb, P)
    lg_int = th.operating_LG(b.T_hot, b.T_cold, air["h"], P, ch, cpw)
    if lg_int is None:
        return {"depth": depth, "feasible": False, "reason": "tower characteristic below demand at every L/G"}
    cap = s["limits"]["thermal_capability_min_pct"] / 100.0
    LG = lg_int / cap
    G = b.m_w / LG                                                    # kg/s dry air
    pp = th.poppe(b.T_hot, b.T_cold, LG, air, P, cpw)
    out_air = {"T": pp["T_air_out"], "W": pp["W_out"]}
    warnings = ch.check(LG, b.T_hot) + ([h_note] if h_note else [])
    return {"depth": depth, "feasible": True, "H_rain": H_rain, "LG_intersect": lg_int, "LG": LG, "G_dry_kg_s": G,
            "Me_demand": float(th.merkel(b.T_hot, b.T_cold, LG, air["h"], P, cpw)),
            "Me_demand_chebyshev": float(th.merkel(b.T_hot, b.T_cold, LG, air["h"], P, cpw, method="chebyshev")),
            **ch.breakdown(LG),
            "capability_pct": th.capability(ch, LG, b.T_hot, b.T_cold, air, P, cpw),
            "Me_poppe": pp["Me"], "T_air_out": pp["T_air_out"], "W_out": pp["W_out"], "RH_out": pp["RH_out"],
            "h_out": pp["h_out"], "supersaturated_out": pp["supersaturated_out"],
            "evap_kg_s": pp["evap_per_kg_air"] * G, "evap_pct": 100 * pp["evap_frac"],
            "evap_rule_pct": 100 * cpw * b.range / ps.HFG0 * 0.85,      # ~85 % of heat leaves as latent
            "energy_balance_err": pp["energy_balance_err"],
            "plume_visible": plume_visible(out_air, air, P),
            "air_in": air, "warnings": warnings, "_char": ch, "_poppe_profile": pp["profile"]}


def run(b: Basis) -> dict:
    s = b.spec
    lib = load_library()
    depths = [s["tower"]["fill_depth_m"]] if s["tower"]["fill_depth_m"] else list(s["grid"]["fill_depth_m"])
    pts = [design_point(b, d, lib) for d in depths]
    ok = [p for p in pts if p["feasible"]]
    if not ok:
        return {"feasible": False, "points": pts}
    # Phase 1 pick: the shallowest depth whose design L/G lies inside the fill data range. Phase 2
    # replaces this with the cost optimiser over depth, plan area and fan.
    inside = [p for p in ok if not any("outside the" in w and "fill data" in w for w in p["warnings"])]
    sel = (inside or ok)[0] if not s["tower"]["fill_depth_m"] else ok[0]
    ch, air, P = sel["_char"], sel["air_in"], b.P_atm

    LGd, Med = th.demand_curve(b.T_hot, b.T_cold, air["h"], P, cpw=b.cp_w)
    approaches = [b.approach - 1.0, b.approach, b.approach + 1.0]
    family = []
    for app in approaches:
        Tc = b.T_wb + app
        if app > 0.5:
            lg, me = th.demand_curve(Tc + b.range, Tc, air["h"], P, cpw=b.cp_w)
            family.append({"approach": app, "LG": lg, "Me": me})

    ratings = []
    for rc in s["rating_cases"]:
        wb = rc.get("wet_bulb_C", b.T_wb)
        db = None if b.T_db is None else max(wb, b.T_db + wb - b.T_wb)
        a = ps.air_state(db, wb, P)
        r = th.rate(ch, sel["LG"] * rc.get("flow_factor", 1.0), a, P,
                    range_C=rc.get("range_C", b.range), cpw=b.cp_w)
        ratings.append({"label": rc.get("label", ""), "T_wb": wb, **r})

    wb_list = list(np.arange(round(b.T_wb) - 8, round(b.T_wb) + 4.01, 1.0))
    perf = th.performance_curves(ch, sel["LG"], b.range, air, P, wb_list, cpw=b.cp_w)
    design_check = th.rate(ch, sel["LG"], air, P, range_C=b.range, cpw=b.cp_w)
    return {"feasible": True, "points": pts, "selected": sel, "demand": {"LG": LGd, "Me": Med},
            "demand_family": family, "LG_max": th.LG_max(b.T_hot, b.T_cold, air["h"], P, b.cp_w),
            "ratings": ratings, "performance": perf, "design_check": design_check}
