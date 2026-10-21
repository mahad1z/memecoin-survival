-- =====================================================================
-- 03_creator_history.sql  —  launches by the same creator in the prior 30 days
-- Same launch window and hash sample as 01_token_level.sql.
-- Proxy for "serial deployers" (wallets that launch token after token).
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
)
,
prior AS (
    SELECT accounts['mint']              AS mint,
           min(block_time)               AS p_created_at,
           argMin(tx_signer, block_time) AS p_creator
    FROM solana.instructions
    WHERE block_time >= toDateTime64('2026-09-01 00:00:00', 3, 'UTC')       -- launch start - 30 days
      AND block_time <  toDateTime64('2026-10-08 00:00:00', 3, 'UTC')       -- launch end
      AND outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND instruction_name = 'mintTo'
      AND accounts['mintAuthority'] = 'TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
      AND tx_signer IN (SELECT creator FROM creates)
    GROUP BY mint
)
SELECT c.mint AS mint,
       countIf(p.p_created_at < c.created_at
               AND p.p_created_at >= c.created_at - INTERVAL 30 DAY) AS creator_prior_launches_30d
FROM creates AS c
LEFT JOIN prior AS p ON p.p_creator = c.creator
GROUP BY c.mint
