"""Tower characteristic ("supply"): fill + rain zone + spray zone Merkel numbers and fill loss.

Coefficients come from references/fill_library.json. Each entry says whether it is PUBLISHED
(with its source) or GENERIC; a vendor curve passed as tower.fill_override replaces the fill
entry key by key. Everything the design leans on outside a correlation's tested range is
returned as a warning so the report can flag it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[2] / "references" / "fill_library.json"


def load_library(path: Path = LIBRARY) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass
class Characteristic:
    fill_type: str
    fill: dict
    depth: float                     # m
    rain: dict
    H_rain: float                    # m, fill bottom to basin water level
    Me_spray: float
    warnings: list = field(default_factory=list)

    def Me_fill(self, LG):
        f = self.fill
        return f["C"] * LG ** (-f["n"]) * self.depth ** f["m"]

    def Me_rain(self, LG):
        r = self.rain
        return r["C"] * LG ** (-r["n"]) * self.H_rain if self.H_rain > 0 else 0.0 * LG

    def __call__(self, LG):
        return self.Me_fill(LG) + self.Me_rain(LG) + self.Me_spray

    def K_fill(self, Gw, Ga):
        """Fill loss coefficient referred to the air dynamic pressure at the fill face."""
        f = self.fill
        return f["k"] * self.depth * (Gw / f["Gw_ref"]) ** f["d"] * (Ga / f["Ga_ref"]) ** f["e"]

    def breakdown(self, LG):
        return {"Me_fill": float(self.Me_fill(LG)), "Me_rain": float(self.Me_rain(LG)),
                "Me_spray": float(self.Me_spray), "Me_total": float(self(LG))}

    def check(self, LG, T_hot, loading_m3_h_m2=None):
        """Range-of-validity and material warnings at an operating point."""
        f, r, w = self.fill, self.rain, []
        lo, hi = f["LG_range"]
        if not lo <= LG <= hi:
            w.append(f"L/G {LG:.2f} outside the {self.fill_type} fill data range {lo}-{hi}")
        lo, hi = f["depth_range_m"]
        if not lo <= self.depth <= hi:
            w.append(f"fill depth {self.depth:.2f} m outside the data range {lo}-{hi} m")
        if T_hot > f["max_hot_water_C"]:
            w.append(f"hot water {T_hot:.1f} C exceeds the {f['material']} fill limit {f['max_hot_water_C']} C")
        if loading_m3_h_m2 is not None:
            lo, hi = f["water_loading_m3_h_m2"]
            if not lo <= loading_m3_h_m2 <= hi:
                w.append(f"water loading {loading_m3_h_m2:.1f} m3/h.m2 outside {lo}-{hi}")
        if self.H_rain > 0:
            lo, hi = r["H_range_m"]
            if not lo <= self.H_rain <= hi:
                w.append(f"rain-zone height {self.H_rain:.2f} m outside the correlation range {lo}-{hi} m")
            lo, hi = r["LG_range"]
            if not lo <= LG <= hi:
                w.append(f"L/G {LG:.2f} outside the rain-zone correlation range {lo}-{hi}")
        if f.get("basis", "").startswith("GENERIC"):
            w.append(f"{self.fill_type} fill uses GENERIC coefficients - obtain vendor curves before purchase")
        return w


def characteristic(tower: dict, depth: float, H_rain: float, library: dict | None = None) -> Characteristic:
    lib = library or load_library()
    ft = tower.get("fill_type", "film")
    if ft not in lib["fills"]:
        raise ValueError(f"unknown fill_type '{ft}'; choose from {sorted(lib['fills'])}")
    fill = dict(lib["fills"][ft])
    if tower.get("fill_override"):
        fill.update(tower["fill_override"])
        fill["basis"] = "VENDOR - user supplied (tower.fill_override)"
    spray = tower.get("spray_zone_Me", lib["spray_zone"]["Me"])
    return Characteristic(ft, fill, float(depth), lib["rain_zone"], float(H_rain), float(spray))
