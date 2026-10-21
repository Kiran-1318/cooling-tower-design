"""ASCE 7 loads for the FRP tower frame: wind (Ch. 29 other structures), seismic (ELF, Ch. 12/15),
and LRFD load combinations tagged with the ASCE/SEI 74 time-effect factor lambda.

Wind   q_z = 0.613 K_z K_zt K_d K_e V^2 (Pa, V in m/s);  F = q_z G C_f A_f
       K_z = 2.01 (z/z_g)^(2/alpha), z >= 4.6 m; alpha, z_g per ASCE 7-16 Table 26.11-1
       K_e = exp(-0.000119 z_e) (ground elevation); G = 0.85 (rigid); C_f = 1.3 for a square prism with
       h/D <= 1 rising to 1.4 at h/D = 7 (Fig. 29.4-1), applied over the full projected face.
Seismic  S_DS = 2/3 F_a S_s, S_D1 = 2/3 F_v S_1 (F_a, F_v: ASCE 7-16 Tables 11.4-1/2) unless S_DS/S_D1
       are given (preferred - use the ASCE Hazard Tool, which also covers ASCE 7-22);
       R = C_d = Omega_0 = 2 for an "ordinary braced cooling tower" (ASCE/SEI 74 Table 9.1.2);
       C_s = S_DS Ie / R, <= S_D1 Ie/(T R) for T <= T_L, >= max(0.044 S_DS Ie, 0.01); T_a = 0.0488 h^0.75;
       ASCE 7 12.8.1.3 does not apply (ASCE 74). Vertical E_v = 0.2 S_DS D.
"""
from __future__ import annotations

import math

import numpy as np

EXPOSURE = {"B": (7.0, 365.76), "C": (9.5, 274.32), "D": (11.5, 213.36)}     # alpha, z_g (m), ASCE 7-16

FA = {"A": [0.8] * 6, "B": [0.9] * 6, "C": [1.3, 1.3, 1.2, 1.2, 1.2, 1.2], "D": [1.6, 1.4, 1.2, 1.1, 1.0, 1.0]}
FA_SS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
FV = {"A": [0.8] * 6, "B": [0.8] * 6, "C": [1.5, 1.5, 1.5, 1.5, 1.5, 1.4], "D": [2.4, 2.2, 2.0, 1.9, 1.8, 1.7]}
FV_S1 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]


def Kz(z: float, exposure: str) -> float:
    a, zg = EXPOSURE[exposure]
    return 2.01 * (max(z, 4.6) / zg) ** (2 / a)


def qz(z: float, V: float, exposure: str, Kd: float = 0.90, Kzt: float = 1.0, z_ground: float = 0.0) -> float:
    Ke = math.exp(-0.000119 * z_ground)
    return 0.613 * Kz(z, exposure) * Kzt * Kd * Ke * V * V


def Cf_square(h_over_D: float) -> float:
    return float(np.interp(h_over_D, [1.0, 7.0, 25.0], [1.3, 1.4, 2.0]))


def seismic_coefficients(seis: dict, height_m: float) -> dict:
    sc = seis.get("site_class", "D")
    if seis.get("SDS") is not None and seis.get("SD1") is not None:
        SDS, SD1, src = seis["SDS"], seis["SD1"], "given"
    else:
        if sc not in FA:
            raise ValueError(f"site class {sc}: give SDS and SD1 directly (site-specific per ASCE 7 11.4.8)")
        Fa = float(np.interp(seis["Ss"], FA_SS, FA[sc]))
        Fv = float(np.interp(seis["S1"], FV_S1, FV[sc]))
        SDS, SD1, src = 2 / 3 * Fa * seis["Ss"], 2 / 3 * Fv * seis["S1"], f"ASCE 7-16 Fa {Fa:.2f}, Fv {Fv:.2f}"
    R, Ie, TL = seis.get("R", 2.0), seis.get("Ie", 1.0), seis.get("TL", 8.0)
    T = 0.0488 * height_m ** 0.75
    Cs = SDS * Ie / R
    Cs = min(Cs, SD1 * Ie / (T * R) if T <= TL else SD1 * TL * Ie / (T * T * R))
    Cs = max(Cs, 0.044 * SDS * Ie, 0.01)
    return {"SDS": SDS, "SD1": SD1, "source": src, "R": R, "Cd": seis.get("Cd", 2.0), "Omega0": seis.get("Omega0", 2.0),
            "Ie": Ie, "T": T, "Cs": Cs, "k": 1.0 if T <= 0.5 else (2.0 if T >= 2.5 else 1 + (T - 0.5) / 2)}


def vertical_distribution(V: float, levels: list[tuple[float, float]], k: float) -> list[float]:
    """F_x = C_vx V, C_vx = w_x h_x^k / sum(w h^k). levels: (height above base, weight)."""
    s = sum(w * h ** k for h, w in levels)
    return [V * w * h ** k / s for h, w in levels]


def combos(SDS: float) -> list[dict]:
    """LRFD combinations (ASCE 7-16 2.3, fluid F with the dead-load factor) with ASCE 74 lambda.
    W and E are applied separately in X (along the row) and Z (across)."""
    ev = 0.2 * SDS
    c = [{"name": "1.4(D+F)", "f": {"D": 1.4, "F": 1.4}, "lam": 0.4},
         {"name": "1.2(D+F)+1.6L+0.5S", "f": {"D": 1.2, "F": 1.2, "L": 1.6, "S": 0.5}, "lam": 0.8},
         {"name": "1.2(D+F)+1.6S+L", "f": {"D": 1.2, "F": 1.2, "S": 1.6, "L": 1.0}, "lam": 0.75}]
    for d in ("X", "Z"):
        c += [{"name": f"1.2(D+F)+1.6S+0.5W{d}", "f": {"D": 1.2, "F": 1.2, "S": 1.6, f"W{d}": 0.5}, "lam": 0.75},
              {"name": f"1.2(D+F)+W{d}+L+0.5S", "f": {"D": 1.2, "F": 1.2, f"W{d}": 1.0, "L": 1.0, "S": 0.5}, "lam": 1.0},
              {"name": f"0.9D+W{d}", "f": {"D": 0.9, f"W{d}": 1.0}, "lam": 1.0},
              {"name": f"(1.2+Ev)(D+F)+E{d}+L", "f": {"D": 1.2 + ev, "F": 1.2 + ev, f"E{d}": 1.0, "L": 1.0}, "lam": 1.0},
              {"name": f"(0.9-Ev)D+E{d}", "f": {"D": 0.9 - ev, f"E{d}": 1.0}, "lam": 1.0}]
    return c


SERVICE = [{"name": "SLS D+F+L", "f": {"D": 1.0, "F": 1.0, "L": 1.0}},
           {"name": "SLS D+F+0.6WX", "f": {"D": 1.0, "F": 1.0, "WX": 0.6}},
           {"name": "SLS D+F+0.6WZ", "f": {"D": 1.0, "F": 1.0, "WZ": 0.6}}]
