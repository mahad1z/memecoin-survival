"""Turn the raw CDP SQL exports into the analysis table (data/token_level.csv).

    python prepare_data.py

Inputs (in data/):
    raw_token_level.csv      sql/01_token_level.sql      (one row per sampled token)
    concentration.csv        sql/02_concentration.sql    (top-10 share after 5 min)
    creator_history.csv      sql/03_creator_history.sql  (creator's prior launches)

Outcome labels and durations are set here so the definitions live in one place:
    graduated : bonding curve completed (migration) within the 7-day follow-up
    dead      : not graduated and no curve trade in the last 24h of the window
                (time of death = time of last trade)
    censored  : still trading near the end of the window

SOL amounts come from pump.fun's constant-product bonding curve:
    virtual SOL reserves = 30 * 1.073e9 / (1.073e9 - tokens sold)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FOLLOW_UP_H = 168.0
DEAD_AFTER_H = 24.0
VT0, VS0 = 1_073_000_000.0, 30.0       # initial virtual token / SOL reserves
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def curve_sol(tokens_sold) -> np.ndarray:
    """SOL that has gone into the curve after `tokens_sold` net tokens left it."""
    q = np.clip(np.asarray(tokens_sold, float), 0, VT0 - 1)
    return VS0 * VT0 / (VT0 - q) - VS0


def curve_mcap(tokens_sold) -> np.ndarray:
    """Market cap in SOL (1bn supply) at a given net amount sold."""
    q = np.clip(np.asarray(tokens_sold, float), 0, VT0 - 1)
    return VS0 * VT0 / (VT0 - q) ** 2 * 1e9


def prepare(raw: pd.DataFrame, conc: pd.DataFrame | None = None,
            hist: pd.DataFrame | None = None) -> pd.DataFrame:
    df = raw.drop_duplicates("mint").copy()
    for c in ("created_at", "graduated_at", "last_trade_at"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    num = [c for c in df.columns
           if c not in ("mint", "creator", "created_at", "graduated_at", "last_trade_at")]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce").fillna(0)

    if conc is not None:
        df = df.merge(conc[["mint", "top10_share_5m"]], on="mint", how="left")
    if hist is not None:
        df = df.merge(hist[["mint", "creator_prior_launches_30d"]], on="mint", how="left")
    for c in ("top10_share_5m", "creator_prior_launches_30d"):
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # --- outcomes -------------------------------------------------------------
    hours = lambda a, b: (a - b).dt.total_seconds() / 3600.0  # noqa: E731
    has_trades = df["n_trades_total"] > 0
    grad = (df["graduated"] > 0) & has_trades
    last_h = hours(df["last_trade_at"], df["created_at"]).where(has_trades, 0.0).clip(lower=0)
    dead = ~grad & (~has_trades | (last_h <= FOLLOW_UP_H - DEAD_AFTER_H))
    df["outcome"] = np.select([grad, dead], ["graduated", "dead"], "censored")
    df["duration_hours"] = np.select(
        [grad, dead],
        [hours(df["graduated_at"], df["created_at"]).clip(lower=0), last_h],
        FOLLOW_UP_H)

    # --- curve-derived SOL features ---------------------------------------------
    net_5m = df["buy_tokens_5m"] - df["sell_tokens_5m"]
    df["net_sol_5m"] = curve_sol(net_5m)
    df["mcap_5m_sol"] = curve_mcap(net_5m)
    df["dev_buy_sol"] = curve_sol(df["dev_buy_tokens_launch"])   # creator buys first, at launch
    df["mayhem"] = (df.get("n_mints", 1) > 1).astype(int)   # 2bn-supply "Mayhem Mode" launch
    df["launch_hour_utc"] = df["created_at"].dt.hour
    df["launch_dow"] = df["created_at"].dt.dayofweek + 1
    return df.drop(columns=["graduated", "graduated_at", "last_trade_at", "creator"],
                   errors="ignore")


def _read(name):
    p = DATA / name
    return pd.read_csv(p) if p.exists() else None


if __name__ == "__main__":
    out = prepare(_read("raw_token_level.csv"), _read("concentration.csv"),
                  _read("creator_history.csv"))
    dest = DATA / "token_level.csv"
    out.to_csv(dest, index=False)
    print(f"{len(out):,} tokens -> {dest}")
    print(out["outcome"].value_counts().to_string())
