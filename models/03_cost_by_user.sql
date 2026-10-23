-- The same view by person: the input to a coaching conversation, not a punishment.
CREATE OR REPLACE VIEW cost_by_user AS
SELECT
    "user",
    department,
    COUNT(*) AS queries,
    ROUND(SUM(cost_usd), 2) AS total_cost_usd,
    ROUND(AVG(cost_usd), 4) AS avg_cost_usd,
    ROUND(MAX(cost_usd), 2) AS max_cost_usd,
    ROUND(SUM(estimated_saving_usd), 2) AS estimated_saving_usd
FROM cost_per_query
GROUP BY 1, 2
ORDER BY total_cost_usd DESC;
