"""Regression against Perry's Chemical Engineers' Handbook (7th ed.), Sec. 12, Evaporative Cooling.

  * Example 9 (p. 12-15): CTI Chebyshev KaV/L, 105 -> 85 F, WB 78 F, L/G 0.97 -> 1.71, with the four
    tabulated driving forces.
  * Counterflow statement (p. 12-16): L/G 1, WB 78 F, hot 95 F, 5 F approach -> KaV/L 1.75 (rounded).
  * Example 10 (p. 12-15): Wood & Betts NOMOGRAPH, which Perry's calls approximate; only the
    trend (a 20 F drop in wet-bulb lowers cold water ~10 F at constant KaV/L and L/G) is checked.
Perry's uses Btu/lb dry air on a 0 F air datum; differences of enthalpy are datum-free (1 Btu/lb = 2326 J/kg).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import psychro as ps, thermal as th  # noqa: E402

P = 101325.0
BTU = 2326.0


def F(f):
    return (f - 32.0) / 1.8


def test_perry_example_9_driving_forces():
    a = ps.air_state(None, F(78), P)
    Th, Tc = F(105), F(85)
    for x, ref in zip([0.1, 0.4, 0.6, 0.9], [8.41, 10.91, 13.33, 18.30]):
        T = Tc + x * (Th - Tc)
        dh = ps.h_sat(T, P) - (a["h"] + 0.97 * ps.CPW * (T - Tc))
        assert dh / BTU == pytest.approx(ref, rel=0.01)


def test_perry_example_9_kavl():
    a = ps.air_state(None, F(78), P)
    assert th.merkel(F(105), F(85), 0.97, a["h"], P, method="chebyshev") == pytest.approx(1.71, rel=0.005)
    assert th.merkel(F(105), F(85), 0.97, a["h"], P) == pytest.approx(1.71, rel=0.005)


def test_perry_counterflow_5F_approach():
    a = ps.air_state(None, F(78), P)
    assert th.merkel(F(95), F(83), 1.0, a["h"], P, method="chebyshev") == pytest.approx(1.75, rel=0.03)


def test_perry_example_10_nomograph_trend():
    a70, a50 = ps.air_state(None, F(70), P), ps.air_state(None, F(50), P)
    Me = th.merkel(F(100), F(80), 1.0, a70["h"], P)
    r = th.rate(lambda lg: Me, 1.0, a50, P, range_C=20 / 1.8)
    assert r["T_cold"] * 1.8 + 32 == pytest.approx(70.0, abs=2.0)      # nomograph: 70 F
