"""Cold-water basin, pump sump (ANSI/HI 9.8 submergence) and basin connections.

Basin plan = tower plan (all cells over one basin). Operating water depth holds the retention
volume (limits.basin_retention_min of circulating flow), and the freeboard to the curb holds the
drain-down (distribution pipework + water held on the fill + water in flight) when pumps stop.
"""
from __future__ import annotations

import math

from .hydraulics import DN_MM

G = 9.81
FILL_DRAIN_M3_PER_M3 = 0.03     # water held as film on wetted film fill at shutdown (estimate)
FALL_TIME_S = 5.0               # water in flight through spray + fill + rain zones (estimate)


def _dn_for(Q_m3_h, v):
    Q = Q_m3_h / 3600.0
    return next((d for d in DN_MM if Q / (math.pi / 4 * (d / 1e3) ** 2) <= v), DN_MM[-1])


def design(geom, b, hyd: dict, wb: dict, s: dict) -> dict:
    ws, lim = s["water_system"], s["limits"]
    A = geom.plan_area
    V_ret = b.V_w * lim["basin_retention_min"] / 60.0
    h_w = max(ws["basin_min_water_depth_m"], V_ret / A)
    drain = hyd["pipe_volume_m3"] + FILL_DRAIN_M3_PER_M3 * A * geom.depth + b.V_w / 3600.0 * FALL_TIME_S
    free = max(ws["basin_freeboard_min_m"], drain / A + 0.1, geom.z["curb"])
    depth = h_w + free
    notes = []
    if s["tower"].get("basin_depth_m"):
        if s["tower"]["basin_depth_m"] < depth - 1e-6:
            notes.append(f"specified basin depth {s['tower']['basin_depth_m']} m is less than the "
                         f"{depth:.2f} m needed for retention + drain-down")
        depth = float(s["tower"]["basin_depth_m"])
        h_w = depth - free

    n = ws["pumps_duty"]
    Qp = b.V_w / 3600.0 / n
    D_bell = math.sqrt(4 * Qp / (math.pi * 1.7))         # HI 9.8 recommended bell velocity ~1.7 m/s
    Fr = 1.7 / math.sqrt(G * D_bell)
    S = D_bell * (1 + 2.3 * Fr)                          # HI 9.8 minimum submergence
    C = 0.5 * D_bell                                     # bell to floor clearance
    sump_floor = -(S + C)                                # relative to operating water level
    pit = sump_floor < -h_w
    return {"plan_L": geom.cells * geom.L, "plan_W": geom.W, "area_m2": A, "retention_volume_m3": V_ret,
            "water_depth_m": h_w, "freeboard_m": free, "depth_m": depth, "drain_down_m3": drain,
            "volume_operating_m3": A * h_w, "pumps_duty": n, "pumps_standby": ws["pumps_standby"],
            "pump_flow_m3_h": Qp * 3600, "bell_D_m": D_bell, "submergence_m": S,
            "sump_floor_below_water_m": S + C, "sump_pit": pit,
            "sump_pit_depth_below_basin_m": max(0.0, S + C - h_w), "sump_bay_width_m": 2 * D_bell,
            "sump_bay_length_m": 5 * D_bell,
            "connections": {"makeup_DN": _dn_for(wb["makeup_perry_m3_h"] * 1.5, 1.5),
                            "overflow_DN": _dn_for(wb["makeup_perry_m3_h"] * 1.5, 1.0),
                            "blowdown_DN": _dn_for(max(wb["blowdown_perry_m3_h"], 1.0), 1.5),
                            "drain_DN": _dn_for(A * depth / ws["drain_time_h"], 1.5)},
            "notes": notes}
