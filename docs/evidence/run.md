# Evidence: end-to-end run

Captured on 2026-10-23 with the default seeded generator (14 days, 1,800 queries/day, seed 7).
Reproduce with:

```bash
python scripts/generate_query_history.py
.venv/bin/python -m finops_optimizer.cli --input data/query_history.json
```

## What the generator produced

```text
Wrote 25,200 queries to data/query_history.json
Modelled cost: $21,548.46 over 14 days ($46,175/month)
Avoidable (SELECT ignoring a partition filter, repeated dashboards): 3,840 queries, $8,188.64 = 38.0% of cost
Reviewable full rebuilds: 3,365 queries, $12,853.27 = 59.6% of cost (legitimate, but incremental loads would be cheaper)
```

## What the pipeline reported

```text
14 days, 25,200 queries, $21,548.47 scanned
  run rate        $46,175 / month
  recoverable     $14,300.33 (66.4% of spend, by the stated assumptions)
  queries over $10  1,090

15 finding(s):
  [critical] q0015452 (clara.ads): One SELECT on warehouse.stg_events scanned 2,000 GB for $12.50 (threshold $10.00).
  [critical] q0018535 (gita.analytics): One INSERT on warehouse.stg_events scanned 1,999 GB for $12.50 (threshold $10.00).
  [critical] q0019343 (hadi.platform): One SELECT on warehouse.stg_events scanned 1,999 GB for $12.50 (threshold $10.00).
  [critical] q0015277 (hadi.platform): One CREATE_TABLE_AS_SELECT on warehouse.stg_events scanned 1,999 GB for $12.49 (threshold $10.00).
  [critical] q0002654 (budi.growth): One SELECT on warehouse.stg_events scanned 1,999 GB for $12.49 (threshold $10.00).
  [warning ] 1090 queries over threshold: 1090 queries exceeded $10.00; the five costliest are listed above.
  [warning ] Marketing: Marketing is running at $16,006/month against a $12,000 budget (133% of plan); $5,310 of the window is flagged as avoidable.
  [warning ] select_star_no_filter on warehouse.stg_events: 422 queries with pattern select_star_no_filter on warehouse.stg_events cost $5,027.79, of which $4,922.29 looks recoverable.
  [warning ] full_rebuild on warehouse.stg_events: 668 queries with pattern full_rebuild on warehouse.stg_events cost $7,941.64, of which $3,887.32 looks recoverable.
  [warning ] select_star_no_filter on warehouse.fct_sessions: 418 queries with pattern select_star_no_filter on warehouse.fct_sessions cost $1,735.56, of which $1,698.98 looks recoverable.
  [warning ] full_rebuild on warehouse.fct_sessions: 646 queries with pattern full_rebuild on warehouse.fct_sessions cost $2,680.74, of which $1,312.11 looks recoverable.
  [warning ] select_star_no_filter on commerce.fct_order_items: 388 queries with pattern select_star_no_filter on commerce.fct_order_items cost $920.93, of which $901.53 looks recoverable.
  [warning ] full_rebuild on commerce.fct_order_items: 662 queries with pattern full_rebuild on commerce.fct_order_items cost $1,570.15, of which $768.53 looks recoverable.
  [warning ] select_star_no_filter on commerce.fct_orders: 436 queries with pattern select_star_no_filter on commerce.fct_orders cost $309.89, of which $303.35 looks recoverable.
  [warning ] Executive: Executive is running at $3,850/month against a $3,000 budget (128% of plan); $1,366 of the window is flagged as avoidable.
```

## What to observe

- **Attribution works.** Marketing's $7,469.67 of the window's $21,548.47 is 34.7% of spend, and
  71.1% of Marketing's spend carries a recommendation.
- **The strongest single fix is shaped like real life.** 422 unfiltered `SELECT`s against the
  events table cost $5,027.79, of which $4,922.29 is recoverable by filtering a column that
  already exists.
- **Legitimate work is labelled as such.** 668 nightly rebuilds of the same table cost $7,941.64
  and are reported as reviewable, not waste.
- **The per-query rule catches the accidents a monthly invoice hides.** Five individual queries
  over $10, all full scans of the events table, including two run by the platform team itself.
- **Findings are ordered by what to do first**, and a rule that fires 1,090 times is summarised
  once instead of repeated.

## Report

`docs/screenshots/finops-report.png` is the rendered `docs/generated/finops-report.html` from this
exact run — ledger summary, triage-ordered findings, spend trend with the avoidable share shaded,
department and user attribution, recommendations, and the methodology block listing the
assumptions.

## Exit codes

```text
$ .venv/bin/python -m finops_optimizer.cli --input data/query_history.json --no-report --fail-on-critical
$ echo $?
3
```

## Tests

```text
$ .venv/bin/python -m pytest -q
38 passed in 1.34s
$ .venv/bin/ruff check .
All checks passed!
```
