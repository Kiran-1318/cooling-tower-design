import sys
from pathlib import Path

import psychrolib
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import spec  # noqa: E402

BASE = {"site": {"design_wet_bulb_C": 24.0}, "duty": {"water_flow_m3_h": 1000.0}}


def mk(**duty):
    return {"site": BASE["site"], "duty": {**BASE["duty"], **duty}}


def test_examples_load():
    for f in (ROOT / "examples").glob("*.json"):
        b = spec.load(f)
        assert b.Q > 0 and b.range > 0 and b.approach >= 2.8


def test_temperature_closure_variants():
    a = spec.load(mk(hot_water_C=32.0, cold_water_C=27.0))
    b = spec.load(mk(range_C=5.0, approach_C=3.0))
    c = spec.load(mk(hot_water_C=32.0, range_C=5.0))
    assert (a.T_hot, a.T_cold) == (32.0, 27.0) == (b.T_hot, b.T_cold) == (c.T_hot, c.T_cold)


def test_duty_hand_check():
    b = spec.load(mk(hot_water_C=32.0, cold_water_C=27.0))
    # 1000 m3/h * ~995 kg/m3 * ~4180 J/kgK * 5 K  ~= 5.78 MW
    assert b.Q == pytest.approx(1000 / 3600 * 995.0 * 4180 * 5.0, rel=0.005)


def test_inconsistent_and_tight_inputs_rejected():
    with pytest.raises(ValueError):
        spec.load(mk(hot_water_C=32.0, cold_water_C=27.0, range_C=4.0))
    with pytest.raises(ValueError):
        spec.load(mk(hot_water_C=30.0, cold_water_C=26.0))       # approach 2 K < 2.8 K


def test_altitude_pressure_matches_psychrolib():
    psychrolib.SetUnitSystem(psychrolib.SI)
    for z in (0.0, 500.0, 1500.0):
        assert spec.p_atm_from_altitude(z) == pytest.approx(psychrolib.GetStandardAtmPressure(z), rel=1e-4)
