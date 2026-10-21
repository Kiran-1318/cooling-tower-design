"""Air-side pressure-loss build-up for one cell (induced draft, counterflow).

Each loss is K x (rho v^2 / 2) at the local velocity and density:
  inlet (+ louvers)   inlet face velocity, ambient density
  rain zone, fill     fill face velocity, mean density in the fill
  spray, eliminator   plan velocity, exit-air density
  plenum + fan inlet  fan annulus velocity, exit-air density
The fill loss coefficient comes from the fill library; the others are GENERIC defaults in
spec.airside and are reported as such. A small natural-draft (buoyancy) credit is taken for
the warm, light air column between the fill top and the stack top.
"""
from __future__ import annotations

import math

G = 9.81


def losses(geom, flows: dict, ch, s: dict) -> dict:
    """flows: Q_in, Q_mean, Q_out (m3/s per cell), rho_in, rho_mean, rho_out, Gw, Ga (kg/m2s)."""
    a, t = s["airside"], s["tower"]
    A_cell = geom.cell_area
    from .geometry import inlet_perimeter
    A_in = inlet_perimeter(geom.L, geom.W, t["air_inlets"]) * geom.H_inlet
    D, hub = geom.fan_D, s["fan"]["hub_ratio"]
    A_fan = math.pi / 4 * D ** 2 * (1 - hub ** 2)
    v_in, v_fill = flows["Q_in"] / A_in, flows["Q_mean"] / A_cell
    v_plan_out, v_fan = flows["Q_out"] / A_cell, flows["Q_out"] / A_fan
    ri, rm, ro = flows["rho_in"], flows["rho_mean"], flows["rho_out"]

    items = [("air inlet", a["K_inlet"] + (a["K_louver"] if t["inlet_louvers"] else 0.0), v_in, ri),
             ("rain zone", a["K_rain_per_m"] * geom.H_rain, v_fill, rm),
             ("fill supports", a["K_fill_support"], v_fill, rm),
             ("fill", ch.K_fill(flows["Gw"], flows["Ga"]), v_fill, rm),
             ("spray zone + distribution", a["K_spray"], v_plan_out, ro),
             ("drift eliminator", a["K_eliminator"][t["drift_eliminator"]], v_plan_out, ro),
             ("plenum + fan inlet", a["K_plenum"], v_fan, ro)]
    rows = [{"item": n, "K": K, "v": v, "rho": r, "dP": K * r * v * v / 2} for n, K, v, r in items]
    buoy = max(0.0, (ri - ro) * G * (geom.z["stack_top"] - geom.z["fill_top"]))
    dP_static = sum(r["dP"] for r in rows) - buoy
    return {"rows": rows, "buoyancy_credit": buoy, "dP_static_system": dP_static,
            "v_inlet": v_in, "v_fill": v_fill, "v_eliminator": v_plan_out, "v_fan": v_fan,
            "A_inlet": A_in, "A_fan": A_fan}
