"""Phase 2: geometry, air side, fan, hydraulics, basin, water balance, optimiser and finalisation."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import spec, sizing, geometry, hydraulics, water_balance, basin, fan  # noqa: E402

HVAC = ROOT / "examples" / "hvac_2cell.json"


@pytest.fixture(scope="module")
def hvac():
    b = spec.load(HVAC)
    df = sizing.optimise(b)
    best = sizing.select(df)
    d = sizing.finalize(b, {k: best[k] for k in sizing.PARAM_KEYS})
    return b, df, best, d


# ------------------------------------------------------------------ Perry's checks
def test_perry_example_13_makeup():
    # Perry's 7th ed. Ex. 13: 2270 m3/h, 37.77 -> 29.44 C, drift 0.2 %, 5 cycles, E by Perry's rule
    E = 0.00085 * 2270 * (37.77 - 29.44) * 1.8
    wb = water_balance.balance(2270, E, 0.2, 5, 37.77 - 29.44)
    assert E == pytest.approx(28.9, abs=0.05)
    assert wb["drift_m3_h"] == pytest.approx(4.54, abs=0.01)
    assert wb["blowdown_perry_m3_h"] == pytest.approx(7.24, abs=0.02)
    assert wb["makeup_perry_m3_h"] == pytest.approx(40.7, abs=0.1)
    assert wb["blowdown_m3_h"] == pytest.approx(7.24 - 4.54, abs=0.02)       # drift-corrected


def test_fan_power_matches_perry_sahp(hvac):
    # Perry eq. 12-13: SAHP = Q(cfm) * hs(in H2O) * d(lb/ft3) / (33000 * 12), with hs the fan total pressure
    fn = hvac[3]["fan"]
    cfm = fn["Q"] * 2118.88
    hs_in = fn["dP_total"] / 249.089
    sahp = cfm * hs_in * 62.4 / (33000 * 12)
    assert fn["P_air_kW"] == pytest.approx(sahp * 0.7457, rel=0.003)


def test_pump_power_matches_perry(hvac):
    b, d = hvac[0], hvac[3]
    gpm, ht_ft = b.V_w * 4.40287, d["hyd"]["pump_head_m"] * 3.28084
    bhp = gpm * ht_ft / (3960 * b.spec["costs"]["pump_efficiency"])         # Perry eq. 12-14 (water, SG 1)
    rho = d["hyd"]["rho"]
    assert d["hyd"]["pump_kW"] == pytest.approx(bhp * 0.7457 * rho / 999.0, rel=0.005)


# ------------------------------------------------------------------ components
def test_inlet_height_rules():
    s = spec.load(HVAC).spec
    assert geometry.inlet_height(6.0, 6.0, 1.0, s) == (1.5, "minimum")
    assert geometry.inlet_height(12.0, 12.0, 1.0, s) == (2.0, "aspect")          # 6 m travel / 3
    H, rule = geometry.inlet_height(6.0, 6.0, 120.0, s)                          # 120/(4*12) = 2.5
    assert (H, rule) == (2.5, "velocity")


def test_nozzle_orifice_equation():
    b = spec.load(HVAC)
    s = b.spec
    g = geometry.build(2, 7.3, 7.3, 1.2, 4.3, 1.7, "x", 0.3, s)
    h = hydraulics.design(g, b, s)
    A = math.pi / 4 * (h["orifice_mm"] / 1e3) ** 2
    q = h["q_nozzle_m3_h"] / 3600
    assert q == pytest.approx(s["water_system"]["nozzle_Cd"] * A * math.sqrt(2 * h["dp_nozzle_kPa"] * 1e3 / h["rho"]), rel=1e-9)
    assert h["nozzles_per_cell"] * h["q_nozzle_m3_h"] == pytest.approx(b.V_w / 2, rel=1e-9)
    assert len(h["nozzle_xy"]) == h["nozzles_per_cell"]
    assert all(0 < x < 7.3 and 0 < y < 7.3 for x, y in h["nozzle_xy"])


def test_pipe_sizing_respects_velocity():
    for Q in (0.01, 0.1, 0.5, 1.5):
        dn = hydraulics.pick_dn(Q, 2.0)
        assert Q / (math.pi / 4 * (dn / 1e3) ** 2) <= 2.0
        smaller = [d for d in hydraulics.DN_MM if d < dn]
        if smaller:
            assert Q / (math.pi / 4 * (smaller[-1] / 1e3) ** 2) > 2.0


def test_hi98_submergence():
    # ANSI/HI 9.8: S = D (1 + 2.3 Fr), Fr = V / sqrt(g D)
    D = math.sqrt(4 * 0.5 / (math.pi * 1.7))
    S = D * (1 + 2.3 * 1.7 / math.sqrt(9.81 * D))
    b = spec.load({"site": {"design_wet_bulb_C": 24.0}, "duty": {"water_flow_kg_s": 1.0 * 995.7, "hot_water_C": 32.0,
                   "cold_water_C": 27.0}, "water_system": {"pumps_duty": 2}})
    g = geometry.build(2, 7.3, 7.3, 1.2, 4.3, 1.7, "x", 0.3, b.spec)
    wb = water_balance.balance(b.V_w, 5.0, 0.0005, 4, 5)
    bs = basin.design(g, b, {"pipe_volume_m3": 2.0}, wb, b.spec)
    assert bs["bell_D_m"] == pytest.approx(math.sqrt(4 * (b.V_w / 3600 / 2) / (math.pi * 1.7)), rel=1e-9)
    assert bs["submergence_m"] == pytest.approx(bs["bell_D_m"] * (1 + 2.3 * 1.7 / math.sqrt(9.81 * bs["bell_D_m"])), rel=1e-9)
    assert bs["volume_operating_m3"] >= b.V_w * 5 / 60 - 1e-6
    assert S > 0


def test_motor_selection_and_gear():
    assert fan.motor_rpm(4, "415V/3ph/50Hz") == pytest.approx(1477.5)
    assert fan.motor_rpm(4, "460V/3ph/60Hz") == pytest.approx(1773.0)


# ------------------------------------------------------------------ optimiser and final design
def test_optimiser_selects_cheapest_feasible(hvac):
    _, df, best, _ = hvac
    ok = df[df.feasible]
    assert best.TPC == ok.TPC.min()
    assert (df.cells == 2).all()                                         # fixed by the spec


def test_final_design_is_consistent(hvac):
    b, _, best, d = hvac
    assert d["violations"] == []
    air, fn, g = d["air"], d["fan"], d["geom"]
    assert air["dP_static_system"] == pytest.approx(sum(r["dP"] for r in air["rows"]) - air["buoyancy_credit"])
    assert fn["dP_total"] == pytest.approx(air["dP_static_system"] + fn["dP_stack"] + fn["vp_exit"])
    assert fn["motor_kW"] >= fn["P_shaft_kW"] / b.spec["fan"]["gear_efficiency"] * b.spec["fan"]["motor_margin"]
    assert fn["fan_rpm"] * math.pi * fn["D"] / 60 == pytest.approx(b.spec["fan"]["tip_speed_design_m_s"])
    # air mass balance: dry air through the fans equals the thermal design
    assert d["flows"]["g_dry_cell"] * g.cells == pytest.approx(d["thermal"]["selected"]["G_dry_kg_s"])
    # elevations stack upward
    z = list(g.z.values())
    assert z == sorted(z)
    # design rates back to the target cold water
    assert d["thermal"]["design_check"]["T_cold"] == pytest.approx(b.T_cold, abs=0.01)
    # Poppe evaporation within +-30 % of Perry's rule
    wb = d["water_balance"]
    assert 0.7 < wb["evaporation_m3_h"] / wb["evaporation_perry_rule_m3_h"] < 1.3


def test_forced_geometry_and_rejection():
    b = spec.load(HVAC)
    d = sizing.finalize(b, {"cells": 2, "L": 9.8, "W": 9.8, "depth": 1.5, "fan_D": 6.7})
    assert d["params"]["L"] == 9.8
    with pytest.raises(ValueError):
        sizing.finalize(b, {"cells": 2, "L": 4.9, "W": 4.9, "depth": 1.2, "fan_D": 9.1})   # fan cannot fit
