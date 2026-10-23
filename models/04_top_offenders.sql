-- The queries worth opening first, each with the reason it is on the list.
CREATE OR REPLACE VIEW top_offenders AS
SELECT
    query_id, "user", department, statement_type, "table",
    bytes_scanned, duration_seconds, pattern,
    cost_usd, estimated_saving_usd, recommendation, started_at
FROM cost_per_query
ORDER BY cost_usd DESC
LIMIT 25;
