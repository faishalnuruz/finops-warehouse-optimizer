-- Spend over time, with the avoidable share called out separately.
CREATE OR REPLACE VIEW daily_trend AS
SELECT
    query_date,
    COUNT(*) AS queries,
    ROUND(SUM(cost_usd), 2) AS cost_usd,
    ROUND(SUM(estimated_saving_usd), 2) AS flagged_cost_usd,
    ROUND(SUM(estimated_saving_usd) / NULLIF(SUM(cost_usd), 0), 4) AS flagged_share
FROM cost_per_query
GROUP BY 1
ORDER BY 1;
