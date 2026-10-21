-- =====================================================================
-- 01_token_level.sql  —  one row per pump.fun token (hash-sampled)
-- Engine: Coinbase CDP SQL API playground (ClickHouse-based, restricted
-- function allowlist, ~60s gateway timeout, free tier: 1,000 queries/month).
--
-- How trades are reconstructed (no decoded pump.fun tables needed)
--   * Launch     = SPL `mintTo` executed inside the pump.fun program
--                  (6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P) with pump.fun's
--                  mint authority. Gives mint, launch time/slot, creator (tx
--                  signer) and the bonding-curve token account.
--   * Buy        = token transfer OUT of the bonding-curve account
--   * Sell       = token transfer INTO the bonding-curve account
--   * Graduation = the migration transfer: exactly 206.9M tokens (the
--                  curve's remaining supply) leave the curve once it is full.
--                  It is excluded from trade counts.
--   * SOL values / market cap are derived in Python (prepare_data.py) from
--     net tokens sold using pump.fun's constant-product curve
--       virtual SOL = 30 * 1.073e9 / (1.073e9 - tokens sold)
--     (checked against on-chain SOL transfers: exact match ex-fees).
--
-- The engine re-evaluates CTEs on every reference, so everything is done
-- in ONE pass over the trades. Edit the marked dates / sample %.
-- Run ONE launch-day at a time (a 7-day window exceeds the ~60s timeout)
-- and stack the results.
-- =====================================================================

WITH
creates AS (
    SELECT accounts['mint']               AS mint,
           argMin(accounts['token'], tuple(block_time, inner_instruction_index))         AS curve_ata,   -- first mint = bonding curve
           count()                        AS n_mints,     -- 2 = Mayhem Mode (2bn supply)
           min(block_time)                AS created_at,
           argMin(block_slot, block_time) AS created_slot,
           argMin(tx_signer, block_time)  AS creator
    FROM solana.instructions
    WHERE block_time >= toDateTime64('2026-10-01 00:00:00', 3, 'UTC')       -- launch window start
      AND block_time <  toDateTime64('2026-10-08 00:00:00', 3, 'UTC')       -- launch window end
      AND outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND instruction_name = 'mintTo'
      AND accounts['mintAuthority'] = 'TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
      AND cityHash64(accounts['mint']) % 100 < 5                            -- sample %
    GROUP BY mint
    HAVING curve_ata != ''
)

SELECT
    c.mint                                                         AS mint,
    any(c.created_at)                                              AS created_at,
    any(c.creator)                                                 AS creator,
    any(c.n_mints)                                                 AS n_mints,
    -- lifetime on the bonding curve ----------------------------------------
    countIf(t.is_trade)                                            AS n_trades_total,
    maxIf(t.block_time, t.is_trade)                                AS last_trade_at,
    if(countIf(t.is_mig) > 0, 1, 0)                                AS graduated,
    minIf(t.block_time, t.is_mig)                                  AS graduated_at,
    sumIf(t.tok, t.is_trade AND t.is_buy)                          AS buy_tokens_total,
    sumIf(t.tok, t.is_trade AND NOT t.is_buy)                      AS sell_tokens_total,
    -- first 5 minutes -----------------------------------------------------
    countIf(t.is_trade AND t.early)                                AS n_trades_5m,
    uniqExactIf(t.trader, t.is_trade AND t.early)                  AS n_traders_5m,
    sumIf(t.tok, t.is_trade AND t.early AND t.is_buy)              AS buy_tokens_5m,
    sumIf(t.tok, t.is_trade AND t.early AND NOT t.is_buy)          AS sell_tokens_5m,
    sumIf(t.tok, t.is_trade AND t.is_buy AND t.launch_slot AND t.is_dev) AS dev_buy_tokens_launch,
    if(countIf(t.is_trade AND t.early AND NOT t.is_buy AND t.is_dev) > 0, 1, 0) AS dev_sold_5m,
    uniqExactIf(t.trader, t.is_trade AND t.is_buy AND t.launch_slot AND NOT t.is_dev) AS same_slot_buyers
FROM creates AS c
LEFT JOIN (
    SELECT c2.mint                                                        AS cmint,
           t.block_time                                                   AS block_time,
           t.source = c2.curve_ata                                        AS is_buy,
           if(t.source = c2.curve_ata, t.destination_owner, t.source_owner) AS trader,
           toFloat64(t.amount) / 1e6                                      AS tok,
           t.source = c2.curve_ata AND t.amount = 206900000000000         AS is_mig,
           NOT (t.source = c2.curve_ata AND t.amount = 206900000000000)   AS is_trade,
           t.block_time < c2.created_at + INTERVAL 5 MINUTE               AS early,
           t.block_slot = c2.created_slot                                 AS launch_slot,
           if(t.source = c2.curve_ata, t.destination_owner, t.source_owner) = c2.creator AS is_dev
    FROM solana.transfers AS t
    INNER JOIN creates AS c2 ON t.mint = c2.mint
    WHERE t.block_time >= toDateTime64('2026-10-01 00:00:00', 3, 'UTC')     -- = launch start
      AND t.block_time <  toDateTime64('2026-10-15 00:00:00', 3, 'UTC')     -- = launch end + 7 days
      AND t.mint IN (SELECT mint FROM creates)                            -- pre-filter (uses the index)
      AND t.action = 1
      AND (t.source = c2.curve_ata OR t.destination = c2.curve_ata)
      AND t.block_time < c2.created_at + INTERVAL 7 DAY
) AS t ON t.cmint = c.mint
GROUP BY c.mint
