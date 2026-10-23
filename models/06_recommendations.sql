-- Grouped by pattern and table, which is how the fixes actually get scheduled.
CREATE OR REPLACE VIEW recommendations AS
SELECT
    pattern,
    "table",
    COUNT(*) AS occurrences,
    ROUND(SUM(cost_usd), 2) AS total_cost_usd,
    ROUND(SUM(estimated_saving_usd), 2) AS estimated_saving_usd,
    MAX(recommendation) AS recommendation
FROM cost_per_query
WHERE pattern <> ''
GROUP BY 1, 2
ORDER BY estimated_saving_usd DESC;
