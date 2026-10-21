-- =====================================================================
-- 02_population_summary.sql  —  headline numbers on ALL tokens (no sample)
-- Same definitions as 01_token_level.sql. Returns one row.
-- Save the result as data/population_summary.csv
-- If it times out, shorten the launch window to 1-3 days.
-- =====================================================================

WITH params AS (
    SELECT
        TIMESTAMP '2026-09-01 00:00:00' AS launch_start,
        TIMESTAMP '2026-09-08 00:00:00' AS launch_end,
        INTERVAL '7' DAY                AS follow_up,
        INTERVAL '24' HOUR              AS dead_after
),

creates AS (
    SELECT c.mint, c.evt_block_time AS created_at
    FROM pumpdotfun_solana.pump_evt_createevent c
    CROSS JOIN params p
    WHERE c.evt_block_date >= CAST(p.launch_start AS DATE)
      AND c.evt_block_date <= CAST(p.launch_end AS DATE)
      AND c.evt_block_time >= p.launch_start
      AND c.evt_block_time <  p.launch_end
      AND (c.quote_mint IS NULL
           OR c.quote_mint = 'So11111111111111111111111111111111111111112')
),

last_trade AS (
    SELECT t.mint, MAX(t.evt_block_time) AS last_trade_at, COUNT(*) AS n_trades
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN creates c ON c.mint = t.mint
    CROSS JOIN params p
    WHERE t.evt_block_date >= CAST(p.launch_start AS DATE)
      AND t.evt_block_date <= CAST(p.launch_end + p.follow_up AS DATE)
      AND t.evt_block_time <  c.created_at + p.follow_up
    GROUP BY 1
),

grads AS (
    SELECT g.mint, MIN(g.evt_block_time) AS graduated_at
    FROM pumpdotfun_solana.pump_evt_completeevent g
    JOIN creates c ON c.mint = g.mint
    CROSS JOIN params p
    WHERE g.evt_block_date >= CAST(p.launch_start AS DATE)
      AND g.evt_block_date <= CAST(p.launch_end + p.follow_up AS DATE)
      AND g.evt_block_time <  c.created_at + p.follow_up
    GROUP BY 1
),

tok AS (
    SELECT
        c.mint,
        COALESCE(l.n_trades, 0) AS n_trades,
        CASE
            WHEN g.graduated_at IS NOT NULL THEN 'graduated'
            WHEN l.last_trade_at IS NULL
              OR l.last_trade_at <= c.created_at + p.follow_up - p.dead_after THEN 'dead'
            ELSE 'censored'
        END AS outcome,
        CASE
            WHEN g.graduated_at IS NOT NULL
                THEN date_diff('second', c.created_at, g.graduated_at) / 3600.0
            WHEN l.last_trade_at IS NULL THEN 0.0
            ELSE date_diff('second', c.created_at, l.last_trade_at) / 3600.0
        END AS t_hours
    FROM creates c
    CROSS JOIN params p
    LEFT JOIN last_trade l ON l.mint = c.mint
    LEFT JOIN grads      g ON g.mint = c.mint
)

SELECT
    COUNT(*)                                                         AS n_tokens,
    SUM(CASE WHEN outcome = 'graduated' THEN 1 ELSE 0 END)           AS n_graduated,
    SUM(CASE WHEN outcome = 'dead'      THEN 1 ELSE 0 END)           AS n_dead,
    SUM(CASE WHEN outcome = 'censored'  THEN 1 ELSE 0 END)           AS n_censored,
    SUM(CASE WHEN n_trades <= 1 THEN 1 ELSE 0 END)                   AS n_at_most_one_trade,
    SUM(CASE WHEN outcome = 'dead' AND t_hours <= 1.0/12 THEN 1 ELSE 0 END) AS n_dead_within_5m,
    SUM(CASE WHEN outcome = 'dead' AND t_hours <= 1   THEN 1 ELSE 0 END) AS n_dead_within_1h,
    SUM(CASE WHEN outcome = 'dead' AND t_hours <= 24  THEN 1 ELSE 0 END) AS n_dead_within_24h,
    SUM(CASE WHEN outcome = 'dead' AND t_hours <= 168 THEN 1 ELSE 0 END) AS n_dead_within_7d,
    approx_percentile(CASE WHEN outcome = 'graduated' THEN t_hours END, 0.5) AS median_hours_to_graduate,
    approx_percentile(CASE WHEN outcome = 'dead'      THEN t_hours END, 0.5) AS median_hours_to_death
FROM tok
