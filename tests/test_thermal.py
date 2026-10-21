"""Validation of psychrometrics, Merkel, Poppe, fill characteristic and rating.

References used as independent checks:
  * CoolProp HAPropsSI (real-gas moist air, Hyland-Wexler with enhancement factor)
  * PsychroLib (ASHRAE Fundamentals, ideal-gas) - should match psychro.py almost exactly
  * scipy.integrate.quad over CoolProp enthalpies for the Merkel integral
  * Vitkovic & Dvorak (2016), MCM'16 HTFF 127, for the published grid-fill and rain-zone fits
"""
import sys
from pathlib import Path

import numpy as np
import psychrolib
import pytest
from CoolProp.HumidAirProp import HAPropsSI
from scipy.integrate import quad

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import psychro as ps, thermal as th, fill, thermal_design, spec  # noqa: E402

P = 101325.0
psychrolib.SetUnitSystem(psychrolib.SI)


def cp_h_sat(T, P=P):
    """CoolProp saturated-air enthalpy on the 0 degC dry-air / liquid-water datum (J/kg dry air)."""
    return HAPropsSI("H", "T", T + 273.15, "P", P, "R", 1.0) - HAPropsSI("H", "T", 273.15, "P", P, "W", 0.0)


# ------------------------------------------------------------------ psychrometrics
@pytest.mark.parametrize("T", [5.0, 15.0, 25.0, 35.0, 45.0, 55.0])
def test_psychro_vs_psychrolib(T):
    assert ps.p_ws(T) == pytest.approx(psychrolib.GetSatVapPres(T), rel=1e-6)
    assert ps.W_from_wb(T + 8, T, P) == pytest.approx(psychrolib.GetHumRatioFromTWetBulb(T + 8, T, P), rel=1e-4)
    W = 0.012
    assert ps.h_moist(T, W) == pytest.approx(psychrolib.GetMoistAirEnthalpy(T, W), rel=1e-3)
    assert ps.v_moist(T, W, P) == pytest.approx(psychrolib.GetMoistAirVolume(T, W, P), rel=1e-4)


@pytest.mark.parametrize("T", [10.0, 25.0, 40.0, 50.0])
def test_h_sat_vs_coolprop(T):
    # ideal-gas (ASHRAE/PsychroLib basis) vs real-gas with enhancement factor: the gap grows with
    # temperature, ~0.4 % in h and ~0.6 % in W at 50 C
    assert ps.h_sat(T, P) == pytest.approx(cp_h_sat(T), rel=5e-3)
    assert ps.W_sat(T, P) == pytest.approx(HAPropsSI("W", "T", T + 273.15, "P", P, "R", 1.0), rel=1e-2)


def test_wet_bulb_roundtrip_and_fog_temperature():
    W = ps.W_from_wb(35.0, 26.0, P)
    assert ps.T_wb_from_W(35.0, W, P) == pytest.approx(26.0, abs=1e-4)
    T, sat = ps.T_from_h_W(float(ps.h_moist(30.0, 0.010)), 0.010, P)
    assert not sat and T == pytest.approx(30.0, abs=1e-9)
    Ws = float(ps.W_sat(20.0, P))
    h_fog = ps.CPA * 20 + Ws * (ps.HFG0 + ps.CPV * 20) + 0.003 * ps.CPW * 20
    T, sat = ps.T_from_h_W(h_fog, Ws + 0.003, P)
    assert sat and T == pytest.approx(20.0, abs=1e-4)


# ------------------------------------------------------------------ Merkel
@pytest.mark.parametrize("Th,Tc,wb,LG", [(32, 27.5, 24.5, 1.0), (43, 33, 29, 1.2), (40, 30, 22, 1.5), (35, 29, 25, 0.8)])
def test_merkel_vs_independent_quad(Th, Tc, wb, LG):
    h_in = cp_h_sat(wb)
    ref = quad(lambda T: ps.CPW / (cp_h_sat(T) - (h_in + LG * ps.CPW * (T - Tc))), Tc, Th, epsabs=1e-10)[0]
    a = ps.air_state(None, wb, P)
    assert th.merkel(Th, Tc, LG, a["h"], P) == pytest.approx(ref, rel=0.015)


def test_chebyshev_close_to_exact_for_normal_ranges():
    a = ps.air_state(None, 24.0, P)
    for Th, Tc in [(32, 27), (38, 28), (40, 29)]:
        ex = th.merkel(Th, Tc, 1.0, a["h"], P)
        assert th.merkel(Th, Tc, 1.0, a["h"], P, method="chebyshev") == pytest.approx(ex, rel=0.01)


def test_LG_max_pinch():
    a = ps.air_state(None, 24.0, P)
    lgmax = th.LG_max(32, 27, a["h"], P)
    assert np.isfinite(th.merkel(32, 27, 0.99 * lgmax, a["h"], P))
    assert th.merkel(32, 27, 1.02 * lgmax, a["h"], P) == np.inf
    assert th.merkel(32, 27, 0.99 * lgmax, a["h"], P) > 3 * th.merkel(32, 27, 0.5 * lgmax, a["h"], P)


# ------------------------------------------------------------------ Poppe
@pytest.mark.parametrize("db,wb,LG", [(None, 24.0, 1.0), (32.0, 24.0, 1.2), (40.0, 28.0, 0.9), (12.0, 8.0, 1.5)])
def test_poppe_conservation(db, wb, LG):
    a = ps.air_state(db, wb, P)
    r = th.poppe(38, 30, LG, a, P)
    assert abs(r["energy_balance_err"]) < 1e-6
    assert r["W_out"] > a["W"] and r["h_out"] > a["h"]
    # evaporation is close to the latent-equivalent of the duty (more with hot dry air, less with cold air)
    latent_equiv = ps.CPW * 8 / ps.HFG0
    assert 0.6 * latent_equiv < r["evap_frac"] < 1.4 * latent_equiv


def test_poppe_cold_air_goes_supersaturated():
    # winter, small L/G: exit air is fogged - this is the plume case Merkel cannot see
    r = th.poppe(30, 20, 1.6, ps.air_state(5.0, 4.0, P), P)
    assert r["supersaturated_out"]
    assert abs(r["energy_balance_err"]) < 1e-6


def test_poppe_vs_merkel_ordering():
    # Kloppers & Kroger (2005): Poppe Merkel numbers exceed Merkel's for the same duty
    a = ps.air_state(None, 24.0, P)
    for LG in (0.8, 1.0, 1.4):
        assert th.poppe(36, 28, LG, a, P)["Me"] > th.merkel(36, 28, LG, a["h"], P)


def test_lewis_factor_limits():
    assert th.lewis_factor(0.02, 0.02) == pytest.approx(0.865 ** 0.667)
    assert 0.9 < th.lewis_factor(0.04, 0.015) < 0.95


# ------------------------------------------------------------------ fill and zones
def test_published_grid_fill_and_rain_zone_reproduce_paper():
    lib = fill.load_library()
    ch = fill.characteristic({"fill_type": "splash_grid"}, depth=1.32, H_rain=1.98, library=lib)
    assert ch.Me_fill(1.5) == pytest.approx(0.3672 * 1.5 ** -0.2794 * 1.32 ** 0.7, rel=1e-9)
    assert ch.Me_rain(1.5) == pytest.approx(0.066 * 1.5 ** -0.3684 * 1.98, rel=1e-9)
    # paper Fig. 4: rain zone of 1.98 m at L/G 1.5 is ~0.12-0.13
    assert 0.11 < ch.Me_rain(1.5) < 0.14


def test_vendor_override_replaces_generic():
    ch = fill.characteristic({"fill_type": "film", "fill_override": {"C": 2.0, "n": 0.7, "m": 1.0}}, 1.2, 0.0)
    assert ch(1.0) == pytest.approx(2.4)
    assert ch.fill["basis"].startswith("VENDOR")
    assert not any("GENERIC" in w for w in ch.check(1.0, 35.0))


def test_fill_warnings():
    ch = fill.characteristic({"fill_type": "film"}, 3.0, 2.0)
    w = " | ".join(ch.check(2.5, 55.0, loading_m3_h_m2=30))
    for frag in ("fill data range", "fill depth", "fill limit", "water loading", "GENERIC"):
        assert frag in w


# ------------------------------------------------------------------ rating and design point
def _basis():
    return spec.load({"site": {"design_wet_bulb_C": 25.0, "design_dry_bulb_C": 33.0},
                      "duty": {"water_flow_m3_h": 2000.0, "hot_water_C": 38.0, "cold_water_C": 30.0},
                      "tower": {"fill_depth_m": 1.2, "air_inlet_height_m": 2.0}})


def test_design_point_rates_back_to_design():
    b = _basis()
    p = thermal_design.design_point(b, 1.2)
    r = th.rate(p["_char"], p["LG"], p["air_in"], b.P_atm, range_C=b.range, cpw=b.cp_w)
    assert r["T_cold"] == pytest.approx(b.T_cold, abs=0.01)
    assert p["capability_pct"] == pytest.approx(100.0, abs=0.1)
    assert abs(p["energy_balance_err"]) < 1e-6


def test_capability_margin():
    b = _basis()
    b.spec["limits"]["thermal_capability_min_pct"] = 110.0
    p = thermal_design.design_point(b, 1.2)
    assert p["capability_pct"] == pytest.approx(110.0, abs=0.2)
    r = th.rate(p["_char"], p["LG"], p["air_in"], b.P_atm, range_C=b.range, cpw=b.cp_w)
    assert r["T_cold"] < b.T_cold - 0.1                                 # oversized tower beats the target


def test_rating_trends():
    b = _basis()
    p = thermal_design.design_point(b, 1.2)
    ch, LG = p["_char"], p["LG"]
    base = th.rate(ch, LG, ps.air_state(None, 25.0, P), P, range_C=8.0)["T_cold"]
    assert th.rate(ch, LG, ps.air_state(None, 27.0, P), P, range_C=8.0)["T_cold"] > base       # warmer WB
    assert th.rate(ch, 1.1 * LG, ps.air_state(None, 25.0, P), P, range_C=8.0)["T_cold"] > base  # more water
    assert th.rate(ch, LG, ps.air_state(None, 25.0, P), P, range_C=9.6)["T_cold"] > base       # more load
    # approach shrinks as wet-bulb rises (same range), the classic CTI curve shape
    a_lo = th.rate(ch, LG, ps.air_state(None, 20.0, P), P, range_C=8.0)["approach"]
    a_hi = th.rate(ch, LG, ps.air_state(None, 28.0, P), P, range_C=8.0)["approach"]
    assert a_hi < a_lo
