-- One row per query: what it cost, and what a defensible fix would recover.
CREATE OR REPLACE VIEW cost_per_query AS
SELECT
    query_id,
    "user",
    department,
    statement_type,
    "table",
    table_bytes,
    partition_filter,
    bytes_scanned,
    duration_seconds,
    CAST(started_at AS TIMESTAMP) AS started_at,
    CAST(CAST(started_at AS TIMESTAMP) AS DATE) AS query_date,
    pattern,
    ROUND(bytes_scanned / 1000000000000.0 * $price_per_tb, 4) AS cost_usd,
    CASE
        WHEN pattern = 'select_star_no_filter'
            THEN ROUND(GREATEST(bytes_scanned - table_bytes * $filter_selectivity, 0)
                       / 1000000000000.0 * $price_per_tb, 4)
        WHEN pattern = 'repeated_dashboard'
            THEN ROUND(bytes_scanned * $materialization_reduction
                       / 1000000000000.0 * $price_per_tb, 4)
        WHEN pattern = 'full_rebuild'
            THEN ROUND(GREATEST(bytes_scanned - table_bytes * $filter_selectivity, 0)
                       * $incremental_reduction / 1000000000000.0 * $price_per_tb, 4)
        ELSE 0
    END AS estimated_saving_usd,
    CASE pattern
        WHEN 'select_star_no_filter' THEN 'Filter on the partition column'
        WHEN 'repeated_dashboard' THEN 'Materialise the result or add a cache'
        WHEN 'full_rebuild' THEN 'Switch the load to incremental'
        ELSE ''
    END AS recommendation
FROM query_history;
