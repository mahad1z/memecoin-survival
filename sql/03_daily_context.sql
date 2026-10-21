-- =====================================================================
-- 03_daily_context.sql  —  daily launches and graduation rate (context chart)
-- Cheap query: creates + completes only. Save as data/daily_context.csv
-- =====================================================================

WITH creates AS (
    SELECT evt_block_date AS day, mint
    FROM pumpdotfun_solana.pump_evt_createevent
    WHERE evt_block_date >= current_date - INTERVAL '180' DAY
),
grads AS (
    SELECT DISTINCT mint
    FROM pumpdotfun_solana.pump_evt_completeevent
    WHERE evt_block_date >= current_date - INTERVAL '180' DAY
)
SELECT
    c.day,
    COUNT(*)                                             AS launches,
    COUNT(g.mint)                                        AS graduated,
    CAST(COUNT(g.mint) AS DOUBLE) / COUNT(*)             AS graduation_rate
FROM creates c
LEFT JOIN grads g ON g.mint = c.mint
GROUP BY 1
ORDER BY 1
