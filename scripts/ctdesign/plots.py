"""Result plots as SVG (matplotlib, Agg backend)."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import psychro as ps  # noqa: E402

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "svg.fonttype": "none"})


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path)
    fig.savefig(str(path)[:-4] + ".png", dpi=110)
    plt.close(fig)


def demand_supply(t: dict, path):
    sel, ch = t["selected"], t["selected"]["_char"]
    fig, ax = plt.subplots(figsize=(7, 5))
    for fam in t["demand_family"]:
        ax.plot(fam["LG"], fam["Me"], lw=1.6 if abs(fam["approach"] - t["design_check"]["approach"]) < 0.3 else 0.9,
                label=f"demand, approach {fam['approach']:.1f} K")
    lg = np.linspace(0.4, min(3.0, t["LG_max"]), 100)
    ax.plot(lg, ch(lg), "k-", lw=1.8, label=f"tower supply ({ch.fill_type}, {ch.depth:.2f} m + rain zone)")
    ax.plot(lg, ch.Me_fill(lg), "k--", lw=0.8, label="fill only")
    ax.plot([sel["LG"]], [sel["Me_total"]], "ro", label=f"design L/G {sel['LG']:.3f}, Me {sel['Me_total']:.3f}")
    ax.axvline(t["LG_max"], color="grey", ls=":", lw=0.8)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("L/G (kg water / kg dry air)"); ax.set_ylabel("KaV/L (Merkel number)")
    ax.set_ylim(0.3, 5); ax.legend(fontsize=7)
    ax.set_title("Demand vs tower characteristic (CTI)")
    _save(fig, path)


def performance(t: dict, path):
    rows = t["performance"]
    flows = sorted({r["flow_pct"] for r in rows})
    fig, axs = plt.subplots(1, len(flows), figsize=(4 * len(flows), 4.2), sharey=True)
    for ax, fq in zip(np.atleast_1d(axs), flows):
        for rp in sorted({r["range_pct"] for r in rows}):
            d = [r for r in rows if r["flow_pct"] == fq and r["range_pct"] == rp]
            ax.plot([r["T_wb"] for r in d], [r["T_cold"] for r in d], marker=".", label=f"{rp:.0f} % range")
        ax.set_title(f"{fq:.0f} % design flow"); ax.set_xlabel("wet-bulb (C)")
        ax.legend(fontsize=7)
    np.atleast_1d(axs)[0].set_ylabel("cold water (C)")
    fig.suptitle("Performance curves (constant air mass flow)")
    _save(fig, path)


def pressure_breakdown(d: dict, path):
    rows = d["air"]["rows"]
    fn = d["fan"]
    names = [r["item"] for r in rows] + ["buoyancy credit", "stack loss", "exit velocity pressure"]
    vals = [r["dP"] for r in rows] + [-d["air"]["buoyancy_credit"], fn["dP_stack"], fn["vp_exit"]]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(names[::-1], vals[::-1], color=["#c44" if v < 0 else "#47a" for v in vals[::-1]])
    for i, v in enumerate(vals[::-1]):
        ax.text(v, i, f" {v:.1f}", va="center", fontsize=7)
    ax.set_xlabel("Pa")
    ax.set_title(f"Fan total pressure {fn['dP_total']:.0f} Pa (static {fn['dP_fan_static']:.0f} Pa)")
    _save(fig, path)


def optimisation(df, sel, path):
    ok = df[df.feasible.astype(bool)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    sc = a1.scatter(ok.capex / 1e3, ok.energy_kW, c=ok.TPC / 1e6, cmap="viridis", s=14)
    a1.plot(sel.capex / 1e3, sel.energy_kW, "r*", ms=14, label="selected")
    a1.set_xlabel("capital cost (k)"); a1.set_ylabel("fan + pump power (kW)"); a1.legend()
    fig.colorbar(sc, ax=a1, label="total present cost (M)")
    for depth, g in ok.groupby("depth"):
        best = g.groupby("cells").TPC.min()
        a2.plot(best.index, best.values / 1e6, "o-", label=f"fill {depth} m")
    a2.set_xlabel("cells"); a2.set_ylabel("best total present cost (M)"); a2.legend(fontsize=7)
    a1.set_title("Feasible candidates"); a2.set_title("Cost vs number of cells")
    _save(fig, path)


def structure_ur(st: dict, path):
    """Isometric wireframe of the analysed block, members coloured by utilisation ratio."""
    fr, res = st["_fr"], st["_res"]
    fig = plt.figure(figsize=(9, 6))
    ax = fig.add_subplot(111, projection="3d")
    cmap = plt.get_cmap("RdYlGn_r")
    for mb in fr["members"]:
        (x1, y1, z1), (x2, y2, z2) = fr["nodes"][mb["i"]], fr["nodes"][mb["j"]]
        ur = res[mb["name"]]["UR"]
        ax.plot([x1, x2], [z1, z2], [y1, y2], color=cmap(min(ur, 1.0)), lw=0.6 if mb["kind"] == "brace" else 1.0)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=ax, shrink=0.6, label="utilisation ratio")
    ax.set_xlabel("X along row (m)"); ax.set_ylabel("Z across (m)"); ax.set_zlabel("elevation (m)")
    xs, zs = fr["xs"], fr["zs"]
    ax.set_box_aspect((xs[-1] - xs[0], zs[-1] - zs[0], fr["tiers"][-1][1] - fr["tiers"][0][1]))
    ax.view_init(elev=22, azim=-60)
    ax.set_title(f"FRP frame, {st['grid']['cells_modelled']} cell(s) analysed: {st['n_members']} members")
    _save(fig, path)


MODEL_COLOURS = {"Basin": ("#9e9e9e", 0.25), "Fill": ("#c8a165", 0.35), "Eliminators": ("#7fb3d5", 0.35),
                 "Distribution": ("#c2185b", 0.9), "Casing": ("#90a4ae", 0.12), "FanDeck": ("#607d8b", 0.4),
                 "FanStacks": ("#37474f", 0.35), "Mechanical": ("#ef6c00", 0.9), "Handrails": ("#fbc02d", 0.8)}


def model_preview(mesh_json, path, elev=24, azim=-58):
    """Isometric render of the FreeCAD model from its coarse tessellation (frame drawn as centrelines)."""
    import json
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    data = json.loads(open(mesh_json, encoding="utf-8").read())
    fig = plt.figure(figsize=(11, 7))
    ax = fig.add_subplot(111, projection="3d")
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for name, m in data.items():
        if name.startswith("_") or not m["f"]:
            continue
        col, alpha = next((v for k, v in MODEL_COLOURS.items() if name.startswith(k)), ("#888888", 0.3))
        v = np.asarray(m["v"], float)
        f = np.asarray(m["f"], int)
        ax.add_collection3d(Poly3DCollection(v[f], facecolor=col, edgecolor="none", alpha=alpha))
        lo, hi = np.minimum(lo, v.min(0)), np.maximum(hi, v.max(0))
    for p1, p2, mark in data.get("_members", []):
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], color="#1565c0" if mark != "BR1" else "#42a5f5", lw=0.5)
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(tuple(hi - lo))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title("FreeCAD model (preview of the STEP/FCStd)")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def poppe_profile(t: dict, P: float, path):
    pr = t["selected"]["_poppe_profile"]                 # Tw, w, ima, Me, Ta, sat, Lef
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4))
    a1.plot(pr[:, 3], pr[:, 0], label="water"); a1.plot(pr[:, 3], pr[:, 4], label="air dry-bulb")
    a1.set_xlabel("cumulative Poppe Me (bottom -> top)"); a1.set_ylabel("temperature (C)"); a1.legend()
    T = np.linspace(min(pr[:, 4].min(), pr[:, 0].min()) - 3, pr[:, 0].max() + 3, 100)
    a2.plot(T, ps.W_sat(T, P) * 1e3, "k-", lw=0.8, label="saturation")
    a2.plot(pr[:, 4], pr[:, 1] * 1e3, "b.-", label="air path")
    a2.set_xlabel("air temperature (C)"); a2.set_ylabel("W (g/kg)"); a2.legend()
    a1.set_title("Poppe: temperatures through the tower"); a2.set_title("Air path on the psychrometric chart")
    _save(fig, path)
