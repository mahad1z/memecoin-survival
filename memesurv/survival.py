"""Survival, competing-risks and classification models."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import SurvfuncRight, survdiff
from statsmodels.stats.outliers_influence import variance_inflation_factor


# ---------------------------------------------------------------- competing risks
def cumulative_incidence(time: np.ndarray, cause: np.ndarray) -> pd.DataFrame:
    """Aalen-Johansen cumulative incidence for two competing events.

    cause: 1 = dead, 2 = graduated, 0 = censored.
    Returns a step table: time, cif_dead, cif_grad, surv (still trading).
    """
    time = np.asarray(time, float)
    cause = np.asarray(cause, int)
    order = np.argsort(time, kind="mergesort")
    time, cause = time[order], cause[order]
    uniq = np.unique(time)
    n = len(time)
    # at-risk = everyone whose time >= t
    idx_first = np.searchsorted(time, uniq, side="left")
    at_risk = n - idx_first
    d1 = pd.Series(cause == 1).groupby(time).sum().reindex(uniq).to_numpy(float)
    d2 = pd.Series(cause == 2).groupby(time).sum().reindex(uniq).to_numpy(float)
    hazard_all = (d1 + d2) / at_risk
    surv = np.cumprod(1 - hazard_all)
    surv_prev = np.concatenate([[1.0], surv[:-1]])
    cif1 = np.cumsum(surv_prev * d1 / at_risk)
    cif2 = np.cumsum(surv_prev * d2 / at_risk)
    return pd.DataFrame({"time": uniq, "cif_dead": cif1, "cif_grad": cif2, "surv": surv})


def cif_at(cif: pd.DataFrame, t: float) -> pd.Series:
    """Value of the step functions at time t (last step <= t)."""
    sub = cif[cif["time"] <= t]
    if sub.empty:
        return pd.Series({"cif_dead": 0.0, "cif_grad": 0.0, "surv": 1.0})
    return sub.iloc[-1][["cif_dead", "cif_grad", "surv"]]


def bootstrap_cif_ci(time, cause, horizons, n_boot=300, seed=7):
    """Percentile bootstrap 95% CI for dead/grad incidence at each horizon."""
    rng = np.random.default_rng(seed)
    time = np.asarray(time, float)
    cause = np.asarray(cause, int)
    n = len(time)
    draws = {h: {"dead": [], "grad": []} for h in horizons}
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        c = cumulative_incidence(time[i], cause[i])
        for h in horizons:
            v = cif_at(c, h)
            draws[h]["dead"].append(v["cif_dead"])
            draws[h]["grad"].append(v["cif_grad"])
    rows = []
    for h in horizons:
        rows.append({
            "horizon_hours": h,
            "dead_lo": np.percentile(draws[h]["dead"], 2.5),
            "dead_hi": np.percentile(draws[h]["dead"], 97.5),
            "grad_lo": np.percentile(draws[h]["grad"], 2.5),
            "grad_hi": np.percentile(draws[h]["grad"], 97.5),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Kaplan-Meier
def km_by_group(df: pd.DataFrame, time_col: str, event_col: str, group_col: str):
    """KM curves per group (cause-specific: other outcomes censored) + log-rank test."""
    curves = {}
    for g, sub in df.groupby(group_col):
        sf = SurvfuncRight(sub[time_col].to_numpy(), sub[event_col].to_numpy())
        # pointwise 95% CI on the log scale
        with np.errstate(divide="ignore", invalid="ignore"):
            se_log = sf.surv_prob_se / sf.surv_prob
        lo = np.clip(sf.surv_prob * np.exp(-1.96 * se_log), 0, 1)
        hi = np.clip(sf.surv_prob * np.exp(1.96 * se_log), 0, 1)
        curves[g] = pd.DataFrame({"time": sf.surv_times, "surv": sf.surv_prob,
                                  "lo": np.nan_to_num(lo), "hi": np.nan_to_num(hi, nan=1.0)})
    chi2, p = survdiff(df[time_col].to_numpy(), df[event_col].to_numpy(),
                       df[group_col].to_numpy())
    return curves, chi2, p


# ---------------------------------------------------------------- Cox model
def vif_table(X: pd.DataFrame) -> pd.DataFrame:
    Xc = sm.add_constant(X, has_constant="add")
    vals = [variance_inflation_factor(Xc.values, i + 1) for i in range(X.shape[1])]
    return pd.DataFrame({"feature": X.columns, "VIF": vals})


def cox_cause_specific(df: pd.DataFrame, features: list[str], time_col="t_lm",
                       event_col="dead") -> tuple[pd.DataFrame, object]:
    """Cause-specific Cox PH for death (graduation treated as censoring).

    Features should already be standardised -> HR is per 1 SD (or 0->1 for flags).
    """
    model = PHReg(df[time_col].to_numpy(), df[features].to_numpy(),
                  status=df[event_col].to_numpy(), ties="efron")
    res = model.fit()
    ci = res.conf_int()
    table = pd.DataFrame({
        "feature": features,
        "HR": np.exp(res.params),
        "HR_lo": np.exp(ci[:, 0]),
        "HR_hi": np.exp(ci[:, 1]),
        "p": res.pvalues,
    })
    return table, res


def ph_assumption_check(res, df: pd.DataFrame, features: list[str],
                        time_col="t_lm", event_col="dead") -> pd.DataFrame:
    """Correlation of scaled-free Schoenfeld residuals with log time (Grambsch-Therneau style).

    A small p-value means the effect of that feature changes over time.
    """
    sr = res.schoenfeld_residuals
    ev = df[event_col].to_numpy() == 1
    t = np.log1p(df[time_col].to_numpy()[ev])
    rows = []
    for j, f in enumerate(features):
        r = sr[ev, j]
        ok = np.isfinite(r)
        if ok.sum() < 10:
            rows.append({"feature": f, "rho": np.nan, "p": np.nan})
            continue
        rho, p = stats.spearmanr(t[ok], r[ok])
        rows.append({"feature": f, "rho": rho, "p": p})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 24h classifier
def auc(y_true, score) -> float:
    """ROC AUC via the Mann-Whitney U statistic."""
    y_true = np.asarray(y_true)
    ranks = stats.rankdata(score)
    n1 = y_true.sum()
    n0 = len(y_true) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return (ranks[y_true == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def logistic_24h(df: pd.DataFrame, features: list[str], seed=42, test_frac=0.3):
    """P(dead on the curve within 24h of launch | alive at 5 min).

    Fit on a random 70% split, report odds ratios and out-of-sample AUC on 30%.
    """
    d = df.copy()
    d["y"] = ((d["dead"] == 1) & (d["duration_hours"] <= 24)).astype(int)
    rng = np.random.default_rng(seed)
    test = rng.random(len(d)) < test_frac
    Xtr = sm.add_constant(d.loc[~test, features], has_constant="add")
    Xte = sm.add_constant(d.loc[test, features], has_constant="add")
    res = sm.Logit(d.loc[~test, "y"], Xtr).fit(disp=False, maxiter=200)
    ci = res.conf_int()
    table = pd.DataFrame({
        "feature": features,
        "OR": np.exp(res.params[features].to_numpy()),
        "OR_lo": np.exp(ci.loc[features, 0].to_numpy()),
        "OR_hi": np.exp(ci.loc[features, 1].to_numpy()),
        "p": res.pvalues[features].to_numpy(),
    })
    p_test = res.predict(Xte)
    metrics = {
        "n_train": int((~test).sum()),
        "n_test": int(test.sum()),
        "base_rate": float(d["y"].mean()),
        "auc_test": float(auc(d.loc[test, "y"].to_numpy(), p_test.to_numpy())),
        "auc_train": float(auc(d.loc[~test, "y"].to_numpy(), res.predict(Xtr).to_numpy())),
    }
    return table, metrics
