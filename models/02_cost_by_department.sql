-- Accountability: which department spends, and how much of it is avoidable.
CREATE OR REPLACE VIEW cost_by_department AS
SELECT
    department,
    COUNT(*) AS queries,
    ROUND(SUM(cost_usd), 2) AS total_cost_usd,
    ROUND(AVG(cost_usd), 4) AS avg_cost_usd,
    ROUND(quantile_cont(cost_usd, 0.95), 4) AS p95_cost_usd,
    ROUND(MAX(cost_usd), 2) AS max_cost_usd,
    SUM(CASE WHEN estimated_saving_usd > 0 THEN 1 ELSE 0 END) AS flagged_queries,
    ROUND(SUM(estimated_saving_usd), 2) AS estimated_saving_usd,
    ROUND(SUM(estimated_saving_usd) / NULLIF(SUM(cost_usd), 0), 4) AS saving_share
FROM cost_per_query
GROUP BY 1
ORDER BY total_cost_usd DESC;
