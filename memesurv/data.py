"""Load the Dune export and build the modelling table."""
from __future__ import annotations

import numpy as np
import pandas as pd

LANDMARK_HOURS = 5 / 60  # features use only the first 5 minutes
OUTCOMES = ("dead", "graduated", "censored")

REQUIRED = [
    "mint", "created_at", "outcome", "duration_hours", "launch_hour_utc",
    "n_trades_5m", "n_traders_5m", "buy_sol_5m", "sell_sol_5m", "dev_buy_sol",
    "dev_sold_5m", "same_slot_buyers", "top10_share_5m",
    "creator_prior_launches_30d",
]

# Model features: name -> plain-English label used in tables and charts
FEATURES = {
    "log_traders_5m": "Unique traders, first 5 min (log)",
    "log_buy_sol_5m": "Buy volume SOL, first 5 min (log)",
    "sell_share_5m": "Sell share of volume, first 5 min",
    "log_dev_buy": "Creator's own buy, SOL (log)",
    "dev_sold_5m": "Creator sold within 5 min",
    "log_same_slot_buyers": "Buyers in the launch block (log)",
    "top10_share_5m": "Top-10 wallets' share of supply",
    "log_serial_creator": "Creator's launches in prior 30 days (log)",
    "session_us": "Launched 14:00-24:00 UTC",
    "session_asia": "Launched 00:00-08:00 UTC",
}
BINARY = {"dev_sold_5m", "session_us", "session_asia"}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {missing}")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
    bad = ~df["outcome"].isin(OUTCOMES)
    if bad.any():
        raise ValueError(f"Unexpected outcome values: {df.loc[bad, 'outcome'].unique()}")
    df = df.drop_duplicates("mint").reset_index(drop=True)
    df["duration_hours"] = df["duration_hours"].clip(lower=0)
    num = REQUIRED[4:]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce").fillna(0)
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    vol = out["buy_sol_5m"] + out["sell_sol_5m"]
    out["log_traders_5m"] = np.log1p(out["n_traders_5m"])
    out["log_buy_sol_5m"] = np.log1p(out["buy_sol_5m"])
    out["sell_share_5m"] = np.where(vol > 0, out["sell_sol_5m"] / vol.where(vol > 0, 1), 0.0)
    out["log_dev_buy"] = np.log1p(out["dev_buy_sol"])
    out["dev_sold_5m"] = (out["dev_sold_5m"] > 0).astype(int)
    out["log_same_slot_buyers"] = np.log1p(out["same_slot_buyers"])
    out["top10_share_5m"] = out["top10_share_5m"].clip(0, 1)
    out["log_serial_creator"] = np.log1p(out["creator_prior_launches_30d"])
    h = out["launch_hour_utc"]
    out["session_us"] = ((h >= 14) & (h < 24)).astype(int)
    out["session_asia"] = (h < 8).astype(int)   # baseline = Europe 08-14 UTC
    out["dead"] = (out["outcome"] == "dead").astype(int)
    out["graduated"] = (out["outcome"] == "graduated").astype(int)
    return out


def landmark(df: pd.DataFrame, at_hours: float = LANDMARK_HOURS) -> pd.DataFrame:
    """Tokens still alive (trading, not graduated) at the landmark.

    Clock is reset so t=0 is the landmark. This avoids immortal-time bias:
    5-minute features are only used for tokens that actually lived 5 minutes.
    """
    alive = df["duration_hours"] > at_hours
    lm = df.loc[alive].copy()
    lm["t_lm"] = lm["duration_hours"] - at_hours
    return lm


def standardise(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """Z-score continuous columns (binary left as 0/1). Returns scaled frame + scales."""
    out = df.copy()
    scales = {}
    for c in cols:
        if c in BINARY:
            continue
        mu, sd = out[c].mean(), out[c].std()
        sd = sd if sd and np.isfinite(sd) and sd > 0 else 1.0
        out[c] = (out[c] - mu) / sd
        scales[c] = (mu, sd)
    return out, scales
