"""Phase 3: FRP sections and capacities, ASCE 7 loads, PyNite extraction, frame design and BOM."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from Pynite import FEModel3D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ctdesign import spec, sizing, structure, bom, frp, loads  # noqa: E402

IN = 0.0254


def iso(E=17e9, nu=0.3):
    return frp.Material("iso", E, E, E / (2 * (1 + nu)), nu, 200e6, 200e6, 200e6, 30e6, 150e6, 1850, 1, 1, "")


# ------------------------------------------------------------------ sections and FRP checks
def test_section_properties_by_hand():
    sq = frp.make_section("SQ", [4.0, 0.25])
    b, t = 4 * IN, 0.25 * IN
    assert sq.A == pytest.approx(4 * (b - t) * t, rel=1e-9)
    assert sq.Iz == pytest.approx((b ** 4 - (b - 2 * t) ** 4) / 12, rel=1e-12)
    w = frp.make_section("W", [8.0, 8.0, 0.375])
    d, bf, t = 8 * IN, 8 * IN, 0.375 * IN
    assert w.A == pytest.approx(2 * bf * t + (d - 2 * t) * t)
    assert w.Iz > w.Iy > 0 and w.Cw > 0


def test_plate_buckling_isotropic_limits():
    m = iso()
    t, b = 0.006, 0.1
    k4 = 4 * math.pi ** 2 * m.E_L / (12 * (1 - m.nu ** 2)) * (t / b) ** 2
    assert frp.plate_ss_ss(m, b, t) == pytest.approx(k4, rel=1e-9)          # classic k = 4
    k0425 = 0.425 * math.pi ** 2 * m.E_L / (12 * (1 - m.nu ** 2)) * (t / (b / 2)) ** 2
    assert frp.flange_outstand(m, b, t) == pytest.approx(k0425, rel=0.01)    # SS-free long plate k = 0.425


def test_end_use_factors_match_asce74_slide():
    lib = frp.library()
    mt = frp.end_use_material(lib, "vinyl_ester_generic", wet=True, T_service_C=40.0)    # 104 F
    assert mt.C_strength == pytest.approx(0.75 * (1.7 - 0.008 * 104), rel=1e-9)
    assert mt.C_modulus == pytest.approx(0.90 * (1.5 - 0.006 * 104), rel=1e-9)
    dry = frp.end_use_material(lib, "vinyl_ester_generic", wet=False, T_service_C=20.0)
    assert dry.C_strength == 1.0 and dry.F_Lc == pytest.approx(200e6)


def test_compression_capacity_and_cap():
    m = iso()
    s = frp.make_section("SQ", [4.0, 0.375])
    long = frp.capacities(s, m, 6.0)
    assert long["Pc_mode"] == "global"
    assert long["Pc"] == pytest.approx(0.70 * math.pi ** 2 * m.E_L * s.A / (6.0 / s.rz) ** 2)
    short = frp.capacities(s, m, 0.3)
    assert short["Pc"] <= 0.7 * m.F_Lc * s.A + 1e-6                          # lambda phi Pn <= 0.7 lambda F_Lc A


def test_ltb_formula():
    m, s, Lb = iso(), frp.make_section("I", [8.0, 4.0, 0.375]), 3.0
    c = frp.capacities(s, m, Lb)
    Mltb = math.pi / Lb * math.sqrt(m.E_L * s.Iy * m.G * s.J + s.Iy * s.Cw * (math.pi * m.E_L / Lb) ** 2)
    assert c["Mz"] <= 0.70 * Mltb + 1e-6


def test_interaction_and_lambda():
    m, s = iso(), frp.make_section("SQ", [4.0, 0.25])
    c = frp.capacities(s, m, 2.0)
    r1 = frp.check_member(s, m, 2.0, {"P": 0.3 * c["Pt"], "Mz": 0.3 * c["Mz"], "My": 0, "V": 0}, 1.0)
    assert r1["UR"] == pytest.approx(0.6, rel=1e-6)                         # tension: no amplification
    r2 = frp.check_member(s, m, 2.0, {"P": 0.3 * c["Pt"], "Mz": 0.3 * c["Mz"], "My": 0, "V": 0}, 0.4)
    assert r2["UR"] == pytest.approx(1.5, rel=1e-6)                         # lambda 0.4 (permanent)


def test_bolted_connection_monotonic():
    m = iso()
    small = frp.bolted(5e3, 0.0095, 0.15, 1.0, m)
    big = frp.bolted(60e3, 0.0095, 0.15, 1.0, m)
    assert small["UR"] <= 1 and big["bolts"] * big["d_mm"] > small["bolts"] * small["d_mm"]


# ------------------------------------------------------------------ loads
def test_wind_velocity_pressure():
    assert loads.Kz(10.0, "C") == pytest.approx(1.0, abs=0.005)              # ASCE 7: Kz = 1.00 at 33 ft, exp. C
    assert loads.Kz(2.0, "C") == loads.Kz(4.6, "C")                          # minimum height
    assert loads.qz(10.0, 45.0, "C", Kd=0.85) == pytest.approx(0.613 * 0.85 * 45 ** 2, rel=0.006)


def test_seismic_coefficients():
    s = loads.seismic_coefficients({"Ss": 0.6, "S1": 0.2, "site_class": "D", "Ie": 1.0}, 12.0)
    assert s["SDS"] == pytest.approx(2 / 3 * 1.32 * 0.6)                     # Fa interpolated 1.4 -> 1.2
    assert s["R"] == 2.0 and s["Cs"] <= s["SDS"] / 2 + 1e-12
    g = loads.seismic_coefficients({"SDS": 0.4, "SD1": 0.05, "Ie": 1.0}, 30.0)
    assert g["source"] == "given" and g["Cs"] >= 0.044 * 0.4


def test_lambda_values_asce74():
    lam = {c["name"]: c["lam"] for c in loads.combos(0.5)}
    assert lam["1.4(D+F)"] == 0.4 and lam["1.2(D+F)+1.6L+0.5S"] == 0.8
    assert lam["1.2(D+F)+1.6S+0.5WX"] == 0.75 and lam["0.9D+WZ"] == 1.0


# ------------------------------------------------------------------ PyNite extraction
def test_internal_force_reconstruction_matches_pynite():
    m = FEModel3D()
    m.add_material("M", 17e9, 3e9, 0.3, 1850)
    m.add_section("S", 0.004, 3e-6, 8e-6, 2e-7)
    for n, p in {"a": (0, 0, 0), "b": (3, 2, 1), "c": (6, 2.5, 4), "d": (6, 0, 4)}.items():
        m.add_node(n, *p)
    for nm, i, j in (("m1", "a", "b"), ("m2", "b", "c"), ("m3", "c", "d")):
        m.add_member(nm, i, j, "M", "S")
    m.def_support("a", *[True] * 6); m.def_support("d", *[True] * 6)
    w = {"m1": 300.0, "m2": -700.0, "m3": 450.0}
    for nm, v in w.items():
        m.add_member_dist_load(nm, "FY", -v, -v, case="D")
    m.add_node_load("b", "FX", 2000, "D"); m.add_node_load("c", "FZ", -1500, "D")
    m.add_load_combo("case:D", {"D": 1.0})
    m.analyze(check_statics=False)
    fr = {"members": [{"name": k} for k in w]}
    info = {"cases": ["D"], "line_w": {k: {"D": v} for k, v in w.items()}}
    R = structure.case_results(m, fr, info)
    for nm in w:
        L = m.members[nm].L()
        for j, xi in enumerate(structure.XI):
            x = xi * L
            assert R[nm][0, 0, j] == pytest.approx(m.members[nm].axial(x, "case:D"), abs=1e-6)
            assert R[nm][0, 1, j] == pytest.approx(m.members[nm].shear("Fy", x, "case:D"), abs=1e-6)
            assert abs(R[nm][0, 3, j]) == pytest.approx(abs(m.members[nm].moment("Mz", x, "case:D")), abs=1e-6)
            assert R[nm][0, 4, j] == pytest.approx(m.members[nm].moment("My", x, "case:D"), abs=1e-6)


# ------------------------------------------------------------------ frame design and BOM
@pytest.fixture(scope="module")
def hvac_struct():
    b = spec.load(ROOT / "examples" / "hvac_2cell.json")
    d = sizing.finalize(b, {"cells": 2, "L": 7.3, "W": 7.3, "depth": 1.2, "fan_D": 4.3})
    st = structure.design(d, b, b.spec, log=lambda *a: None)
    return b, d, st


def test_framing_rules(hvac_struct):
    _, _, st = hvac_struct
    g = st["grid"]
    assert len(g["xs"]) >= 4 and len(g["zs"]) >= 4 and len(g["tiers"]) - 1 >= 3     # ASCE 74 OBCT layout
    bays = np.diff(g["xs"])
    assert bays.max() <= 2.4 + 1e-9
    braced_lines = {(m["name"][:2], m["name"].split("_")[1] if m["name"].startswith("DX") else m["name"][2:].split("_")[0])
                    for m in st["members"] if m["kind"] == "brace"}
    assert len({l for t, l in braced_lines if t == "DX"}) == len(g["zs"])            # every X line braced
    assert len({l for t, l in braced_lines if t == "DZ"}) == len(g["xs"])            # every Z line braced


def test_frame_passes_and_statics(hvac_struct):
    _, _, st = hvac_struct
    assert st["violations"] == []
    assert all(v["UR_max"] <= 1.0 for v in st["groups"].values())
    assert all(c["UR"] <= 1.0 for c in st["connections"].values())
    assert st["base_reactions"]["max_down_kN"] > 0


def test_sizing_enforces_asce74_compression_limits():
    # trial case (cement plant) where slenderness used to be reported but not designed for
    b = spec.load(ROOT / "trials" / "cement_plant" / "spec.json")
    d = sizing.finalize(b, {"cells": 4, "L": 6.1, "W": 6.1, "depth": 1.8, "fan_D": 4.3})
    st = structure.design(d, b, b.spec, log=lambda *a: None)
    assert st["slenderness_failures"] == 0 and st["serviceability_failures"] == 0
    assert st["violations"] == []
    assert any("slenderness" in g["governs"] for g in st["groups"].values())   # the limit is active in sizing


def test_gravity_equilibrium(hvac_struct):
    b, d, _ = hvac_struct
    s = b.spec
    lib = frp.library()
    mat = frp.end_use_material(lib, "vinyl_ester_generic", True, 35.0)
    fam, secs = structure._section_set(lib)
    fr = structure.framing(d, s)
    ldd = structure.build_loads(d, b, s, fr, mat)
    seis = loads.seismic_coefficients(s["loads"]["seismic"], 8.0)
    m, info = structure.analyse(fr, ldd, dict(structure.START), fam, secs, mat, seis, s)
    applied = sum(-P for c, n, dr, P in ldd["node"] if c == "D" and dr == "FY")
    applied += sum(info["line_w"][x["name"]].get("D", 0.0) * x["L"] for x in fr["members"])   # self weight + area loads
    reaction = sum(m.nodes[n].RxnFY["case:D"] for n in fr["nodes"] if structure.tier_of(n) == 0)
    assert reaction == pytest.approx(applied, rel=1e-6)


def test_bom_counts(hvac_struct):
    b, d, st = hvac_struct
    B = bom.build(d, b, b.spec, st)
    g = st["grid"]
    cols = B[B.item == "Column"].qty.sum()
    assert cols == len(g["xs"]) * len(g["zs"])                  # 2 cells modelled = whole tower here
    assert (B.total_kg >= 0).all()
    summ = bom.summary(B)
    assert summ["frp_structure_kg"] > 0
    nozzles = B[B.item == "Spray nozzle"].qty.iloc[0]
    assert nozzles == d["geom"].cells * d["hyd"]["nozzles_per_cell"]
