"""Cell geometry and elevations of a counterflow induced-draft cell.

Datum: basin operating water level = 0.0 m. Cells sit in one row along x; each cell is
L (along the row) x W (across). With "two_sides" inlets air enters both long faces and
travels W/2 to the cell centre; with "four_sides" (single cell) it travels min(L, W)/2.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

CURB = 0.3            # basin curb above operating water level
FILL_SUPPORT = 0.15   # inlet top to fill bottom (support beams)
ELIM_DEPTH = {"cellular": 0.15, "blade": 0.20}


@dataclass
class Geometry:
    cells: int
    L: float
    W: float
    depth: float              # fill depth
    fan_D: float
    H_inlet: float
    inlet_rule: str
    z: dict                   # named elevations, m
    stack_H: float
    stack_exit_D: float

    @property
    def cell_area(self):
        return self.L * self.W

    @property
    def plan_area(self):
        return self.cells * self.L * self.W

    @property
    def H_rain(self):
        return self.z["fill_bottom"]       # fill bottom to basin water level

    def to_dict(self):
        d = asdict(self)
        d.update(cell_area=self.cell_area, plan_area=self.plan_area, H_rain=self.H_rain)
        return d


def air_travel(L, W, inlets):
    return W / 2.0 if inlets == "two_sides" else min(L, W) / 2.0


def inlet_perimeter(L, W, inlets):
    return 2.0 * L if inlets == "two_sides" else 2.0 * (L + W)


def inlet_height(L, W, Q_in_cell, s: dict):
    """Air-inlet height: the largest of the minimum, the aspect rule and the inlet-velocity rule."""
    lim, inlets = s["limits"], s["tower"]["air_inlets"]
    if s["tower"].get("air_inlet_height_m"):
        return float(s["tower"]["air_inlet_height_m"]), "fixed by spec"
    rules = {"minimum": lim["inlet_height_min_m"],
             "aspect": air_travel(L, W, inlets) / lim["inlet_aspect_max"],
             "velocity": Q_in_cell / (lim["air_inlet_velocity_max_m_s"] * inlet_perimeter(L, W, inlets))}
    rule = max(rules, key=rules.get)
    return math.ceil(rules[rule] * 10 - 1e-9) / 10.0, rule


def build(cells, L, W, depth, fan_D, H_inlet, inlet_rule, header_D, s: dict) -> Geometry:
    t, a = s["tower"], s["airside"]
    z = {"water": 0.0, "curb": CURB, "inlet_top": CURB + H_inlet}
    z["fill_bottom"] = z["inlet_top"] + FILL_SUPPORT
    z["fill_top"] = z["fill_bottom"] + depth
    z["nozzle"] = z["fill_top"] + t["nozzle_clearance_m"]
    z["header_cl"] = z["nozzle"] + 0.15 + header_D / 2.0
    z["elim_bottom"] = z["header_cl"] + header_D / 2.0 + 0.3
    z["elim_top"] = z["elim_bottom"] + ELIM_DEPTH[t["drift_eliminator"]]
    z["fan_deck"] = z["elim_top"] + max(1.5, 0.4 * fan_D)
    z["fan"] = z["fan_deck"] + 0.4
    if t.get("fan_stack_height_m"):
        Hs = float(t["fan_stack_height_m"])
    else:
        Hs = max(1.8, (0.5 if t["fan_stack"] == "velocity_recovery" else 0.3) * fan_D)
    Hs = math.ceil(Hs * 10 - 1e-9) / 10.0
    exit_D = fan_D + (2 * (Hs - 0.4) * math.tan(math.radians(a["stack_half_angle_deg"]))
                      if t["fan_stack"] == "velocity_recovery" else 0.0)
    z["stack_top"] = z["fan_deck"] + Hs
    return Geometry(cells, L, W, depth, fan_D, H_inlet, inlet_rule, {k: round(v, 3) for k, v in z.items()}, Hs, exit_D)
