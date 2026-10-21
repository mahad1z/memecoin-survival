# Results

Sample: **17,709 tokens** (4,302 Mayhem Mode, 13,407 standard) launched 2026-10-01 to 2026-10-07.

Outcome counts: dead 17,095 (96.5%), graduated 453 (2.6%), censored 161 (0.9%)

## 1. How fast they die (Aalen–Johansen, 95% bootstrap CI)

| by | dead % | graduated % |
|---|---|---|
| 5 min | 57.4% (56.7%–58.2%) | 1.62% (1.45%–1.81%) |
| 1 hour | 75.1% (74.5%–75.7%) | 2.24% (2.02%–2.45%) |
| 24 hours | 89.4% (89.0%–89.9%) | 2.47% (2.24%–2.70%) |
| 7 days | 96.5% (96.3%–96.8%) | 2.56% (2.32%–2.80%) |

### Standard vs Mayhem Mode launches

| launch type | n | dead by 1h | dead by 24h | graduated by 7d |
|---|---|---|---|---|
| Standard | 13,407 | 73.0% | 88.1% | 2.68% |
| Mayhem Mode | 4,302 | 81.8% | 93.5% | 2.19% |

### Full population check (no sampling, sql/04)

- Tokens: 352,621
- Graduated: 2.48%
- Dead within 5 min: 57.0%, 1h: 75.0%, 24h: 89.4%, 7d: 96.6%
- At most one trade ever: 13.7%
- Graduated within 1h: 2.19%, within 24h: 2.39%

## 2. Standard tokens alive at 5 minutes: 6,014 (44.9% of standard launches)

Unique traders in first 5 min: 0–5 = 43%, 6–20 = 24%, 21+ = 33% of the cohort. Log-rank chi² = 381.4, p = <0.001

- 0–5 traders: median remaining life 0.82 h
- 6–20 traders: median remaining life 0.51 h
- 21+ traders: median remaining life 18.02 h

Creator sold within 5 min vs held: log-rank chi² = 2.1, p = 0.146 (share of the cohort where the creator sold: 56%)

## 3. What predicts death (cause-specific Cox PH, standardised features)

| label | HR | HR_lo | HR_hi | p | PH_p | VIF |
|---|---|---|---|---|---|---|
| Unique traders, first 5 min (log) | 0.77 | 0.73 | 0.81 | <0.001 | <0.001 | 3.6 |
| Net SOL into the curve, first 5 min (log) | 0.94 | 0.89 | 1.00 | 0.050 | <0.001 | 4.5 |
| Sell share of token volume, first 5 min | 1.09 | 1.05 | 1.14 | <0.001 | <0.001 | 2.3 |
| Creator's own buy, SOL (log) | 1.02 | 0.98 | 1.06 | 0.372 | 0.144 | 2.0 |
| Creator sold within 5 min | 1.12 | 1.03 | 1.22 | 0.006 | <0.001 | 2.3 |
| Buyers in the launch block (log) | 1.03 | 0.99 | 1.06 | 0.168 | <0.001 | 1.9 |
| Top-10 wallets' share of supply | 0.90 | 0.85 | 0.96 | 0.001 | <0.001 | 4.3 |
| Creator's launches in prior 30 days (log) | 0.92 | 0.90 | 0.95 | <0.001 | <0.001 | 1.2 |
| Launched 14:00-24:00 UTC | 0.96 | 0.90 | 1.02 | 0.209 | <0.001 | 1.7 |
| Launched 00:00-08:00 UTC | 0.93 | 0.86 | 1.00 | 0.048 | <0.001 | 1.7 |

HR > 1 = dies faster. PH_p < 0.05 means the effect changes over time (interpret as an average effect). VIF > 5 = collinearity worth flagging.

## 4. Can the first 5 minutes predict death within 24h?

Logistic regression, 70/30 split. Base rate 77.9%. AUC test **0.667** (train 0.703), n_test = 1,858.

| label | OR | OR_lo | OR_hi | p |
|---|---|---|---|---|
| Unique traders, first 5 min (log) | 0.57 | 0.49 | 0.66 | <0.001 |
| Net SOL into the curve, first 5 min (log) | 0.61 | 0.53 | 0.72 | <0.001 |
| Sell share of token volume, first 5 min | 1.25 | 1.10 | 1.42 | <0.001 |
| Creator's own buy, SOL (log) | 1.12 | 1.00 | 1.25 | 0.050 |
| Creator sold within 5 min | 1.10 | 0.87 | 1.40 | 0.426 |
| Buyers in the launch block (log) | 1.09 | 0.98 | 1.21 | 0.131 |
| Top-10 wallets' share of supply | 0.92 | 0.79 | 1.07 | 0.269 |
| Creator's launches in prior 30 days (log) | 0.86 | 0.79 | 0.94 | <0.001 |
| Launched 14:00-24:00 UTC | 0.97 | 0.79 | 1.20 | 0.791 |
| Launched 00:00-08:00 UTC | 0.80 | 0.64 | 1.01 | 0.065 |
