"""Moist-air psychrometrics, vectorised with numpy (ASHRAE Fundamentals, ideal-gas mixture).

Saturation pressure uses the Hyland-Wexler equations (ASHRAE 2017, ch. 1, eqs. 5-6); enthalpy is
per kg of dry air with 0 degC dry air and 0 degC liquid water as datum, which is the basis of the
CTI/Merkel enthalpy-driving-force method. Tests check these against CoolProp's real-gas HAPropsSI
and PsychroLib. Temperatures in degC, pressures in Pa, enthalpies in J/kg dry air, W in kg/kg.
"""
from __future__ import annotations

import numpy as np

K = 273.15
CPA = 1006.0         # J/kgK dry air
CPV = 1860.0         # J/kgK water vapour
HFG0 = 2.501e6       # J/kg latent heat at 0 degC
CPW = 4186.0         # J/kgK liquid water (fog/mist term and Poppe vapour datum)
EPS = 0.621945       # Mw/Ma
R_DA = 287.042       # J/kgK dry air


def p_ws(T):
    """Saturation vapour pressure (Pa) over liquid water (T >= 0 degC) or ice (T < 0 degC)."""
    T = np.asarray(T, dtype=float)
    Tk = T + K
    liq = np.exp(-5.8002206e3 / Tk + 1.3914993 - 4.8640239e-2 * Tk + 4.1764768e-5 * Tk ** 2
                 - 1.4452093e-8 * Tk ** 3 + 6.5459673 * np.log(Tk))
    ice = np.exp(-5.6745359e3 / Tk + 6.3925247 - 9.677843e-3 * Tk + 6.2215701e-7 * Tk ** 2
                 + 2.0747825e-9 * Tk ** 3 - 9.484024e-13 * Tk ** 4 + 4.1635019 * np.log(Tk))
    return np.where(T >= 0.0, liq, ice)


def W_from_pw(pw, P):
    return EPS * pw / (P - pw)


def W_sat(T, P):
    return W_from_pw(p_ws(T), P)


def h_moist(T, W):
    """Enthalpy of unsaturated moist air, J/kg dry air."""
    return CPA * np.asarray(T) + np.asarray(W) * (HFG0 + CPV * np.asarray(T))


def h_sat(T, P):
    """Enthalpy of saturated air at T (the Merkel driving potential at the water temperature)."""
    return h_moist(T, W_sat(T, P))


def W_from_wb(T_db, T_wb, P):
    """Humidity ratio from dry- and wet-bulb (ASHRAE eq. 33, T_wb above freezing)."""
    Ws = W_sat(T_wb, P)
    return ((HFG0 - 2326.0 * T_wb) * Ws - CPA * (T_db - T_wb)) / (HFG0 + CPV * T_db - CPW * T_wb)


def T_wb_from_W(T_db, W, P, tol=1e-6):
    """Wet-bulb by bisection (scalar)."""
    lo, hi = -20.0, float(T_db)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if W_from_wb(T_db, mid, P) > W:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def RH(T, W, P):
    pw = np.asarray(W) * P / (EPS + np.asarray(W))
    return pw / p_ws(T)


def rho_moist(T, W, P):
    """Density of moist air, kg (dry air + vapour) per m3."""
    return P / (R_DA * (np.asarray(T) + K) * (1.0 + 1.607858 * np.asarray(W))) * (1.0 + np.asarray(W))


def v_moist(T, W, P):
    """Specific volume, m3 per kg dry air."""
    return R_DA * (np.asarray(T) + K) * (1.0 + 1.607858 * np.asarray(W)) / P


def T_from_h_W(h, W, P):
    """Air temperature from enthalpy and humidity ratio, including the supersaturated (fog) region.

    Unsaturated: h = cpa T + W (hfg0 + cpv T). Supersaturated: the vapour is capped at W_sat(T) and the
    excess is liquid fog, h = cpa T + Ws (hfg0 + cpv T) + (W - Ws) cpw T (Kloppers & Kroger 2005).
    Returns (T, supersaturated_flag).
    """
    T_u = (h - HFG0 * W) / (CPA + CPV * W)
    if W <= W_sat(T_u, P):
        return float(T_u), False
    # fog: treating the liquid as vapour charges it with latent heat, so T_u is BELOW the true T;
    # the root lies between T_u and the dew point (hm is monotonic in T)
    lo, hi = float(T_u), float(T_u) + 50.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        Ws = W_sat(mid, P)
        hm = CPA * mid + Ws * (HFG0 + CPV * mid) + (W - Ws) * CPW * mid
        if hm > h:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-7:
            break
    return 0.5 * (lo + hi), True


def air_state(T_db, T_wb, P):
    """Inlet air state from dry/wet bulb; T_db None means saturated at the wet-bulb (Merkel convention)."""
    if T_db is None:
        T_db = T_wb
    W = float(W_from_wb(T_db, T_wb, P))
    return {"T_db": float(T_db), "T_wb": float(T_wb), "W": W, "h": float(h_moist(T_db, W)),
            "RH": float(RH(T_db, W, P)), "rho": float(rho_moist(T_db, W, P)), "v": float(v_moist(T_db, W, P))}
