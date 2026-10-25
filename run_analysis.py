"""Run the full analysis.

    python run_analysis.py                     # uses data/token_level.csv (+ optional extras)
    python run_analysis.py --synthetic         # pipeline test on fake data (watermarked)

Optional inputs picked up automatically if present:
    data/population_summary.csv   (sql/04) -> headline numbers on all tokens
    data/daily_context.csv        (sql/05) -> context chart
Outputs: figures/*.png, results/summary.md, results/*.csv
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from memesurv import data, plots, survival, synthetic

ROOT = Path(__file__).resolve().parent
HORIZONS = {"5 min": 5 / 60, "1 hour": 1.0, "24 hours": 24.0, "7 days": 168.0}


def md_table(df: pd.DataFrame, floatfmt: dict | None = None) -> str:
    floatfmt = floatfmt or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                cells.append(format(v, floatfmt.get(c, ".3f")))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "token_level.csv"))
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--n-boot", type=int, default=300)
    args = ap.parse_args()

    figs, res_dir = ROOT / "figures", ROOT / "results"
    figs.mkdir(exist_ok=True)
    res_dir.mkdir(exist_ok=True)

    if args.synthetic:
        raw = synthetic.make()
        daily = synthetic.make_daily()
        pop = None
        source = "Synthetic data."
    else:
        raw = data.load(args.data)
        dp = ROOT / "data" / "daily_context.csv"
        pp = ROOT / "data" / "population_summary.csv"
        daily = pd.read_csv(dp) if dp.exists() else None
        pop_raw = pd.read_csv(pp) if pp.exists() else None
        pop = pop_raw.drop(columns=["day_start"], errors="ignore").sum(numeric_only=True) if pop_raw is not None else None
        source = "Data: Solana on-chain transfers, Coinbase CDP SQL API."
    syn = args.synthetic

    df_all = data.add_features(raw)
    if "mayhem" not in df_all.columns:
        df_all["mayhem"] = 0
    n_all = len(df_all)
    # Main models use standard launches; "Mayhem Mode" launches (2bn supply, different
    # curve mechanics) are reported separately.
    df = df_all[df_all["mayhem"] == 0].copy()
    n = len(df)
    out = []
    out.append("# Results" + (" — SYNTHETIC TEST RUN (do not publish)" if syn else ""))
    out.append(f"\nSample: **{n_all:,} tokens** ({n_all - n:,} Mayhem Mode, {n:,} standard) launched "
               f"{df['created_at'].min():%Y-%m-%d} to {df['created_at'].max():%Y-%m-%d}.\n")
    out.append("Outcome counts: " + ", ".join(
        f"{k} {v:,} ({v / n_all:.1%})" for k, v in df_all["outcome"].value_counts().items()) + "\n")

    # ---------- 1. competing-risks incidence on ALL sampled tokens
    cause = np.select([df_all["outcome"] == "dead", df_all["outcome"] == "graduated"], [1, 2], 0)
    cif = survival.cumulative_incidence(df_all["duration_hours"], cause)
    ci = survival.bootstrap_cif_ci(df_all["duration_hours"].to_numpy(), cause,
                                   list(HORIZONS.values()), n_boot=args.n_boot)
    rows = []
    for (label, h), (_, c) in zip(HORIZONS.items(), ci.iterrows()):
        v = survival.cif_at(cif, h)
        rows.append({"by": label,
                     "dead %": f"{v['cif_dead']:.1%} ({c['dead_lo']:.1%}–{c['dead_hi']:.1%})",
                     "graduated %": f"{v['cif_grad']:.2%} ({c['grad_lo']:.2%}–{c['grad_hi']:.2%})"})
    inc = pd.DataFrame(rows)
    inc.to_csv(res_dir / "incidence.csv", index=False)
    out.append("## 1. How fast they die (Aalen–Johansen, 95% bootstrap CI)\n")
    out.append(md_table(inc) + "\n")
    plots.plot_cif(cif, n_all, str(figs / "fig1_death_vs_graduation.png"), syn, source)

    # standard vs Mayhem Mode
    rows = []
    for lab, sub in (("Standard", df_all[df_all["mayhem"] == 0]), ("Mayhem Mode", df_all[df_all["mayhem"] == 1])):
        if len(sub) == 0:
            continue
        cs = np.select([sub["outcome"] == "dead", sub["outcome"] == "graduated"], [1, 2], 0)
        cc = survival.cumulative_incidence(sub["duration_hours"], cs)
        v1, v24, v7 = (survival.cif_at(cc, h) for h in (1, 24, 168))
        rows.append({"launch type": lab, "n": f"{len(sub):,}", "dead by 1h": f"{v1['cif_dead']:.1%}",
                     "dead by 24h": f"{v24['cif_dead']:.1%}", "graduated by 7d": f"{v7['cif_grad']:.2%}"})
    out.append("### Standard vs Mayhem Mode launches\n")
    out.append(md_table(pd.DataFrame(rows)) + "\n")

    if pop is not None:
        N = pop["n_tokens"]
        out.append("### Full population check (no sampling, sql/04)\n")
        out.append(f"- Tokens: {int(N):,}\n- Graduated: {pop['n_graduated'] / N:.2%}\n"
                   f"- Dead within 5 min: {pop['n_dead_within_5m'] / N:.1%}, 1h: "
                   f"{pop['n_dead_within_1h'] / N:.1%}, 24h: {pop['n_dead_within_24h'] / N:.1%}, "
                   f"7d: {pop['n_dead'] / N:.1%}\n"
                   f"- At most one trade ever: {pop['n_at_most_one_trade'] / N:.1%}\n"
                   f"- Graduated within 1h: {pop['n_grad_within_1h'] / N:.2%}, within 24h: "
                   f"{pop['n_grad_within_24h'] / N:.2%}\n")

    # ---------- 2. landmark cohort: alive at 5 minutes
    lm = data.landmark(df)
    out.append(f"## 2. Standard tokens alive at 5 minutes: {len(lm):,} ({len(lm) / n:.1%} of standard launches)\n")
    lm["trader_group"] = pd.cut(lm["n_traders_5m"], [-1, 5, 20, np.inf], labels=[0, 1, 2]).astype(int)
    curves, chi2, p = survival.km_by_group(lm, "t_lm", "dead", "trader_group")
    plots.plot_km_groups(curves, {0: "0–5 traders", 1: "6–20 traders", 2: "21+ traders"}, p,
                         str(figs / "fig2_traders.png"), syn, source,
                         title="Real early demand is what keeps a memecoin alive",
                         subtitle="Survival of tokens alive at 5 min, by unique traders in the first 5 min")
    share = lm["trader_group"].value_counts(normalize=True).sort_index()
    out.append(f"Unique traders in first 5 min: 0–5 = {share.get(0, 0):.0%}, 6–20 = {share.get(1, 0):.0%}, "
               f"21+ = {share.get(2, 0):.0%} of the cohort. Log-rank chi² = {chi2:.1f}, p = {fmt_p(p)}\n")
    for g, c in sorted(curves.items()):
        below = c.loc[c["surv"] <= 0.5, "time"]
        out.append(f"- {['0–5', '6–20', '21+'][g]} traders: median remaining life {below.iloc[0] if len(below) else float('nan'):.2f} h")
    out.append("")
    _, chi2b, pb = survival.km_by_group(lm, "t_lm", "dead", "dev_sold_5m")
    out.append(f"Creator sold within 5 min vs held: log-rank chi² = {chi2b:.1f}, p = {fmt_p(pb)} "
               f"(share of the cohort where the creator sold: {lm['dev_sold_5m'].mean():.0%})\n")

    # ---------- 3. Cox model
    feats = list(data.FEATURES)
    lm_z, _ = data.standardise(lm, feats)
    vif = survival.vif_table(lm_z[feats])
    cox, cox_res = survival.cox_cause_specific(lm_z, feats)
    ph = survival.ph_assumption_check(cox_res, lm_z, feats)
    cox_out = cox.merge(ph.rename(columns={"p": "PH_p", "rho": "PH_rho"}), on="feature") \
                 .merge(vif, on="feature")
    cox_out.insert(1, "label", cox_out["feature"].map(data.FEATURES))
    cox_out.to_csv(res_dir / "cox_hazard_ratios.csv", index=False)
    plots.plot_forest(cox, data.FEATURES, str(figs / "fig3_hazard_ratios.png"), syn, source)
    show = cox_out[["label", "HR", "HR_lo", "HR_hi", "p", "PH_p", "VIF"]].copy()
    show["p"] = show["p"].map(fmt_p)
    show["PH_p"] = show["PH_p"].map(lambda x: "n/a" if pd.isna(x) else fmt_p(x))
    out.append("## 3. What predicts death (cause-specific Cox PH, standardised features)\n")
    out.append(md_table(show, {"HR": ".2f", "HR_lo": ".2f", "HR_hi": ".2f", "VIF": ".1f"}) + "\n")
    out.append("HR > 1 = dies faster. PH_p < 0.05 means the effect changes over time "
               "(interpret as an average effect). VIF > 5 = collinearity worth flagging.\n")

    # ---------- 4. out-of-sample prediction
    logit, m = survival.logistic_24h(lm_z, feats)
    logit.insert(1, "label", logit["feature"].map(data.FEATURES))
    logit.to_csv(res_dir / "logit_24h_odds_ratios.csv", index=False)
    out.append("## 4. Can the first 5 minutes predict death within 24h?\n")
    out.append(f"Logistic regression, 70/30 split. Base rate {m['base_rate']:.1%}. "
               f"AUC test **{m['auc_test']:.3f}** (train {m['auc_train']:.3f}), "
               f"n_test = {m['n_test']:,}.\n")
    lshow = logit[["label", "OR", "OR_lo", "OR_hi", "p"]].copy()
    lshow["p"] = lshow["p"].map(fmt_p)
    out.append(md_table(lshow, {"OR": ".2f", "OR_lo": ".2f", "OR_hi": ".2f"}) + "\n")

    if daily is not None:
        plots.plot_daily(daily, str(figs / "fig4_daily_launches.png"), syn, source)

    (res_dir / "summary.md").write_text("\n".join(out))
    print("\n".join(out))
    print(f"\nFigures -> {figs}\nTables  -> {res_dir}")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
