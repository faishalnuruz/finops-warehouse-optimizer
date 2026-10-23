# Architecture and decisions

## Flow

```text
query history (generated, or exported from INFORMATION_SCHEMA.JOBS)
        |
        v
  DuckDB  +  models/*.sql  (pricing injected as template values)
        |
        +--> cost_per_query ------> cost_by_department ---> accountability
        |                      \--> cost_by_user
        |                      \--> top_offenders -------> the list to open first
        |                      \--> daily_trend
        |                      \--> recommendations -----> what to schedule
        |
        v
  alert rules (single query / budget breach / dominant pattern)
        |
        v
  static report + exit code (0 ok, 3 critical) for scheduled jobs
```

## Decisions worth defending

**The pricing lives in one Python object, not in the SQL.** Models receive `$price_per_tb` and the
saving assumptions as template values, so a change to the cost model is a one-line diff and the
report's methodology block is guaranteed to describe the arithmetic that actually ran.

**`full_rebuild` is not called waste.** A nightly rebuild that scans a whole table is legitimate
work; an incremental load would be cheaper, so it is reported as *reviewable* with a conservative
50% reduction. Labelling real engineering as waste is how a cost report gets ignored — and the
generator's own tests assert that rebuilds are never flagged as avoidable.

**Avoidable means a filter existed and was skipped.** A query is only flagged
`select_star_no_filter` when its table has a partition column, the query is a `SELECT`, and no
filter was applied. Anything else reports a saving of exactly zero.

**Every savings number is an assumption, published.** The report prints the assumptions next to the
headline figure, and the README repeats them. A FinOps number without its assumptions is a
negotiation tactic, not engineering.

**Alert fatigue is designed against.** Hundreds of queries over threshold become one summary
finding; only single queries, budget breaches, and dominant patterns interrupt anyone.

**Exit codes are an interface.** `--fail-on-critical` returns 3 so a scheduler can alert on the run
without parsing text.

**DuckDB, not a warehouse.** The models are ordinary SQL and the engine is local, so the whole thing
runs in a second with no account, no credentials, and no cost of its own.

## Failure modes

| What breaks | What happens |
| --- | --- |
| History file is missing | `FileNotFoundError` naming the generator command to run |
| History is empty | Models return empty views; the report states zero spend rather than failing |
| A table has no partition column | Queries against it can never be flagged avoidable |
| Budget file is absent | Budget findings are skipped; the other two rules still run |
| A department has no budget entry | Falls back to `default` in the budget file |
| Cost is zero for a query | Saving is zero; no division by zero in the share columns (`NULLIF`) |
| Report opened offline | Charts need the Chart.js CDN; the tables still render |
