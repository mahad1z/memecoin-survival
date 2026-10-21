-- =====================================================================
-- 02_concentration.sql  —  top-10 wallets' share of supply after 5 minutes
-- Same launch window and hash sample as 01_token_level.sql.
-- Net position = tokens bought from the curve minus tokens sold back,
-- per wallet, in the first 5 minutes. Share = top-10 net / 1bn supply.
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
      AND cityHash64(accounts['mint']) % 100 < 5                            -- sample % (same as 01)
    GROUP BY mint
    HAVING curve_ata != ''
),
holders AS (   -- net tokens bought from the curve per wallet, first 5 minutes
    SELECT c2.mint AS mint,
           if(t.source = c2.curve_ata, t.destination_owner, t.source_owner) AS trader,
           sum(if(t.source = c2.curve_ata, 1, -1) * toFloat64(t.amount) / 1e6) AS net
    FROM solana.transfers AS t
    INNER JOIN creates AS c2 ON t.mint = c2.mint
    WHERE t.block_time >= toDateTime64('2026-10-01 00:00:00', 3, 'UTC')
      AND t.block_time <  toDateTime64('2026-10-08 00:10:00', 3, 'UTC')
      AND t.mint IN (SELECT mint FROM creates)
      AND t.action = 1
      AND (t.source = c2.curve_ata OR t.destination = c2.curve_ata)
      AND t.block_time < c2.created_at + INTERVAL 5 MINUTE
      AND NOT (t.source = c2.curve_ata AND t.amount = 206900000000000)
    GROUP BY mint, trader
)
SELECT mint, sum(net) / 1e9 AS top10_share_5m
FROM (
    SELECT mint, net, row_number() OVER (PARTITION BY mint ORDER BY net DESC) AS rn
    FROM holders
    WHERE net > 0
)
WHERE rn <= 10
GROUP BY mint
