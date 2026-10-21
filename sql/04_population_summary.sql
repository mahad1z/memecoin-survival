-- =====================================================================
-- 04_population_summary.sql  —  headline numbers on ALL launches (no sampling)
-- One launch day per run (stays under the playground's ~60s timeout);
-- run it for each day of the window and stack the rows.
-- Same outcome definitions as the token-level data:
--   graduated = migration transfer within 7 days
--   dead      = not graduated and no curve trade in the last 24h of the 7 days
-- =====================================================================
WITH
creates AS (
    SELECT accounts['mint']       AS mint,
           argMin(accounts['token'], tuple(block_time, inner_instruction_index)) AS curve_ata,   -- first mint = bonding curve
           count()                        AS n_mints,     -- 2 = Mayhem Mode (2bn supply)
           min(block_time)        AS created_at
    FROM solana.instructions
    WHERE block_time >= toDateTime64('2026-10-01 00:00:00', 3, 'UTC')       -- day start
      AND block_time <  toDateTime64('2026-10-02 00:00:00', 3, 'UTC')       -- day end
      AND outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND instruction_name = 'mintTo'
      AND accounts['mintAuthority'] = 'TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
    GROUP BY mint
    HAVING curve_ata != ''
),
tok AS (
    SELECT c.mint                                   AS mint,
           any(c.created_at)                        AS created_at,
           any(c.n_mints)                           AS n_mints,
           countIf(t.is_trade)                      AS n_trades,
           maxIf(t.block_time, t.is_trade)          AS last_trade_at,
           countIf(t.is_mig) > 0                    AS graduated,
           minIf(t.block_time, t.is_mig)            AS graduated_at
    FROM creates AS c
    LEFT JOIN (
        SELECT c2.mint AS cmint, t.block_time AS block_time,
               t.source = c2.curve_ata AND t.amount = 206900000000000       AS is_mig,
               NOT (t.source = c2.curve_ata AND t.amount = 206900000000000) AS is_trade
        FROM solana.transfers AS t
        INNER JOIN creates AS c2 ON t.mint = c2.mint
        WHERE t.block_time >= toDateTime64('2026-10-01 00:00:00', 3, 'UTC')   -- = day start
          AND t.block_time <  toDateTime64('2026-10-09 00:00:00', 3, 'UTC')   -- = day end + 7 days
          AND t.mint IN (SELECT mint FROM creates)
          AND t.action = 1
          AND (t.source = c2.curve_ata OR t.destination = c2.curve_ata)
          AND t.block_time < c2.created_at + INTERVAL 7 DAY
    ) AS t ON t.cmint = c.mint
    GROUP BY c.mint
)
SELECT
    n_mints,
    min(created_at)                                                      AS day_start,
    count()                                                              AS n_tokens,
    countIf(graduated)                                                   AS n_graduated,
    countIf(NOT graduated AND (n_trades = 0 OR last_trade_at <= created_at + INTERVAL 6 DAY))  AS n_dead,
    countIf(NOT graduated AND n_trades > 0 AND last_trade_at > created_at + INTERVAL 6 DAY)    AS n_censored,
    countIf(n_trades <= 1)                                               AS n_at_most_one_trade,
    countIf(NOT graduated AND (n_trades = 0 OR last_trade_at <= created_at + INTERVAL 5 MINUTE)) AS n_dead_within_5m,
    countIf(NOT graduated AND (n_trades = 0 OR last_trade_at <= created_at + INTERVAL 1 HOUR))   AS n_dead_within_1h,
    countIf(NOT graduated AND (n_trades = 0 OR last_trade_at <= created_at + INTERVAL 24 HOUR))  AS n_dead_within_24h,
    countIf(graduated AND graduated_at <= created_at + INTERVAL 1 HOUR)  AS n_grad_within_1h,
    countIf(graduated AND graduated_at <= created_at + INTERVAL 24 HOUR) AS n_grad_within_24h
FROM tok
GROUP BY n_mints
