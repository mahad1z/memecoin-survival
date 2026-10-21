-- =====================================================================
-- 05_daily_context.sql  —  daily launches and graduations (context chart)
-- Run in 3-day chunks (longer ranges exceed the per-query scan limit);
-- the chart uses 13 Aug – 20 Oct 2026.
-- Launches: pump.fun mintTo calls. Graduations: migration transfers
-- (exactly 206.9M tokens leaving a pump.fun bonding curve).
-- Graduation rate here = graduations that day / launches that day
-- (context only; the cohort-based rate is in 04_population_summary).
-- =====================================================================
WITH
launches AS (
    SELECT toDate(created_at) AS day, count() AS launches
    FROM (
        SELECT accounts['mint'] AS mint, min(block_time) AS created_at
        FROM solana.instructions
        WHERE block_time >= toDateTime64('2026-07-01 00:00:00', 3, 'UTC')
          AND block_time <  toDateTime64('2026-10-21 00:00:00', 3, 'UTC')
          AND outer_executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
          AND instruction_name = 'mintTo'
          AND accounts['mintAuthority'] = 'TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
        GROUP BY mint
    )
    GROUP BY day
),
grads AS (
    SELECT toDate(block_time) AS day, uniqExact(mint) AS graduated
    FROM solana.transfers
    WHERE block_time >= toDateTime64('2026-07-01 00:00:00', 3, 'UTC')
      AND block_time <  toDateTime64('2026-10-21 00:00:00', 3, 'UTC')
      AND endsWith(mint, 'pump')
      AND amount = 206900000000000
      AND action = 1
    GROUP BY day
)
SELECT l.day AS day, l.launches AS launches, g.graduated AS graduated,
       g.graduated / l.launches AS graduation_rate
FROM launches AS l
LEFT JOIN grads AS g ON g.day = l.day
ORDER BY day
