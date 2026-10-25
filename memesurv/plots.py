"""Charts for the write-up. One idea per chart, sized for LinkedIn (16:9)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3de"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # fixed order: blue, orange, aqua

HOUR_TICKS = [1 / 60, 5 / 60, 1, 6, 24, 72, 168]
HOUR_LABELS = ["1m", "5m", "1h", "6h", "24h", "3d", "7d"]


def _style(ax, title, subtitle=None):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=10, length=0, pad=6)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig = ax.figure
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.06, 0.95, title, fontsize=15, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.06, 0.885, subtitle, fontsize=10.5, color=INK_2, va="top")


def _footer(fig, note, synthetic):
    fig.text(0.06, 0.02, note, fontsize=8.5, color=INK_2, va="bottom", linespacing=1.4)
    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC TEST DATA — NOT REAL RESULTS", fontsize=22,
                 color="#e34948", alpha=0.25, ha="center", va="center", rotation=18,
                 fontweight="bold")


def _save(fig, out):
    """Save, then palette-quantise (48 colours) to keep PNGs small for the repo."""
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    try:
        from PIL import Image
        Image.open(out).convert("RGB").quantize(colors=48).save(out, optimize=True)
    except Exception:
        pass


def _fmt_h(h):
    if not np.isfinite(h):
        return "> 7d"
    if h < 1:
        return f"{h * 60:.0f} min"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} days"


def _new():
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.subplots_adjust(left=0.09, right=0.84, top=0.80, bottom=0.21)
    return fig, ax


def plot_cif(cif: pd.DataFrame, n: int, out: str, synthetic=False, source=""):
    fig, ax = _new()
    t = cif["time"].clip(lower=1 / 120)
    ax.step(t, cif["cif_dead"] * 100, where="post", color=SERIES[0], lw=2)
    ax.step(t, cif["cif_grad"] * 100, where="post", color=SERIES[1], lw=2)
    ax.set_xscale("log")
    ax.set_xticks(HOUR_TICKS, HOUR_LABELS)
    ax.set_xlim(1 / 120, 168)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of all launches", color=INK_2, fontsize=10)
    ax.set_xlabel("Time since launch (log scale)", color=INK_2, fontsize=10)
    last = cif.iloc[-1]
    ax.text(170, last["cif_dead"] * 100, f"Dead  {last['cif_dead']:.1%}", color=INK,
            fontsize=10, va="center", ha="left")
    ax.text(170, max(last["cif_grad"] * 100, 3), f"Graduated  {last['cif_grad']:.2%}",
            color=INK, fontsize=10, va="center", ha="left")
    for h in (1, 24):
        v = cif[cif["time"] <= h]["cif_dead"]
        if len(v):
            ax.plot([h], [v.iloc[-1] * 100], "o", ms=6, color=SERIES[0],
                    markeredgecolor=SURFACE, markeredgewidth=2)
            ax.annotate(f"{v.iloc[-1]:.0%} by {'1h' if h == 1 else '24h'}",
                        (h, v.iloc[-1] * 100), xytext=(-8, 10), textcoords="offset points",
                        ha="right", fontsize=9.5, color=INK)
    _style(ax, "How fast do pump.fun memecoins die?",
           f"Cumulative incidence of death vs graduation, n = {n:,} launches")
    _footer(fig, "Dead = no curve trade in last 24h of a 7-day window. Aalen–Johansen (graduation = competing risk).\n"
                 + source, synthetic)
    _save(fig, out)


def plot_km_groups(curves: dict, labels: dict, p_value: float, out: str,
                   synthetic=False, source="",
                   title="Does the creator selling early shorten a token's life?",
                   subtitle="Survival of tokens alive at 5 minutes, by creator behaviour"):
    fig, ax = _new()
    medians = []
    for i, (g, c) in enumerate(sorted(curves.items())):
        col = SERIES[i]
        t = np.concatenate([[0], c["time"].to_numpy()])
        s = np.concatenate([[1], c["surv"].to_numpy()]) * 100
        ax.step(t, s, where="post", color=col, lw=2)
        lo = np.concatenate([[1], c["lo"].to_numpy()]) * 100
        hi = np.concatenate([[1], c["hi"].to_numpy()]) * 100
        ax.fill_between(t, lo, hi, step="post", color=col, alpha=0.12, lw=0)
        below = c.loc[c["surv"] <= 0.5, "time"]
        med = below.iloc[0] if len(below) else np.nan
        medians.append(f"{labels[g].lower()} {_fmt_h(med)}")
        ax.plot([], [], color=col, lw=2, label=labels[g])
    ax.set_xscale("log")
    ax.set_xlim(1 / 60, 168)
    ax.set_xticks(HOUR_TICKS[:1] + HOUR_TICKS[2:], HOUR_LABELS[:1] + HOUR_LABELS[2:])
    ax.set_ylim(0, 100)
    ax.set_ylabel("% still trading", color=INK_2, fontsize=10)
    ax.set_xlabel("Time since the 5-minute mark (log scale)", color=INK_2, fontsize=10)
    ax.text(0.98, 0.70, "Median life:\n" + "\n".join(medians), transform=ax.transAxes,
            ha="right", va="top", fontsize=9.5, color=INK)
    ax.legend(frameon=False, loc="upper right", fontsize=9.5, labelcolor=INK)
    ptxt = "p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"
    _style(ax, title, f"{subtitle} (log-rank {ptxt})")
    _footer(fig, "Kaplan–Meier with 95% CI; graduation treated as censoring. " + source, synthetic)
    _save(fig, out)


def plot_forest(table: pd.DataFrame, labels: dict, out: str, synthetic=False, source=""):
    t = table.sort_values("HR").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.subplots_adjust(left=0.40, right=0.95, top=0.80, bottom=0.19)
    y = np.arange(len(t))
    risk = t["HR"] > 1
    cols = np.where(risk, SERIES[1], SERIES[0])
    ax.hlines(y, t["HR_lo"], t["HR_hi"], color=cols, lw=2)
    ax.scatter(t["HR"], y, s=55, color=cols, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.axvline(1, color=INK_2, lw=1, ls="--")
    ax.set_xscale("log")
    lo, hi = t["HR_lo"].min(), t["HR_hi"].max()
    cands = [0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3, 4, 6, 10]
    ticks = [v for v in cands if lo * 0.9 <= v <= hi * 1.1] or [1]
    if 1 not in ticks:
        ticks.append(1)
    ax.set_xticks(sorted(ticks), [f"{v:g}×" for v in sorted(ticks)])
    ax.minorticks_off()
    ax.set_yticks(y, [labels.get(f, f) for f in t["feature"]], fontsize=9.5, color=INK)
    ax.set_xlabel("Hazard ratio for dying (log scale) — right of 1 = dies faster",
                  color=INK_2, fontsize=10)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    _style(ax, "What predicts a memecoin's death?",
           "Cause-specific Cox model, 95% CI. Continuous features per 1 SD.")
    ax.grid(axis="y", visible=False)
    _footer(fig, source, synthetic)
    _save(fig, out)


def plot_daily(daily: pd.DataFrame, out: str, synthetic=False, source=""):
    daily = daily.copy()
    daily["day"] = pd.to_datetime(daily["day"])
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.5), dpi=150, sharex=True)
    fig.subplots_adjust(left=0.10, right=0.95, top=0.80, bottom=0.14, hspace=0.35)
    a1.bar(daily["day"], daily["launches"] / 1000, color=SERIES[0], width=0.8)
    a1.set_ylabel("Launches (k)", color=INK_2, fontsize=9.5)
    a2.plot(daily["day"], daily["graduation_rate"] * 100, color=SERIES[1], lw=2)
    a2.set_ylabel("Graduated %", color=INK_2, fontsize=9.5)
    a2.set_ylim(bottom=0)
    import matplotlib.dates as mdates
    a2.xaxis.set_major_locator(mdates.MonthLocator())
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    for a in (a1, a2):
        a.set_facecolor(SURFACE)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a.spines[s].set_color(GRID)
        a.tick_params(colors=INK_2, labelsize=9, length=0)
        a.grid(axis="y", color=GRID, linewidth=0.8)
        a.set_axisbelow(True)
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.06, 0.95, "30–55k launches a day, 2–4% graduate", fontsize=15,
             fontweight="bold", color=INK, va="top")
    fig.text(0.06, 0.885, "Daily pump.fun launches and graduations (bonding curve filled), 13 Aug – 20 Oct 2026",
             fontsize=10.5, color=INK_2, va="top")
    _footer(fig, source, synthetic)
    _save(fig, out)
