"""Makeup water balance (Perry's 7th ed. eqs. 12-9 to 12-12, drift-corrected blowdown).

  makeup  M = E + D + B
  blowdown B = E/(C - 1) - D        (drift also carries dissolved solids out; never below 0)
Perry's form B = E/(C - 1) ignores drift; it is reported as the conservative bound.
Evaporation comes from Poppe; Perry's rule E = 0.00085 Wc dT(F) = 0.153 %/K is the check value.
"""
from __future__ import annotations


def balance(flow_m3_h: float, evap_m3_h: float, drift_pct: float, cycles: float, range_K: float) -> dict:
    if cycles <= 1.0:
        raise ValueError("cycles of concentration must exceed 1")
    D = flow_m3_h * drift_pct / 100.0
    B = max(0.0, evap_m3_h / (cycles - 1.0) - D)
    B_perry = evap_m3_h / (cycles - 1.0)
    return {"evaporation_m3_h": evap_m3_h, "evaporation_perry_rule_m3_h": 0.00085 * 1.8 * flow_m3_h * range_K,
            "drift_m3_h": D, "blowdown_m3_h": B, "makeup_m3_h": evap_m3_h + D + B,
            "blowdown_perry_m3_h": B_perry, "makeup_perry_m3_h": evap_m3_h + D + B_perry, "cycles": cycles}
