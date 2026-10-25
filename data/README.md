# data/

Query results from the Coinbase CDP SQL API, for launches on 1–7 October 2026.

| File | Query | Rows | In repo? |
|---|---|---|---|
| `raw_token_level.csv` | `sql/01_token_level.sql` (5% hash sample, run per launch-day) | 17,709 | no (4 MB, regenerate with the query) |
| `concentration.csv` | `sql/02_concentration.sql` | 9,946 | no |
| `creator_history.csv` | `sql/03_creator_history.sql` | 17,709 | no |
| `population_summary.csv` | `sql/04_population_summary.sql` (all launches, per day × launch type) | 14 | yes |
| `daily_context.csv` | `sql/05_daily_context.sql` (13 Aug – 20 Oct 2026) | 69 | yes |

Then run `python prepare_data.py && python run_analysis.py` from the repo root.
