-- =====================================================================
-- 01_token_level.sql  —  one row per pump.fun token (sampled)
-- Run on Dune (DuneSQL / Trino). Download result as data/token_level.csv
--
-- What it does
--   * Takes every SOL-quoted pump.fun launch in [launch_start, launch_end)
--   * Keeps a reproducible hash sample (sample_pct %) so the query fits
--     inside Dune's free-tier limits
--   * Follows each token on the bonding curve for `follow_up` (7 days)
--   * Builds "first 5 minutes" features (landmark design: no look-ahead)
--   * Labels the outcome: graduated / dead / censored
--
-- Outcome definitions (state these in the write-up)
--   graduated : CompleteEvent (bonding curve filled) within follow-up
--   dead      : not graduated AND no bonding-curve trade in the final
--               `dead_after` (24h) of the follow-up window.
--               Time of death = time of last trade.
--   censored  : still trading near the end of the window
--
-- If it times out: lower sample_pct or shorten the launch window.
-- Pick launch dates that ended at least 8 days ago.
-- =====================================================================

WITH params AS (
    SELECT
        TIMESTAMP '2026-09-01 00:00:00' AS launch_start,
        TIMESTAMP '2026-09-08 00:00:00' AS launch_end,     -- 7 days of launches
        INTERVAL '7' DAY                AS follow_up,
        INTERVAL '24' HOUR              AS dead_after,
        INTERVAL '5' MINUTE             AS landmark,
        10                              AS sample_pct      -- % of tokens kept
),

creates AS (
    SELECT
        c.mint,
        c."user"          AS creator,
        c.evt_block_time  AS created_at,
        c.evt_block_slot  AS created_slot,
        c.name,
        c.symbol
    FROM pumpdotfun_solana.pump_evt_createevent c
    CROSS JOIN params p
    WHERE c.evt_block_date >= CAST(p.launch_start AS DATE)
      AND c.evt_block_date <= CAST(p.launch_end AS DATE)
      AND c.evt_block_time >= p.launch_start
      AND c.evt_block_time <  p.launch_end
      AND (c.quote_mint IS NULL
           OR c.quote_mint = 'So11111111111111111111111111111111111111112')
      AND abs(from_big_endian_64(xxhash64(to_utf8(c.mint)))) % 100 < p.sample_pct
),

trades AS (
    SELECT
        t.mint,
        t.evt_block_time AS ts,
        t.evt_block_slot AS slot,
        t."user"         AS trader,
        COALESCE(t.is_buy, t.isBuy) AS is_buy,
        COALESCE(CAST(t.sol_amount   AS DOUBLE), CAST(t.solAmount   AS DOUBLE)) / 1e9 AS sol,
        COALESCE(CAST(t.token_amount AS DOUBLE), CAST(t.tokenAmount AS DOUBLE)) / 1e6 AS tokens,
        -- market cap in SOL (1bn supply): virtual SOL reserves / virtual token reserves
        COALESCE(CAST(t.virtual_sol_reserves AS DOUBLE), CAST(t.virtualSolReserves AS DOUBLE)) * 1e6
          / NULLIF(COALESCE(CAST(t.virtual_token_reserves AS DOUBLE),
                            CAST(t.virtualTokenReserves  AS DOUBLE)), 0) AS mcap_sol,
        c.creator,
        c.created_at,
        c.created_slot
    FROM pumpdotfun_solana.pump_evt_tradeevent t
    JOIN creates c ON c.mint = t.mint
    CROSS JOIN params p
    WHERE t.evt_block_date >= CAST(p.launch_start AS DATE)
      AND t.evt_block_date <= CAST(p.launch_end + p.follow_up AS DATE)
      AND t.evt_block_time <  c.created_at + p.follow_up
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

-- ---------- features measured in the first 5 minutes only ----------
early AS (
    SELECT
        c.mint,
        COUNT(t.ts)                                                        AS n_trades_5m,
        COUNT(DISTINCT t.trader)                                           AS n_traders_5m,
        COALESCE(SUM(CASE WHEN t.is_buy     THEN t.sol END), 0)            AS buy_sol_5m,
        COALESCE(SUM(CASE WHEN NOT t.is_buy THEN t.sol END), 0)            AS sell_sol_5m,
        COALESCE(SUM(CASE WHEN t.trader = c.creator AND t.is_buy THEN t.sol END), 0) AS dev_buy_sol,
        MAX(CASE WHEN t.trader = c.creator AND NOT t.is_buy THEN 1 ELSE 0 END)       AS dev_sold_5m,
        COUNT(DISTINCT CASE WHEN t.slot = c.created_slot AND t.is_buy
                             AND t.trader <> c.creator THEN t.trader END)  AS same_slot_buyers,
        MAX_BY(t.mcap_sol, t.ts)                                           AS mcap_5m_sol
    FROM creates c
    CROSS JOIN params p
    LEFT JOIN trades t
           ON t.mint = c.mint
          AND t.ts < c.created_at + p.landmark
    GROUP BY 1
),

holders_5m AS (
    SELECT t.mint, t.trader,
           SUM(CASE WHEN t.is_buy THEN t.tokens ELSE -t.tokens END) AS net_tokens
    FROM trades t
    CROSS JOIN params p
    WHERE t.ts < t.created_at + p.landmark
    GROUP BY 1, 2
),

concentration AS (
    SELECT mint,
           SUM(CASE WHEN rn <= 10 THEN net_tokens ELSE 0 END) / 1e9 AS top10_share_5m
    FROM (
        SELECT mint, net_tokens,
               ROW_NUMBER() OVER (PARTITION BY mint ORDER BY net_tokens DESC) AS rn
        FROM holders_5m
        WHERE net_tokens > 0
    )
    GROUP BY 1
),

creator_history AS (
    SELECT c.mint, COUNT(prev.mint) AS creator_prior_launches_30d
    FROM creates c
    CROSS JOIN params p
    LEFT JOIN pumpdotfun_solana.pump_evt_createevent prev
           ON prev."user" = c.creator
          AND prev.evt_block_date >= CAST(p.launch_start - INTERVAL '30' DAY AS DATE)
          AND prev.evt_block_time <  c.created_at
          AND prev.evt_block_time >= c.created_at - INTERVAL '30' DAY
    GROUP BY 1
),

-- ---------- whole-window lifetime stats ----------
life AS (
    SELECT
        c.mint,
        MAX(t.ts)                  AS last_trade_at,
        MAX(t.mcap_sol)            AS peak_mcap_sol,
        MAX_BY(t.mcap_sol, t.ts)   AS last_mcap_sol,
        COUNT(t.ts)                AS n_trades_total,
        COALESCE(SUM(t.sol), 0)    AS volume_sol_total
    FROM creates c
    LEFT JOIN trades t ON t.mint = c.mint
    GROUP BY 1
)

SELECT
    c.mint,
    c.name,
    c.symbol,
    c.creator,
    c.created_at,
    hour(c.created_at)                 AS launch_hour_utc,
    day_of_week(c.created_at)          AS launch_dow,          -- 1 = Monday
    g.graduated_at,
    l.last_trade_at,
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
        WHEN l.last_trade_at <= c.created_at + p.follow_up - p.dead_after
            THEN date_diff('second', c.created_at, l.last_trade_at) / 3600.0
        ELSE date_diff('second', c.created_at, c.created_at + p.follow_up) / 3600.0
    END AS duration_hours,
    e.n_trades_5m,
    e.n_traders_5m,
    e.buy_sol_5m,
    e.sell_sol_5m,
    e.dev_buy_sol,
    e.dev_sold_5m,
    e.same_slot_buyers,
    e.mcap_5m_sol,
    COALESCE(k.top10_share_5m, 0)      AS top10_share_5m,
    h.creator_prior_launches_30d,
    l.peak_mcap_sol,
    l.last_mcap_sol,
    l.n_trades_total,
    l.volume_sol_total
FROM creates c
CROSS JOIN params p
LEFT JOIN grads           g ON g.mint = c.mint
LEFT JOIN life            l ON l.mint = c.mint
LEFT JOIN early           e ON e.mint = c.mint
LEFT JOIN concentration   k ON k.mint = c.mint
LEFT JOIN creator_history h ON h.mint = c.mint
ORDER BY c.created_at
