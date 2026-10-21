"""Synthetic data with the same schema as sql/01_token_level.sql.

Only for testing the pipeline (CI and tests).
Numbers produced from this data mean NOTHING and must never be published.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def make(n: int = 20000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    created = pd.Timestamp("2026-09-01", tz="UTC") + pd.to_timedelta(
        rng.uniform(0, 7 * 24 * 3600, n), unit="s")
    traders = rng.negative_binomial(1, 0.15, n)
    buy = rng.gamma(1.0, 0.6, n) * (traders + 1) * 0.3
    sell = buy * rng.beta(2, 5, n)
    dev_buy = rng.exponential(0.8, n)
    dev_sold = rng.random(n) < 0.25
    same_slot = rng.poisson(0.8, n)
    top10 = np.clip(rng.beta(4, 3, n), 0, 1)
    serial = rng.negative_binomial(1, 0.3, n)
    hour = created.hour.to_numpy()

    # linear predictor for the death hazard (true effects for the test)
    lp = (-0.35 * np.log1p(traders) - 0.25 * np.log1p(buy) + 1.0 * dev_sold
          + 0.25 * np.log1p(serial) + 0.6 * top10 + 0.15 * np.log1p(same_slot))
    scale = 3.0 * np.exp(-lp)                     # hours
    t_death = scale * rng.weibull(0.45, n)
    instant = rng.random(n) < 0.45                # never really trades
    t_death[instant] = rng.uniform(0, 3 / 60, instant.sum())
    traders[instant] = 0
    buy[instant] = sell[instant] = 0

    g_score = np.log1p(traders) + np.log1p(buy) - dev_sold
    grad_p = 1 / (1 + np.exp(-(g_score - 7.0)))
    grads = (rng.random(n) < grad_p) & ~instant
    t_grad = rng.lognormal(0.0, 1.2, n)

    follow, dead_after = 168.0, 24.0
    outcome = np.where(grads & (t_grad < t_death), "graduated",
                       np.where(t_death <= follow - dead_after, "dead", "censored"))
    dur = np.where(outcome == "graduated", t_grad,
                   np.where(outcome == "dead", t_death, follow))

    return pd.DataFrame({
        "mint": [f"SYN{i:07d}pump" for i in range(n)],
        "name": "synthetic", "symbol": "SYN",
        "creator": [f"C{c}" for c in rng.integers(0, n // 3, n)],
        "created_at": created,
        "launch_hour_utc": hour,
        "launch_dow": created.dayofweek.to_numpy() + 1,
        "outcome": outcome,
        "duration_hours": dur,
        "n_trades_5m": traders * 2,
        "n_traders_5m": traders,
        "buy_tokens_5m": buy * 3e7,
        "sell_tokens_5m": sell * 3e7,
        "net_sol_5m": np.clip(buy - sell, 0, None),
        "dev_buy_sol": dev_buy,
        "dev_sold_5m": dev_sold.astype(int),
        "same_slot_buyers": same_slot,
        "mcap_5m_sol": 28 + buy - sell,
        "top10_share_5m": top10,
        "creator_prior_launches_30d": serial,
    })


def make_daily(days: int = 120, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = pd.date_range(end=pd.Timestamp("2026-10-20"), periods=days)
    launches = (25000 + 5000 * np.sin(np.arange(days) / 9) + rng.normal(0, 2000, days)).astype(int)
    rate = np.clip(0.008 + 0.002 * np.sin(np.arange(days) / 15) + rng.normal(0, 0.0008, days), 0.001, None)
    return pd.DataFrame({"day": d.date, "launches": launches,
                         "graduated": (launches * rate).astype(int), "graduation_rate": rate})
