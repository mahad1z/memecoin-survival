# How long do memecoins live? A survival analysis of pump.fun launches

![tests](https://github.com/mahad1z/memecoin-survival/actions/workflows/tests.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![data](https://img.shields.io/badge/data-Dune%20Analytics-orange)
![license](https://img.shields.io/badge/license-MIT-green)

Tens of thousands of tokens are launched on [pump.fun](https://pump.fun) (Solana) every day. This project measures **how quickly they die, how few "graduate", and which signals in a token's first five minutes predict its death**, using the same survival-analysis tools used in medicine and credit-risk modelling.

> **Status:** pipeline built and tested. On-chain data pull in progress; results and charts will be added here.

## Question

1. What share of pump.fun tokens are still trading after 5 minutes, 1 hour, 24 hours and 7 days?
2. How rare is graduation, given that most tokens die first?
3. Which observable features in the first 5 minutes predict a shorter life?

This is **risk research, not a trading strategy.** The goal is to quantify how hostile the environment is, not to pick winners.

## Data

On-chain events decoded by [Dune Analytics](https://dune.com) from the pump.fun bonding-curve program (`6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`):

| Table | Used for |
|---|---|
| `pumpdotfun_solana.pump_evt_createevent` | Launch time, creator, token |
| `pumpdotfun_solana.pump_evt_tradeevent` | Every buy and sell on the bonding curve, with reserves (gives price and market cap) |
| `pumpdotfun_solana.pump_evt_completeevent` | Graduation (bonding curve filled) |

Queries are in [`sql/`](sql/). Only SOL-quoted launches are included. The token-level query uses a reproducible hash sample to stay within Dune's free-tier limits; the headline query (`02`) runs on the full population as a check.

## Definitions

| Term | Definition |
|---|---|
| **Dead** | Not graduated, and no bonding-curve trade in the last 24h of the 7-day window. Time of death = time of last trade. |
| **Graduated** | Bonding curve filled within 7 days (CompleteEvent). Treated as a **competing event**, because a graduated token leaves the bonding curve. |
| **Censored** | Still trading near the end of the 7-day window. |
| **Landmark** | Features use only the first 5 minutes. Models include only tokens alive at 5 minutes, with the clock reset there. This avoids *immortal-time bias* (a token can't have 5-minute features unless it lived 5 minutes). |

## Methods

1. **Aalen–Johansen cumulative incidence.** Probability of death vs graduation over time, treating them as competing risks. A naive Kaplan–Meier with graduation censored would overstate death. 95% CIs by bootstrap.
2. **Kaplan–Meier + log-rank test.** Survival of tokens alive at 5 minutes, split by whether the creator sold in that window.
3. **Cause-specific Cox proportional-hazards model.** Hazard ratios for death per 1 SD of each feature (binary flags 0→1). Includes checks for collinearity (VIF) and the proportional-hazards assumption (Schoenfeld residuals vs log time).
4. **Out-of-sample logistic regression.** Can the first 5 minutes predict death within 24h? Fit on 70%, AUC reported on the held-out 30%.

### Features (first 5 minutes)

Unique traders · buy volume · sell share of volume · creator's own buy · whether the creator sold · buyers in the launch block (bundling/sniping proxy) · top-10 wallets' share of supply · creator's launches in the prior 30 days (serial-deployer proxy) · launch session (Asia / Europe / US hours, UTC).

## Results

_Coming soon._ The pipeline produces four charts and a full results file (`results/summary.md`):

1. Death vs graduation over the first 7 days (cumulative incidence)
2. Survival curves split by whether the creator sold in the first 5 minutes
3. Hazard ratios for every early-warning feature
4. Daily launches and graduation rate over the last 6 months

## Limitations

- **Death is defined by inactivity on the bonding curve.** Graduated tokens are not followed onto PumpSwap/Raydium; post-graduation survival is a natural extension.
- **Observational, not causal.** A creator selling early is a *signal*, not proven to *cause* death.
- **One time window.** Memecoin activity is cyclical; results may differ in hotter or colder markets.
- **Wallet-level features are proxies.** One person can control many wallets, so "top-10 share" and "same-block buyers" understate concentration.
- **Sampling.** The model uses a hash sample of tokens; headline rates are cross-checked on the full population.

## Reproduce

```bash
pip install -r requirements.txt

# 1. Run sql/01, 02, 03 on dune.com, download results as CSV into data/:
#    data/token_level.csv, data/population_summary.csv, data/daily_context.csv
# 2. Run the analysis
python run_analysis.py

# Pipeline test on synthetic data (charts are watermarked, numbers are fake)
python run_analysis.py --synthetic
python -m pytest tests
```

## Project structure

```
sql/                 Dune queries (DuneSQL / Trino)
memesurv/data.py     Loading, feature engineering, landmark cohort
memesurv/survival.py Aalen–Johansen, Kaplan–Meier, Cox PH, logistic + AUC
memesurv/plots.py    Figures
memesurv/synthetic.py Fake data with the same schema, for testing
run_analysis.py      Runs everything -> figures/ and results/
```

## Related work

Marino et al. (2026) analyse pump.fun's bonding-curve market design and show incentives for large holders to sell just before graduation. This project takes an empirical, token-lifetime view of the same platform.

---
*Author: Mahad — Economics, Mathematics & Statistics, University College Dublin.*
