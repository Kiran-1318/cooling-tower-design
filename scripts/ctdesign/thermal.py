"""Counterflow tower thermal models: Merkel (CTI) and Poppe (Kloppers & Kroger 2005).

Merkel number   Me = KaV/L = integral_{Tc}^{Th} cpw dTw / (h_sat(Tw) - h_a(Tw)),
air operating line h_a = h_in + (L/G) cpw (Tw - Tc)  (no evaporation loss, Lewis factor 1).

Poppe keeps the evaporated water and a Bosnjakovic Lewis factor, tracks the air humidity and
switches to the supersaturated (fog) equations when the air reaches saturation. It gives the
exit-air state, the evaporation rate and the plume risk, which Merkel cannot.

"Demand" is the Me a duty requires at a given L/G; "supply" is the Me a tower (fill + rain +
spray zones) provides. The design L/G is where they meet; rating finds the cold-water
temperature at which they meet for a fixed tower.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from . import psychro as ps

CHEB = np.array([0.1, 0.4, 0.6, 0.9])
_GL_X, _GL_W = np.polynomial.legendre.leggauss(40)


# ----------------------------------------------------------------------------- Merkel
def merkel(T_hot, T_cold, LG, h_in, P, cpw=ps.CPW, method="gauss"):
    """Merkel number for one or many L/G. Returns inf where the operating line reaches saturation."""
    LG = np.atleast_1d(np.asarray(LG, dtype=float))
    R = T_hot - T_cold
    if method == "chebyshev":
        Tw, wts = T_cold + CHEB * R, np.full(4, R / 4.0)
    else:
        Tw, wts = T_cold + 0.5 * R * (_GL_X + 1.0), 0.5 * R * _GL_W
    dh = ps.h_sat(Tw, P)[None, :] - (h_in + LG[:, None] * cpw * (Tw - T_cold)[None, :])
    Me = np.where((dh > 0).all(axis=1), (cpw * wts[None, :] / np.where(dh > 0, dh, np.nan)).sum(axis=1), np.inf)
    return Me if Me.size > 1 else float(Me[0])


def LG_max(T_hot, T_cold, h_in, P, cpw=ps.CPW):
    """Largest L/G before the Merkel air line touches the saturation curve (Me -> infinity)."""
    Tw = np.linspace(T_cold, T_hot, 400)[1:]
    return float(np.min((ps.h_sat(Tw, P) - h_in) / (cpw * (Tw - T_cold))))


def demand_curve(T_hot, T_cold, h_in, P, LG=None, cpw=ps.CPW):
    lgmax = LG_max(T_hot, T_cold, h_in, P, cpw)
    if LG is None:
        LG = np.linspace(0.3, min(3.0, 0.98 * lgmax), 60)
    return np.asarray(LG), merkel(T_hot, T_cold, LG, h_in, P, cpw)


# ----------------------------------------------------------------------------- Poppe
def lewis_factor(w_sw, w):
    """Bosnjakovic Lewis factor, Lef = 0.865^(2/3) (x - 1)/ln x, x = (w_sw + 0.622)/(w + 0.622)."""
    x = (w_sw + 0.622) / (w + 0.622)
    return 0.865 ** 0.667 * (x - 1.0) / np.log(x) if abs(x - 1.0) > 1e-9 else 0.865 ** 0.667


def _poppe_rhs(Tw, y, mw_ma_in, w_out, P, cpw, lef_fixed):
    w, ima, _ = y
    Ta, sat = ps.T_from_h_W(ima, w, P)
    wsw = float(ps.W_sat(Tw, P))
    imasw = float(ps.h_sat(Tw, P))
    iv = ps.HFG0 + ps.CPV * Tw
    mw_ma = mw_ma_in * (1.0 - (w_out - w) / mw_ma_in)
    if not sat:
        Lef = lef_fixed or lewis_factor(wsw, w)
        den = imasw - ima + (Lef - 1.0) * (imasw - ima - (wsw - w) * iv) - (wsw - w) * cpw * Tw
        dw = cpw * mw_ma * (wsw - w) / den
        dima = mw_ma * cpw * (1.0 + (wsw - w) * cpw * Tw / den)
    else:
        wsa = float(ps.W_sat(Ta, P))
        Lef = lef_fixed or lewis_factor(wsw, wsa)
        den = (imasw - ima + (Lef - 1.0) * (imasw - ima - (wsw - wsa) * iv + (w - wsa) * cpw * Tw)
               + (w - wsa) * cpw * Tw - (wsw - wsa) * cpw * Tw)
        dw = cpw * mw_ma * (wsw - wsa) / den
        dima = mw_ma * cpw * (1.0 + (wsw - wsa) * cpw * Tw / den)
    if den <= 0:
        raise ValueError("Poppe: driving potential vanished (air line reached saturation)")
    return np.array([dw, dima, cpw / den]), sat, Lef


def poppe(T_hot, T_cold, LG, air_in, P, cpw=ps.CPW, n=60, lef=None, tol=1e-8):
    """Poppe integration from the cold (air-inlet) end to the hot end.

    LG is the water-INLET mass flow over dry-air flow. air_in is psychro.air_state(). Returns the
    Poppe Merkel number, exit air, evaporation per kg dry air and the profile along the fill.
    lef=None uses the Bosnjakovic Lewis factor; lef=1.0 reproduces the Lewis-factor-1 limit.
    """
    h = (T_hot - T_cold) / n
    w_out = air_in["W"] + 0.8 * LG * cpw * (T_hot - T_cold) / ps.HFG0         # first guess
    for _ in range(50):
        y = np.array([air_in["W"], air_in["h"], 0.0])
        Tw = T_cold
        prof = [(Tw, *y, *ps.T_from_h_W(y[1], y[0], P), np.nan)]
        for _i in range(n):
            f = lambda T, yy: _poppe_rhs(T, yy, LG, w_out, P, cpw, lef)[0]
            k1 = f(Tw, y); k2 = f(Tw + h / 2, y + h / 2 * k1)
            k3 = f(Tw + h / 2, y + h / 2 * k2); k4 = f(Tw + h, y + h * k3)
            y = y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            Tw += h
            _, sat, Lef = _poppe_rhs(Tw, y, LG, w_out, P, cpw, lef)
            prof.append((Tw, *y, *ps.T_from_h_W(y[1], y[0], P), Lef))
        if abs(y[0] - w_out) < tol:
            break
        w_out = y[0]
    T_out, sat_out = ps.T_from_h_W(y[1], y[0], P)
    evap = y[0] - air_in["W"]                                                   # kg/kg dry air
    mw_out_ma = LG - evap
    Q_air = y[1] - air_in["h"]                                                  # J/kg dry air
    Q_water = LG * cpw * T_hot - mw_out_ma * cpw * T_cold
    return {"Me": float(y[2]), "W_out": float(y[0]), "h_out": float(y[1]), "T_air_out": float(T_out),
            "supersaturated_out": bool(sat_out), "RH_out": float(min(1.0, ps.RH(T_out, y[0], P))),
            "evap_per_kg_air": float(evap), "evap_frac": float(evap / LG),
            "energy_balance_err": float((Q_water - Q_air) / Q_air),
            "profile": np.array(prof, dtype=float)}   # cols: Tw, w, ima, Me, Ta, sat, Lef


def poppe_demand(T_hot, T_cold, LG, air_in, P, cpw=ps.CPW):
    return np.array([poppe(T_hot, T_cold, lg, air_in, P, cpw, n=30)["Me"] for lg in np.atleast_1d(LG)])


# ----------------------------------------------------------------------------- design point and rating
def operating_LG(T_hot, T_cold, h_in, P, supply, cpw=ps.CPW):
    """L/G at which tower supply Me(L/G) equals Merkel demand. supply is a callable of L/G.

    Demand rises with L/G, supply falls, so the root is unique. Returns None if the tower cannot
    reach the duty at any L/G (supply below demand everywhere).
    """
    lgmax = LG_max(T_hot, T_cold, h_in, P, cpw)
    g = lambda lg: supply(lg) - merkel(T_hot, T_cold, lg, h_in, P, cpw)
    lo, hi = 0.05, 0.999 * lgmax
    if g(lo) < 0:
        return None
    return float(brentq(g, lo, hi, xtol=1e-6))


def rate(supply, LG, T_wb_air, P, *, T_hot=None, range_C=None, cpw=ps.CPW):
    """Cold-water temperature of a fixed tower (supply curve) at a given L/G and inlet air.

    Give T_hot (fixed inlet water temperature) or range_C (fixed heat load; T_hot floats).
    T_wb_air is psychro.air_state() for the inlet air.
    """
    Me_s = supply(LG)
    h_in, T_wb = T_wb_air["h"], T_wb_air["T_wb"]

    def resid(Tc):
        Th = T_hot if T_hot is not None else Tc + range_C
        return merkel(Th, Tc, LG, h_in, P, cpw) - Me_s

    lo = T_wb + 1e-3
    hi = (T_hot - 1e-3) if T_hot is not None else T_wb + 40.0
    while not np.isfinite(resid(lo)):
        lo += 0.02
        if lo >= hi:
            raise ValueError("rating: no solution")
    Tc = brentq(resid, lo, hi, xtol=1e-5)
    Th = T_hot if T_hot is not None else Tc + range_C
    return {"T_cold": float(Tc), "T_hot": float(Th), "approach": float(Tc - T_wb), "Me": float(Me_s), "LG": float(LG)}


def capability(supply, LG_design, T_hot, T_cold, air_in, P, cpw=ps.CPW):
    """CTI-style thermal capability (%): water flow the tower can cool to the design cold-water
    temperature at design hot water, wet-bulb and air flow, as a percentage of design flow."""
    def resid(f):
        return supply(f * LG_design) - merkel(T_hot, T_cold, f * LG_design, air_in["h"], P, cpw)
    lgmax = LG_max(T_hot, T_cold, air_in["h"], P, cpw)
    hi = 0.999 * lgmax / LG_design
    if resid(hi) > 0:
        return 100.0 * hi
    return 100.0 * float(brentq(resid, 0.2, hi, xtol=1e-6))


def performance_curves(supply, LG_design, range_design, air_template, P, wb_list,
                       flows=(0.9, 1.0, 1.1), ranges=(0.8, 1.0, 1.2), cpw=ps.CPW):
    """CTI ATC-105 style curves: cold water vs wet-bulb for each flow and range fraction,
    at constant dry-air mass flow (design fan, constant density basis)."""
    from .psychro import air_state
    rows = []
    for fq in flows:
        for fr in ranges:
            for wb in wb_list:
                a = air_state(None, wb, P) if air_template.get("T_db") == air_template.get("T_wb") \
                    else air_state(max(wb, wb + air_template["T_db"] - air_template["T_wb"]), wb, P)
                try:
                    r = rate(supply, LG_design * fq, a, P, range_C=range_design * fr, cpw=cpw)
                    rows.append({"flow_pct": 100 * fq, "range_pct": 100 * fr, "T_wb": wb, **r})
                except ValueError:
                    pass
    return rows
