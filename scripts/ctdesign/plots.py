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
