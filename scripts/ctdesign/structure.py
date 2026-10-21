"""Pultruded FRP framing: generator, ASCE 7 loads, PyNite 3D frame analysis and member sizing.

Framing follows the ASCE/SEI 74 "ordinary braced cooling tower" rules (R = 2):
  * orthogonal grid of columns, bays within structure.column_bay_m, at least four column lines;
  * columns continuous from the basin floor to the fan deck; beams on every grid line at every tier
    (at least three tiers): basin tie (just above water), fill support, distribution support,
    eliminator support, fan deck;
  * every column line braced in both directions with diagonals (alternate bays, alternating
    direction) in each storey taller than 0.9 m; braces are pin-ended.
Global axes: X along the cell row, Y up (from the basin operating water level), Z across the cell.
PyNite axial forces are positive in compression; this module converts to tension-positive.

When the tower has more cells than structure.model_cells_max, a representative block of that many
cells (end walls on both sides) is analysed and the member sizes are applied to every cell.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict

import numpy as np
from Pynite import FEModel3D

from . import frp, loads as ld

G = 9.81
GROUPS = ["column", "fill_beam", "dist_beam", "elim_beam", "deck_beam", "tie_beam", "brace"]
START = {"column": 2, "fill_beam": 1, "dist_beam": 0, "elim_beam": 0, "deck_beam": 1, "tie_beam": 0, "brace": 0}


def _grid(length: float, bay_lo: float, bay_hi: float) -> list[float]:
    n = max(1, math.ceil(length / bay_hi - 1e-9))
    while length / n < bay_lo and n > 1:
        n -= 1
    return [length * i / n for i in range(n + 1)]


def _trib(vals: list[float], i: int, lo=None, hi=None) -> float:
    a = vals[i] if i == 0 else 0.5 * (vals[i - 1] + vals[i])
    b = vals[i] if i == len(vals) - 1 else 0.5 * (vals[i] + vals[i + 1])
    if lo is not None:
        a, b = max(a, lo), min(b, hi)
    return max(0.0, b - a)


def framing(d: dict, s: dict) -> dict:
    """Node and member layout of the modelled block of cells."""
    g, st = d["geom"], s["structure"]
    n_m = min(g.cells, st.get("model_cells_max", 2))
    lo, hi = st["column_bay_m"]
    xc = _grid(g.L, lo, hi)
    xs = sorted({round(c * g.L + x, 4) for c in range(n_m) for x in xc})
    zs = [round(z, 4) for z in _grid(g.W, lo, hi)]
    if len(xs) < 4 or len(zs) < 4:                       # ASCE 74: at least four column lines
        zs = [round(g.W * i / 3, 4) for i in range(4)] if len(zs) < 4 else zs
        xs = sorted({round(n_m * g.L * i / 3, 4) for i in range(4)} | set(xs)) if len(xs) < 4 else xs
    floor = -d["basin"]["water_depth_m"]
    tiers = [("base", floor)]
    if floor < -0.5:
        tiers.append(("tie", g.z["curb"]))
    tiers += [("fill", g.z["fill_bottom"]), ("dist", g.z["nozzle"] + 0.15), ("elim", g.z["elim_bottom"]),
              ("deck", g.z["fan_deck"])]
    beam_group = {"tie": "tie_beam", "fill": "fill_beam", "dist": "dist_beam", "elim": "elim_beam", "deck": "deck_beam"}
    nodes, members = {}, []
    N = lambda i, k, t: f"N{i}_{k}_{t}"
    for t, (tn, y) in enumerate(tiers):
        for i, x in enumerate(xs):
            for k, z in enumerate(zs):
                nodes[N(i, k, t)] = (x, y, z)
    for t in range(1, len(tiers)):
        tn, y = tiers[t]
        h = y - tiers[t - 1][1]
        for i in range(len(xs)):
            for k in range(len(zs)):
                members.append({"name": f"C{i}_{k}_{t}", "i": N(i, k, t - 1), "j": N(i, k, t), "group": "column",
                                "kind": "column", "tier": t, "L": h})
        for k in range(len(zs)):
            for i in range(len(xs) - 1):
                members.append({"name": f"BX{i}_{k}_{t}", "i": N(i, k, t), "j": N(i + 1, k, t), "group": beam_group[tn],
                                "kind": "beam", "dir": "x", "tier": t, "line": k, "L": xs[i + 1] - xs[i]})
        for i in range(len(xs)):
            for k in range(len(zs) - 1):
                members.append({"name": f"BZ{i}_{k}_{t}", "i": N(i, k, t), "j": N(i, k + 1, t), "group": beam_group[tn],
                                "kind": "beam", "dir": "z", "tier": t, "line": i, "L": zs[k + 1] - zs[k]})
        if h >= 0.9:
            for k in range(len(zs)):
                for i in range(len(xs) - 1):
                    if (i + t) % 2 == 0:
                        a, b = (N(i, k, t - 1), N(i + 1, k, t)) if (i // 2) % 2 == 0 else (N(i + 1, k, t - 1), N(i, k, t))
                        members.append({"name": f"DX{i}_{k}_{t}", "i": a, "j": b, "group": "brace", "kind": "brace",
                                        "tier": t, "L": math.hypot(xs[i + 1] - xs[i], h)})
            for i in range(len(xs)):
                for k in range(len(zs) - 1):
                    if (k + t) % 2 == 0:
                        a, b = (N(i, k, t - 1), N(i, k + 1, t)) if (k // 2) % 2 == 0 else (N(i, k + 1, t - 1), N(i, k, t))
                        members.append({"name": f"DZ{i}_{k}_{t}", "i": a, "j": b, "group": "brace", "kind": "brace",
                                        "tier": t, "L": math.hypot(zs[k + 1] - zs[k], h)})
    return {"xs": xs, "zs": zs, "tiers": tiers, "nodes": nodes, "members": members, "cells_modelled": n_m,
            "N": N}


# ----------------------------------------------------------------------------- loads
def build_loads(d: dict, b, s: dict, fr: dict, mat: frp.Material) -> dict:
    """Load cases D, F, L, S, WX, WZ, EX, EZ as member line loads and node loads (N, m)."""
    g, st, lo = d["geom"], s["structure"], s["loads"]
    xs, zs, tiers, N = fr["xs"], fr["zs"], fr["tiers"], fr["N"]
    T = {tn: t for t, (tn, _) in enumerate(tiers)}
    lib_fill = d["thermal"]["selected"]["_char"].fill
    line, node = [], []                                   # (case, member, w N/m) / (case, node, dir, P)
    tier_w = defaultdict(float)

    def area_on_x_beams(case, tier, q, cell_only=None):
        t = T[tier]
        for k in range(len(zs)):
            tw = _trib(zs, k)
            for i in range(len(xs) - 1):
                line.append((case, f"BX{i}_{k}_{t}", q * tw))
                tier_w[t] += q * tw * (xs[i + 1] - xs[i]) if case in ("D", "F") else 0.0

    # fill: dry weight (D) and hold-up water + fouling allowance (F)
    area_on_x_beams("D", "fill", lib_fill.get("density_dry_kg_m3", 35.0) * g.depth * G)
    area_on_x_beams("F", "fill", st["fill_hold_up_kg_m3"] * g.depth * G)
    # distribution: water in pipes (F), pipes + nozzles at ~30 % of the water weight (D)
    q_pipe = d["hyd"]["pipe_volume_m3"] * 1000.0 * G / g.plan_area
    area_on_x_beams("F", "dist", q_pipe)
    area_on_x_beams("D", "dist", 0.3 * q_pipe)
    area_on_x_beams("D", "elim", 15.0 * G)                # wet cellular eliminator packs
    area_on_x_beams("D", "deck", 30.0 * G)                # FRP deck panels + grating
    area_on_x_beams("L", "deck", st["fan_deck_live_kPa"] * 1e3)
    snow = 0.7 * lo.get("ground_snow_kPa", 0.0) * 1e3
    if snow > 0:
        area_on_x_beams("S", "deck", snow)

    # mechanical equipment + fan stack, per cell, on deck nodes
    fn = d["fan"]
    m_eq = 25.0 * fn["D"] ** 2 + 8.0 * fn["motor_kW"]             # fan + gearbox + motor + shaft (estimate, kg)
    stack_area = math.pi * 0.5 * (fn["D"] + fn["stack_exit_D"]) * fn["stack_H"]
    m_stack = 20.0 * stack_area                                    # FRP stack shell (estimate, kg)
    td = T["deck"]
    deck_nodes = [(N(i, k, td), xs[i], zs[k]) for i in range(len(xs)) for k in range(len(zs))]
    q_stack_wind = ld.qz(fn["stack_H"] / 2 + g.z["fan_deck"], lo["wind_speed_m_s"], lo["exposure"],
                         lo.get("Kd", 0.90), z_ground=s["site"]["altitude_m"]) * 0.85 * 0.7 * fn["D"] * fn["stack_H"]
    for c in range(fr["cells_modelled"]):
        cx, cz = (c + 0.5) * g.L, g.W / 2
        near = sorted(deck_nodes, key=lambda n: math.hypot(n[1] - cx, n[2] - cz))[:4]
        for nm, _, _ in near:
            node.append(("D", nm, "FY", -m_eq * G / 4))
        ring = [n for n in deck_nodes if abs(math.hypot(n[1] - cx, n[2] - cz) - fn["D"] / 2) < 0.75 * (xs[1] - xs[0])] or near
        for nm, _, _ in ring:
            node.append(("D", nm, "FY", -m_stack * G / len(ring)))
            node.append(("WX", nm, "FX", q_stack_wind / len(ring)))
            node.append(("WZ", nm, "FZ", q_stack_wind / len(ring)))
        tier_w[td] += (m_eq + m_stack) * G

    # casing (8 kg/m2) and wind on the perimeter faces
    ys = [y for _, y in tiers]
    y_top = g.z["fan_deck"]
    h_tot = y_top - g.z["curb"]
    Cf_x = ld.Cf_square(h_tot / g.W)
    Cf_z = ld.Cf_square(h_tot / (fr["cells_modelled"] * g.L))
    two = s["tower"]["air_inlets"] == "two_sides"
    for t in range(1, len(tiers)):
        y = ys[t]
        cased_lo = g.z["curb"] if not two else g.z["inlet_top"]
        for fname, kind in (("x0", "end"), ("x1", "end"), ("z0", "side"), ("z1", "side")):
            if fname.startswith("x"):
                i = 0 if fname == "x0" else len(xs) - 1
                pts = [(N(i, k, t), zs, k) for k in range(len(zs))]
                lo_c = g.z["curb"]                                   # end walls cased full height
            else:
                k = 0 if fname == "z0" else len(zs) - 1
                pts = [(N(i, k, t), xs, i) for i in range(len(xs))]
                lo_c = cased_lo
            for nm, u, idx in pts:
                w = _trib(u, idx)
                h_c = _trib(ys, t, lo_c, y_top)
                if h_c > 0:
                    node.append(("D", nm, "FY", -8.0 * G * w * h_c))
                    tier_w[t] += 8.0 * G * w * h_c
                h_w = _trib(ys, t, g.z["curb"], y_top)                # wind on the full face height
                q = ld.qz(max(y, 0.1), lo["wind_speed_m_s"], lo["exposure"], lo.get("Kd", 0.90),
                          z_ground=s["site"]["altitude_m"])
                if fname == "x0":
                    node.append(("WX", nm, "FX", q * 0.85 * Cf_x * w * h_w))
                if fname == "z0":
                    node.append(("WZ", nm, "FZ", q * 0.85 * Cf_z * w * h_w))

    # member self weight (D): a marker, resolved per section size in analyse()
    for m in fr["members"]:
        line.append(("D", m["name"], -1.0))
    return {"line": line, "node": node, "tier_w": dict(tier_w), "m_eq_kg": m_eq, "m_stack_kg": m_stack}


# ----------------------------------------------------------------------------- model, analysis, design
def tier_of(node: str) -> int:
    return int(node.rsplit("_", 1)[1])


def _section_set(lib):
    fam = {g: lib["groups"].get(g, {"family": "I"})["family"] for g in GROUPS}
    fam["tie_beam"] = "I"
    return fam, {f: frp.family_sections(lib, f) for f in set(fam.values())}


def analyse(fr, ldd, sizes: dict, fam, secs, mat, seis, s) -> tuple[FEModel3D, dict]:
    m = FEModel3D()
    m.add_material("FRP", mat.E_L, mat.G, mat.nu, mat.rho)
    for gname in GROUPS:
        sc = secs[fam[gname]][sizes[gname]]
        m.add_section(gname, sc.A, sc.Iy, sc.Iz, sc.J)
    for n, (x, y, z) in fr["nodes"].items():
        m.add_node(n, x, y, z)
    for mb in fr["members"]:
        m.add_member(mb["name"], mb["i"], mb["j"], "FRP", mb["group"])
        if mb["kind"] == "brace":
            m.def_releases(mb["name"], Ryi=True, Rzi=True, Ryj=True, Rzj=True)
    for n in fr["nodes"]:
        if tier_of(n) == 0:
            m.def_support(n, True, True, True, False, False, False)
    # torsional restraint for pin-ended braces is provided by their Rx end fixity
    weights = defaultdict(float, ldd["tier_w"])
    for case, mem, w in ldd["line"]:
        mb = m.members[mem]
        if w == -1.0:                                                 # self weight
            sec = secs[fam[fr_by_name(fr)[mem]["group"]]][sizes[fr_by_name(fr)[mem]["group"]]]
            ww = sec.A * mat.rho * G
            m.add_member_dist_load(mem, "FY", -ww, -ww, case="D")
            t = fr_by_name(fr)[mem]["tier"]
            info = fr_by_name(fr)[mem]
            if info["kind"] == "beam":
                weights[t] += ww * info["L"]
            else:
                weights[t] += 0.5 * ww * info["L"]
                if t - 1 > 0:
                    weights[t - 1] += 0.5 * ww * info["L"]
        else:
            m.add_member_dist_load(mem, "FY", -w, -w, case=case)
    for case, n, dr, P in ldd["node"]:
        m.add_node_load(n, dr, P, case=case)
    # seismic: ELF base shear on the modelled block, vertical distribution over the tiers
    base_y = fr["tiers"][0][1]
    lev = [(fr["tiers"][t][1] - base_y, weights[t]) for t in range(1, len(fr["tiers"]))]
    W = sum(w for _, w in lev)
    V = seis["Cs"] * W
    Fx = ld.vertical_distribution(V, lev, seis["k"])
    for t, F in zip(range(1, len(fr["tiers"])), Fx):
        tn = [n for n in fr["nodes"] if tier_of(n) == t]
        for n in tn:
            m.add_node_load(n, "FX", F / len(tn), case="EX")
            m.add_node_load(n, "FZ", F / len(tn), case="EZ")
    cases = sorted({c for c, *_ in ldd["line"]} | {c for c, *_ in ldd["node"]} | {"EX", "EZ"})
    for c in cases:                                   # one combination per primary case; combinations are
        m.add_load_combo(f"case:{c}", {c: 1.0})       # built by superposition (the analysis is linear)
    m.analyze(check_statics=False, sparse=True)
    line_w = defaultdict(lambda: defaultdict(float))
    for case, mem, w in ldd["line"]:
        if w == -1.0:
            sec = secs[fam[fr_by_name(fr)[mem]["group"]]][sizes[fr_by_name(fr)[mem]["group"]]]
            line_w[mem]["D"] += sec.A * mat.rho * G
        else:
            line_w[mem][case] += w
    combos = ld.combos(seis["SDS"])
    return m, {"seismic_W": W, "seismic_V": V, "combos": combos, "cases": cases, "line_w": line_w,
               "tier_weights": dict(weights)}


_BYNAME = {}


def fr_by_name(fr):
    key = id(fr)
    if key not in _BYNAME:
        _BYNAME.clear()
        _BYNAME[key] = {m["name"]: m for m in fr["members"]}
    return _BYNAME[key]


XI = np.array([0.0, 0.25, 0.5, 0.75, 1.0])


def case_results(m: FEModel3D, fr: dict, info: dict) -> dict:
    """Internal forces at five stations per member and primary case: array (case, quantity, station),
    quantities = axial (+compression), Vy, Vz, Mz, My. Rebuilt from PyNite's local end forces plus the
    member's uniform load (all member loads here are uniform, global -Y); calibrated against
    PyNite's axial/shear/moment functions in tests/test_structure.py."""
    out = {}
    for mb in fr["members"]:
        pm = m.members[mb["name"]]
        L = pm.L()
        R = pm.T()[:3, :3]
        x = XI * L
        arr = np.zeros((len(info["cases"]), 5, len(XI)))
        for ci, c in enumerate(info["cases"]):
            f = pm.f(f"case:{c}").flatten()
            wl = R @ np.array([0.0, -info["line_w"][mb["name"]].get(c, 0.0), 0.0])
            arr[ci, 0] = f[0] + wl[0] * x
            arr[ci, 1] = f[1] + wl[1] * x
            arr[ci, 2] = f[2] + wl[2] * x
            arr[ci, 3] = f[5] - f[1] * x - wl[1] * x * x / 2
            arr[ci, 4] = -f[4] - f[2] * x - wl[2] * x * x / 2
        out[mb["name"]] = arr
    return out


def factors(info: dict, f: dict) -> np.ndarray:
    return np.array([f.get(c, 0.0) for c in info["cases"]])


def forces_for(arr: np.ndarray, fv: np.ndarray) -> dict:
    X = np.tensordot(fv, arr, axes=1)
    return {"Pc": max(0.0, X[0].max()), "Pt": max(0.0, -X[0].min()), "Mz": np.abs(X[3]).max(),
            "My": np.abs(X[4]).max(), "V": max(np.abs(X[1]).max(), np.abs(X[2]).max())}


def compression_limits(sec, mat, mb, R: dict, info: dict, delta0_L: float = 0.001) -> tuple[float, str]:
    """ASCE 74 limits on compression members (columns, braces), as utilisation ratios:
    slenderness KL/r <= 1.4 sqrt(E_L A / P_D), with P_D the sustained unfactored load D + F (the fill's
    water hold-up is permanent in operation, so it is treated as dead load for this creep-related limit),
    and the serviceability check Ps <= phi_0 Pe <= 0.3 F_L^c A under D+F+L. Beams return 0."""
    if mb["kind"] == "beam":
        return 0.0, ""
    PD = forces_for(R[mb["name"]], factors(info, {"D": 1.0, "F": 1.0}))["Pc"]
    Ps = forces_for(R[mb["name"]], factors(info, {"D": 1.0, "F": 1.0, "L": 1.0}))["Pc"]
    _, KLr, lim = frp.slenderness_ok(sec, mat, mb["L"], PD)
    ur_s = KLr / lim if math.isfinite(lim) else 0.0
    _, ur_v = frp.serviceability_ok(sec, mat, mb["L"], Ps, delta0_L)
    return (ur_s, "slenderness (ASCE 74)") if ur_s >= ur_v else (ur_v, "service compression (ASCE 74)")


def check_all(fr, R: dict, sizes, fam, secs, mat, info) -> dict:
    res = {}
    fvs = [(c, factors(info, c["f"])) for c in info["combos"]]
    for mb in fr["members"]:
        sec = secs[fam[mb["group"]]][sizes[mb["group"]]]
        caps = frp.capacities(sec, mat, mb["L"])
        worst = None
        for c, fv in fvs:
            f = forces_for(R[mb["name"]], fv)
            for P in (f["Pt"], -f["Pc"]):
                r = frp.check_member(sec, mat, mb["L"], {"P": P, "Mz": f["Mz"], "My": f["My"], "V": f["V"]}, c["lam"], caps=caps)
                if worst is None or r["UR"] > worst["UR"]:
                    worst = {**r, "combo": c["name"], "lam": c["lam"], **f}
        ur_c, why = compression_limits(sec, mat, mb, R, info)
        if ur_c > worst["UR"]:
            worst.update(UR=ur_c, governs=why, combo="D (+F+L) service")
        res[mb["name"]] = worst
    return res


def required_index(group, fr, R, start, fam, secs, mat, info) -> int:
    """Smallest section of the group's family whose UR <= 1 for every member under the forces of the
    current analysis (forces then change with stiffness, so design() re-analyses until stable)."""
    fvs = [(c, factors(info, c["f"])) for c in info["combos"]]
    members = [mb for mb in fr["members"] if mb["group"] == group]
    forces = {mb["name"]: [(c["lam"], forces_for(R[mb["name"]], fv)) for c, fv in fvs] for mb in members}
    family = secs[fam[group]]
    for idx in range(start + 1, len(family)):
        sec = family[idx]
        ok = True
        for mb in members:
            caps = frp.capacities(sec, mat, mb["L"])
            if compression_limits(sec, mat, mb, R, info)[0] > 1.0:
                ok = False
                break
            for lam, f in forces[mb["name"]]:
                for P in (f["Pt"], -f["Pc"]):
                    if frp.check_member(sec, mat, mb["L"], {"P": P, "Mz": f["Mz"], "My": f["My"], "V": f["V"]},
                                        lam, caps=caps)["UR"] > 1.0:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            return idx
    return len(family) - 1


def design(d: dict, b, s: dict, max_iter: int = 8, log=print) -> dict:
    st = s["structure"]
    lib = frp.library()
    T_service = max(b.T_hot, d["thermal"]["selected"]["T_air_out"])
    mat = frp.end_use_material(lib, st.get("frp_material", "vinyl_ester_generic"), wet=True, T_service_C=T_service)
    fam, secs = _section_set(lib)
    fr = framing(d, s)
    ldd = build_loads(d, b, s, fr, mat)
    seis = ld.seismic_coefficients(s["loads"]["seismic"], d["geom"].z["fan_deck"] - fr["tiers"][0][1])
    sizes = dict(START)
    for g in GROUPS:
        sizes[g] = min(sizes[g], len(secs[fam[g]]) - 1)
    hist = []
    for it in range(max_iter):
        t0 = time.time()
        m, info = analyse(fr, ldd, sizes, fam, secs, mat, seis, s)
        R = case_results(m, fr, info)
        res = check_all(fr, R, sizes, fam, secs, mat, info)
        gmax = defaultdict(float)
        for name, r in res.items():
            gmax[fr_by_name(fr)[name]["group"]] = max(gmax[fr_by_name(fr)[name]["group"]], r["UR"])
        hist.append({"iter": it, "sizes": {g: secs[fam[g]][sizes[g]].name for g in GROUPS},
                     "UR": dict(gmax), "s": time.time() - t0})
        log(f"[structure] iter {it}: " + ", ".join(f"{g} {secs[fam[g]][sizes[g]].name} UR {gmax[g]:.2f}" for g in GROUPS if g in gmax)
            + f"  ({time.time() - t0:.0f} s)")
        bump = [g for g in GROUPS if gmax.get(g, 0) > 1.0 and sizes[g] < len(secs[fam[g]]) - 1]
        if not bump:
            break
        for g in bump:                                 # jump to the smallest section passing the current forces
            sizes[g] = required_index(g, fr, R, sizes[g], fam, secs, mat, info)
    return finish(d, b, s, fr, ldd, m, info, R, res, sizes, fam, secs, mat, seis, hist)


def finish(d, b, s, fr, ldd, m, info, R, res, sizes, fam, secs, mat, seis, hist) -> dict:
    st = s["structure"]
    byname = fr_by_name(fr)
    groups = {}
    for g in GROUPS:
        mem = [n for n, mb in byname.items() if mb["group"] == g]
        if not mem:
            continue
        worst = max(mem, key=lambda n: res[n]["UR"])
        sec = secs[fam[g]][sizes[g]]
        groups[g] = {"section": sec.name, "family": sec.family, "count": len(mem), "UR_max": res[worst]["UR"],
                     "governing_member": worst, "governs": res[worst]["governs"], "combo": res[worst]["combo"],
                     "kg_per_m": sec.mass_per_m(mat.rho), "A_mm2": sec.A * 1e6, "t_mm": sec.t * 1e3,
                     "d_mm": sec.d * 1e3, "bf_mm": sec.bf * 1e3}
    # ASCE 74 slenderness and serviceability compression (unfactored dead load / SLS D+F+L)
    slender, svc = [], []
    for n, mb in byname.items():
        if mb["kind"] == "beam":
            continue
        sec = secs[fam[mb["group"]]][sizes[mb["group"]]]
        PD = forces_for(R[n], factors(info, {"D": 1.0, "F": 1.0}))["Pc"]
        Ps = forces_for(R[n], factors(info, {"D": 1.0, "F": 1.0, "L": 1.0}))["Pc"]
        ok, KLr, lim = frp.slenderness_ok(sec, mat, mb["L"], PD)
        if not ok:
            slender.append((n, KLr, lim))
        ok2, ur2 = frp.serviceability_ok(sec, mat, mb["L"], Ps, st.get("out_of_straightness", 0.001))
        if not ok2:
            svc.append((n, ur2))
    # beam deflection under SLS D+F+L and frame drift under 0.6W
    lim_b = st.get("deflection_limit", 180)
    defl = []
    for n, mb in byname.items():
        if mb["kind"] == "beam":
            dmid = abs(sum(m.members[n].rel_deflection("dy", mb["L"] / 2, f"case:{c}") for c in ("D", "F", "L")
                           if c in info["cases"]))
            defl.append((dmid * lim_b / mb["L"], n, dmid))
    worst_defl = max(defl) if defl else (0, "", 0)
    td = len(fr["tiers"]) - 1
    deck = [n for n in fr["nodes"] if tier_of(n) == td]
    H = fr["tiers"][-1][1] - fr["tiers"][0][1]
    disp = lambda n, attr, f: sum(v * getattr(m.nodes[n], attr)[f"case:{c}"] for c, v in f.items() if c in info["cases"])
    drift = max(max(abs(disp(n, "DX", {"D": 1, "F": 1, "WX": 0.6})), abs(disp(n, "DZ", {"D": 1, "F": 1, "WZ": 0.6})))
                for n in deck)
    lim_d = st.get("drift_limit", 150)
    # connections per group
    conns = {}
    for g, gi in groups.items():
        if g == "column":
            continue
        mem = [n for n, mb in byname.items() if mb["group"] == g]
        sec = secs[fam[g]][sizes[g]]
        # demand / lambda maximised over the combinations, so the time effect of permanent loads is kept
        fvs = [(c["lam"], factors(info, c["f"])) for c in info["combos"]]
        if g == "brace":
            F, F_lam = 0.0, 0.0
            for n in mem:
                for lam, fv in fvs:
                    f = forces_for(R[n], fv)
                    F = max(F, f["Pt"], f["Pc"])
                    F_lam = max(F_lam, max(f["Pt"], f["Pc"]) / lam)
            c = frp.bolted(F_lam, 2 * sec.t, sec.bf, 1.0, mat, st["fastener_material"].split()[0], planes=2)
            conns[g] = {"type": "brace through-bolted to a 12 mm FRP gusset (double shear)", "force_kN": F / 1e3,
                        "force_over_lambda_kN": F_lam / 1e3, **c}
        else:
            V, V_lam = 0.0, 0.0
            for n in mem:
                for lam, fv in fvs:
                    v = forces_for(R[n], fv)["V"]
                    V, V_lam = max(V, v), max(V_lam, v / lam)
            c = frp.bolted(V_lam, sec.t, sec.d - 2 * sec.t, 1.0, mat, st["fastener_material"].split()[0])
            conns[g] = {"type": "pair of FRP clip angles, beam web to column", "force_kN": V / 1e3,
                        "force_over_lambda_kN": V_lam / 1e3, **c}
    # base reactions
    base = [n for n in fr["nodes"] if tier_of(n) == 0]
    rx = {"max_down_kN": 0.0, "max_uplift_kN": 0.0, "max_shear_kN": 0.0}
    for c in info["combos"]:
        for n in base:
            fy, fx, fz = (sum(v * getattr(m.nodes[n], a)[f"case:{k}"] for k, v in c["f"].items() if k in info["cases"])
                          for a in ("RxnFY", "RxnFX", "RxnFZ"))
            rx["max_down_kN"] = max(rx["max_down_kN"], fy / 1e3)
            rx["max_uplift_kN"] = max(rx["max_uplift_kN"], -fy / 1e3)
            rx["max_shear_kN"] = max(rx["max_shear_kN"], math.hypot(fx, fz) / 1e3)
    viol = [f"{g}: UR {gi['UR_max']:.2f} with the largest {gi['family']} section" for g, gi in groups.items() if gi["UR_max"] > 1.0]
    viol += [f"{g} connection UR {c['UR']:.2f}" for g, c in conns.items() if c["UR"] > 1.0]
    if slender:
        viol.append(f"{len(slender)} members exceed the ASCE 74 slenderness limit (e.g. {slender[0][0]}: KL/r {slender[0][1]:.0f} > {slender[0][2]:.0f})")
    if svc:
        viol.append(f"{len(svc)} members exceed the ASCE 74 serviceability compression limit")
    if worst_defl[0] > 1.0:
        viol.append(f"beam deflection {worst_defl[2] * 1e3:.1f} mm exceeds L/{lim_b} ({worst_defl[1]})")
    if drift > H / lim_d:
        viol.append(f"drift {drift * 1e3:.1f} mm exceeds H/{lim_d}")
    return {"material": {"name": mat.name, "basis": mat.basis, "C_strength": mat.C_strength, "C_modulus": mat.C_modulus,
                         "E_L_GPa": mat.E_L / 1e9, "F_Lc_MPa": mat.F_Lc / 1e6, "F_Lt_MPa": mat.F_Lt / 1e6,
                         "T_service_C": max(b.T_hot, d["thermal"]["selected"]["T_air_out"])},
            "phi": frp.PHI, "phi_source": frp.PHI_SOURCE,
            "grid": {"xs": fr["xs"], "zs": fr["zs"], "tiers": fr["tiers"], "cells_modelled": fr["cells_modelled"]},
            "n_nodes": len(fr["nodes"]), "n_members": len(fr["members"]),
            "groups": groups, "connections": conns, "seismic": {**seis, "W_kN": info["seismic_W"] / 1e3, "V_kN": info["seismic_V"] / 1e3},
            "wind": {"V_m_s": s["loads"]["wind_speed_m_s"], "exposure": s["loads"]["exposure"],
                     "qz_deck_Pa": ld.qz(d["geom"].z["fan_deck"], s["loads"]["wind_speed_m_s"], s["loads"]["exposure"],
                                         s["loads"].get("Kd", 0.90), z_ground=s["site"]["altitude_m"])},
            "equipment_kg_per_cell": ldd["m_eq_kg"], "stack_kg_per_cell": ldd["m_stack_kg"],
            "deflection": {"worst_member": worst_defl[1], "mid_mm": worst_defl[2] * 1e3, "ratio_to_limit": worst_defl[0],
                           "limit": f"L/{lim_b}"},
            "drift": {"mm": drift * 1e3, "limit_mm": H / lim_d * 1e3}, "base_reactions": rx,
            "slenderness_failures": len(slender), "serviceability_failures": len(svc),
            "iterations": hist, "violations": viol, "members": fr["members"], "sizes": sizes,
            "_sections": {g: secs[fam[g]][sizes[g]] for g in GROUPS}, "_mat": mat, "_fr": fr, "_res": res}
