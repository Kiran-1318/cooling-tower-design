"""Design specification: load a JSON spec, fill defaults, close the water-side duty.

A spec describes one mechanical induced-draft counterflow cooling tower: the site
(altitude, design wet-bulb, wind/seismic data), the water duty (flow, hot/cold water
or range/approach), the configuration choices that are fixed and the ones left to the
optimiser, limits, water-treatment data, cost rates and project metadata.
See references/spec_schema.md.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from CoolProp.CoolProp import PropsSI

P_ATM = 101325.0
K = 273.15

DEFAULT_SPEC = {
    "project": {"name": "Cooling tower", "tag": "CT-101", "client": "", "site_name": "", "date": "",
                "revision": "A", "drawn_by": "", "units": "SI"},
    "site": {
        "altitude_m": 0.0,                 # used for barometric pressure unless P_atm_kPa is given
        "P_atm_kPa": None,
        "design_wet_bulb_C": None,         # required
        "design_dry_bulb_C": None,         # optional; RH or dry bulb sets the inlet air humidity for Poppe
        "recirculation_allowance_C": 0.0,  # added to the wet-bulb for recirculation/interference
    },
    "duty": {
        "water_flow_m3_h": None,           # required (or water_flow_kg_s)
        "water_flow_kg_s": None,
        "hot_water_C": None,               # give two of hot, cold, range, approach
        "cold_water_C": None,
        "range_C": None,
        "approach_C": None,
    },
    "tower": {
        "type": "counterflow_induced_draft",
        "cells": None,                     # None -> optimiser chooses
        "cell_length_m": None,             # along the cell row; None -> optimiser
        "cell_width_m": None,
        "fill_type": "film",               # key into references/fill_library.json
        "fill_depth_m": None,              # None -> optimiser
        "fill_override": None,             # vendor curve: {"C":..,"n":..,"dp": {...}}
        "air_inlet_height_m": None,        # None -> from rain-zone / inlet-velocity rule
        "air_inlets": "two_sides",         # "two_sides" (row of cells) | "four_sides" (single cell)
        "drift_eliminator": "cellular",    # "cellular" | "blade"
        "drift_rate_pct": 0.0005,          # % of circulating flow
        "nozzle_type": "low_pressure_spray",
        "fan_diameter_m": None,            # None -> optimiser (standard sizes)
        "fan_stack": "velocity_recovery",  # "straight" | "velocity_recovery"
        "fan_stack_height_m": None,
        "motor_poles": 4,
        "power_supply": "415V/3ph/50Hz",
        "basin": "concrete",               # "concrete" (civil by others) | "frp"
        "basin_depth_m": None,
    },
    "limits": {
        "approach_min_C": 2.8,
        "water_loading_m3_h_m2": [8.0, 20.0],
        "fill_air_velocity_m_s": [1.8, 3.5],
        "air_inlet_velocity_max_m_s": 4.0,
        "fan_tip_speed_max_m_s": 61.0,
        "fan_static_max_Pa": 250.0,
        "eliminator_velocity_max_m_s": 3.5,
        "nozzle_pressure_kPa": [20.0, 70.0],
        "thermal_capability_min_pct": 100.0,
        "basin_retention_min": 5.0,        # minutes of circulating flow held in the basin
    },
    "water": {
        "cycles_of_concentration": 4.0,
        "makeup_tds_mg_L": None,
    },
    "structure": {
        "material": "frp_pultruded",
        "profile_library": "frp_profiles.json",
        "column_bay_m": [1.8, 2.4],
        "fastener_material": "SS316",
        "fill_hold_up_kg_m3": 150.0,       # wet fill + scale/biofouling allowance on fill supports
        "fan_deck_live_kPa": 2.4,
        "casing": "frp_corrugated",
    },
    "loads": {
        "code": "ASCE 7-22",
        "risk_category": "II",
        "wind_speed_m_s": 45.0,            # basic wind speed V (3-s gust, 10 m, exposure C)
        "exposure": "C",
        "seismic": {"Ss": 0.25, "S1": 0.10, "site_class": "D", "Ie": 1.0},
        "ground_snow_kPa": 0.0,
    },
    "costs": {
        "currency": "USD",
        "frp_per_kg": 9.0, "fill_per_m3": 300.0, "eliminator_per_m2": 60.0, "casing_per_m2": 45.0,
        "fan_set_per_kW": 600.0, "fixed_per_cell": 20000.0, "basin_per_m2": 250.0,
        "electricity_per_kWh": 0.12, "hours_per_year": 8000.0, "years": 15, "rate": 0.10,
        "pump_efficiency": 0.75,
    },
    "grid": {                              # optimiser search space (used only where tower.* is None)
        "cells": [1, 2, 3, 4, 6, 8],
        "cell_plan_m": [[4.9, 4.9], [6.1, 6.1], [7.3, 7.3], [9.8, 9.8], [12.2, 12.2], [14.6, 14.6]],
        "fill_depth_m": [0.9, 1.2, 1.5, 1.8],
        "fan_diameter_m": [2.4, 3.0, 3.7, 4.3, 5.5, 6.7, 7.9, 8.5, 9.1, 10.4],
    },
    "rating_cases": [],                    # [{"label":..., "wet_bulb_C":..., "flow_factor":..., "range_C":...}]
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def p_atm_from_altitude(z_m: float) -> float:
    """Barometric pressure (Pa) of the ICAO standard atmosphere at altitude z (m)."""
    return P_ATM * (1.0 - 2.25577e-5 * z_m) ** 5.25588


@dataclass
class Basis:
    spec: dict
    P_atm: float              # Pa
    T_wb: float               # degC, design wet-bulb incl. recirculation allowance
    T_db: float | None        # degC
    T_hot: float              # degC
    T_cold: float
    m_w: float                # kg/s circulating water
    V_w: float                # m3/h circulating water at the hot-water temperature
    rho_w: float              # kg/m3 at the mean water temperature
    cp_w: float               # J/kgK at the mean water temperature
    Q: float                  # W heat rejected
    meta: dict = field(default_factory=dict)

    @property
    def range(self) -> float:
        return self.T_hot - self.T_cold

    @property
    def approach(self) -> float:
        return self.T_cold - self.T_wb


def _temperatures(duty: dict, T_wb: float) -> tuple[float, float]:
    hot, cold, rng, app = (duty.get(k) for k in ("hot_water_C", "cold_water_C", "range_C", "approach_C"))
    if cold is None and app is not None:
        cold = T_wb + app
    if hot is None and cold is not None and rng is not None:
        hot = cold + rng
    if cold is None and hot is not None and rng is not None:
        cold = hot - rng
    if hot is None or cold is None:
        raise ValueError("duty: give two of hot_water_C, cold_water_C, range_C, approach_C "
                         "(at least one of them a temperature or the approach).")
    for k, v, derived in (("range_C", rng, hot - cold), ("approach_C", app, cold - T_wb)):
        if v is not None and abs(v - derived) > 0.05:
            raise ValueError(f"duty: {k}={v} is inconsistent with the temperatures given ({derived:.2f}).")
    return float(hot), float(cold)


def load(spec_path_or_dict) -> Basis:
    raw = spec_path_or_dict if isinstance(spec_path_or_dict, dict) else \
        json.loads(Path(spec_path_or_dict).read_text(encoding="utf-8"))
    spec = _merge(DEFAULT_SPEC, raw)
    site, duty, lim = spec["site"], spec["duty"], spec["limits"]

    if site["design_wet_bulb_C"] is None:
        raise ValueError("site.design_wet_bulb_C is required.")
    P = site["P_atm_kPa"] * 1e3 if site["P_atm_kPa"] else p_atm_from_altitude(float(site["altitude_m"]))
    T_wb = float(site["design_wet_bulb_C"]) + float(site["recirculation_allowance_C"])
    T_db = site["design_dry_bulb_C"]
    if T_db is not None and T_db < T_wb - 1e-6:
        raise ValueError("site: design_dry_bulb_C is below the wet-bulb.")

    T_hot, T_cold = _temperatures(duty, T_wb)
    if T_hot <= T_cold:
        raise ValueError("duty: hot water must be warmer than cold water.")
    if T_cold - T_wb < lim["approach_min_C"]:
        raise ValueError(f"duty: approach {T_cold - T_wb:.2f} K is below limits.approach_min_C "
                         f"({lim['approach_min_C']} K); a counterflow tower cannot be guaranteed that close.")

    Tm = 0.5 * (T_hot + T_cold) + K
    rho_m = PropsSI("D", "T", Tm, "P", P, "Water")
    cp = PropsSI("C", "T", Tm, "P", P, "Water")
    rho_hot = PropsSI("D", "T", T_hot + K, "P", P, "Water")
    if duty["water_flow_kg_s"]:
        m = float(duty["water_flow_kg_s"])
    elif duty["water_flow_m3_h"]:
        m = float(duty["water_flow_m3_h"]) * rho_hot / 3600.0
    else:
        raise ValueError("duty: water_flow_m3_h or water_flow_kg_s is required.")
    Q = m * cp * (T_hot - T_cold)
    return Basis(spec, P, T_wb, None if T_db is None else float(T_db), T_hot, T_cold, m,
                 m / rho_hot * 3600.0, rho_m, cp, Q)
