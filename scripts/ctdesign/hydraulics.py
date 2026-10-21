"""Water distribution of one cell: nozzle grid, nozzle orifice, header, laterals, riser, pump head.

Layout: the riser rises outside the air-inlet face (y = 0) and feeds a header running across the
cell (along y, length W); laterals branch both ways along x (length L/2 each) carrying nozzles on a
square grid of pitch ~tower.nozzle_pitch_m. Pipes are sized by velocity limits from nominal
FRP/HDPE sizes (ID taken as DN). Friction uses the Colebrook factor from `fluids`; for a
manifold with uniform outflow along its length the loss is 1/3 of the full-flow value.
The tower pump head = lift from basin level to the nozzle + nozzle pressure + pipe losses.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from CoolProp.CoolProp import PropsSI
from fluids.friction import friction_factor

DN_MM = [50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900, 1000, 1100,
         1200, 1400, 1600]
ORIFICE_MM = [19, 22, 25, 29, 32, 35, 38, 41, 44, 48, 51, 57, 64, 70, 76]
G = 9.81


@lru_cache(maxsize=64)
def water_props(T_C: float, P: float) -> tuple[float, float]:
    return (PropsSI("D", "T", T_C + 273.15, "P", P, "Water"), PropsSI("V", "T", T_C + 273.15, "P", P, "Water"))


def pick_dn(Q, v_max):
    for dn in DN_MM:
        if Q / (math.pi / 4 * (dn / 1e3) ** 2) <= v_max:
            return dn
    return DN_MM[-1]


def pipe_dp(Q, dn, length, rho, mu, rough_mm, K=0.0, manifold=False):
    D = dn / 1e3
    v = Q / (math.pi / 4 * D ** 2)
    Re = rho * v * D / mu
    f = friction_factor(Re=Re, eD=rough_mm / 1e3 / D)
    dp = (f * length / D * (1 / 3 if manifold else 1.0) + K) * rho * v * v / 2
    return dp, v


def nozzle_grid(L, W, pitch):
    n_lat = max(1, round(W / pitch))                  # laterals across the header (along y)
    n_half = max(1, round((L / 2) / pitch))           # nozzles per lateral on each side of the header
    ys = (np.arange(n_lat) + 0.5) * W / n_lat
    xs = np.concatenate([L / 2 - (np.arange(n_half) + 0.5) * (L / 2) / n_half,
                         L / 2 + (np.arange(n_half) + 0.5) * (L / 2) / n_half])
    pts = [(float(x), float(y)) for y in ys for x in sorted(xs)]
    return n_lat, n_half, pts


def design(geom, b, s: dict, z_nozzle: float | None = None) -> dict:
    ws, t, lim = s["water_system"], s["tower"], s["limits"]
    rho, mu = water_props(b.T_hot, b.P_atm)
    Qc = b.V_w / 3600.0 / geom.cells                   # m3/s per cell
    n_lat, n_half, pts = nozzle_grid(geom.L, geom.W, t["nozzle_pitch_m"])
    n_noz = len(pts)
    q = Qc / n_noz
    pmin, pmax = (p * 1e3 for p in lim["nozzle_pressure_kPa"])
    orifice, dp_noz = None, None
    for d in reversed(ORIFICE_MM):                    # largest orifice (least clogging) above the minimum pressure
        A = math.pi / 4 * (d / 1e3) ** 2
        dp = rho / 2 * (q / (ws["nozzle_Cd"] * A)) ** 2
        if dp >= pmin:
            orifice, dp_noz = d, dp
            break
    if orifice is None:                               # even the smallest orifice is below p_min
        orifice = ORIFICE_MM[0]
        dp_noz = rho / 2 * (q / (ws["nozzle_Cd"] * math.pi / 4 * (orifice / 1e3) ** 2)) ** 2

    dn_h = pick_dn(Qc, ws["header_velocity_max_m_s"])
    q_lat = Qc / (2 * n_lat)
    dn_l = pick_dn(q_lat, ws["lateral_velocity_max_m_s"])
    dn_r = pick_dn(Qc, ws["riser_velocity_max_m_s"])
    rough = ws["pipe_roughness_mm"]
    dp_h, v_h = pipe_dp(Qc, dn_h, geom.W, rho, mu, rough, manifold=True)
    dp_l, v_l = pipe_dp(q_lat, dn_l, geom.L / 2, rho, mu, rough, K=0.5, manifold=True)   # K: tee branch
    zn = geom.z["nozzle"] if z_nozzle is None else z_nozzle
    riser_len = geom.z["header_cl"] + 3.0                  # from below basin level + horizontal run-in
    dp_r, v_r = pipe_dp(Qc, dn_r, riser_len, rho, mu, rough, K=0.3 * 2 + 0.3 + 1.0)    # 2 elbows, valve, tee
    head = zn + (dp_noz + dp_h + dp_l + dp_r) / (rho * G)
    p_inlet = rho * G * (head - geom.z["header_cl"])      # gauge pressure at the header inlet flange
    pump_kW = rho * G * head * b.V_w / 3600.0 / s["costs"]["pump_efficiency"] / 1e3
    viol = []
    if not pmin <= dp_noz <= pmax:
        viol.append(f"nozzle pressure {dp_noz / 1e3:.0f} kPa outside {pmin / 1e3:.0f}-{pmax / 1e3:.0f}")
    pipe_vol = geom.cells * (math.pi / 4 * ((dn_h / 1e3) ** 2 * geom.W + 2 * n_lat * (dn_l / 1e3) ** 2 * geom.L / 2
                                            + (dn_r / 1e3) ** 2 * riser_len))
    return {"rho": rho, "Q_cell_m3_h": Qc * 3600, "nozzles_per_cell": n_noz, "laterals_per_cell": 2 * n_lat,
            "nozzles_per_lateral": n_half, "q_nozzle_m3_h": q * 3600, "orifice_mm": orifice,
            "dp_nozzle_kPa": dp_noz / 1e3, "header_DN": dn_h, "lateral_DN": dn_l, "riser_DN": dn_r,
            "v_header": v_h, "v_lateral": v_l, "v_riser": v_r,
            "dp_header_kPa": dp_h / 1e3, "dp_lateral_kPa": dp_l / 1e3, "dp_riser_kPa": dp_r / 1e3,
            "pump_head_m": head, "inlet_pressure_kPa": p_inlet / 1e3, "pump_kW": pump_kW,
            "pipe_volume_m3": pipe_vol, "nozzle_xy": pts, "violations": viol}
