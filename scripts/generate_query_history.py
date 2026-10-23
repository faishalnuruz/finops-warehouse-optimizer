"""Generate a believable warehouse query history.

Real cost work starts from an audit log nobody can share, so this produces a
synthetic one whose economics match a real warehouse:

* cost follows bytes scanned, and bytes scanned depends on the table's size and
  whether the query filtered on its partition column;
* filtering is roughly two orders of magnitude cheaper, which is why one
  unfiltered query can cost more than a month of dashboards;
* nightly full rebuilds are legitimately expensive, while ``SELECT`` queries
  that ignore an available partition filter are genuinely avoidable. Keeping
  those two apart is the difference between a useful FinOps report and a
  report that tells engineers to stop doing their jobs.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

GB = 1_000_000_000

# BigQuery on-demand list price: you pay for bytes scanned, which is exactly why
# an unfiltered scan is the classic cost incident.
PRICE_PER_TB_USD = 6.25

# table, partition column (None means the table cannot be filtered), size
# Sizes are per day of history, which is why one unfiltered scan of the events
# table is a $12 decision while a filtered one costs cents.
TABLES = (
    ("commerce.fct_orders", "order_date", 120 * GB),
    ("commerce.fct_order_items", "order_date", 400 * GB),
    ("commerce.dim_customers", None, 2 * GB),
    ("commerce.dim_products", None, 1 * GB),
    ("warehouse.stg_events", "event_date", 2_000 * GB),
    ("warehouse.fct_sessions", "session_date", 700 * GB),
    ("finance.fct_invoices", "invoice_date", 40 * GB),
)

TOTAL_TABLE_BYTES = sum(size for _, _, size in TABLES)

DEPARTMENTS = {
    # team -> (share of queries, share of SELECTs that filter on the partition column)
    "Marketing": (0.28, 0.78),
    "Finance": (0.12, 0.90),
    "Product": (0.22, 0.88),
    "Data Platform": (0.20, 0.98),
    "Executive": (0.06, 0.68),
    "Support": (0.12, 0.84),
}

USERS = {
    "Marketing": ["ana.marketing", "budi.growth", "clara.ads"],
    "Finance": ["dedi.finance", "erwin.controlling"],
    "Product": ["fajar.product", "gita.analytics"],
    "Data Platform": ["hadi.platform", "intan.eng", "joko.etl"],
    "Executive": ["ceo.dashboard"],
    "Support": ["lia.support", "maya.cx"],
}

STATEMENT_TYPES = ("SELECT", "INSERT", "CREATE_TABLE_AS_SELECT", "MERGE")
STATEMENT_WEIGHTS = (0.82, 0.07, 0.06, 0.05)
REBUILD_TYPES = ("INSERT", "CREATE_TABLE_AS_SELECT", "MERGE")

# Filters on a date partition touch days, not months: ~0.1%-2% of the table.
FILTER_SELECTIVITY = (0.001, 0.02)
FULL_SCAN_SELECTIVITY = (0.90, 1.00)


@dataclass
class Query:
    query_id: str
    user: str
    department: str
    statement_type: str
    table: str
    table_bytes: int
    partition_filter: bool
    bytes_scanned: int
    duration_seconds: float
    started_at: str
    pattern: str  # "select_star_no_filter" | "repeated_dashboard" | "full_rebuild" | ""

    @property
    def cost_usd(self) -> float:
        return round(self.bytes_scanned / 1e12 * PRICE_PER_TB_USD, 6)

    @property
    def avoidable(self) -> bool:
        """Queries that scanned data a filter could have skipped."""
        return self.pattern in {"select_star_no_filter", "repeated_dashboard"}


def generate_history(
    days: int = 14,
    queries_per_day: int = 1800,
    seed: int = 7,
    start: datetime | None = None,
) -> list[Query]:
    rng = random.Random(seed)
    # Default to the last `days` whole days, so the window is exactly that many
    # calendar dates and the monthly run rate extrapolates cleanly.
    start = start or (datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days))
    departments = list(DEPARTMENTS)
    weights = [DEPARTMENTS[name][0] for name in departments]

    queries: list[Query] = []
    for day in range(days):
        for _ in range(queries_per_day):
            department = rng.choices(departments, weights=weights)[0]
            filter_propensity = DEPARTMENTS[department][1]

            # Working hours carry most of the traffic.
            hour = rng.choices(range(24), weights=[3 if 8 <= h <= 19 else 1 for h in range(24)])[0]
            started = start + timedelta(
                days=day, hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60)
            )

            table, partition_column, table_bytes = rng.choice(TABLES)
            statement_type = rng.choices(STATEMENT_TYPES, weights=STATEMENT_WEIGHTS)[0]
            rebuild = statement_type in REBUILD_TYPES

            # Nightly rebuilds read the whole table; ad-hoc SELECTs mostly filter.
            if partition_column is None or rebuild:
                partition_filter = False
            else:
                partition_filter = rng.random() < filter_propensity

            if partition_filter:
                scanned = int(table_bytes * rng.uniform(*FILTER_SELECTIVITY))
            else:
                scanned = int(table_bytes * rng.uniform(*FULL_SCAN_SELECTIVITY))

            pattern = ""
            if partition_column is not None and not partition_filter:
                if statement_type == "SELECT":
                    pattern = "select_star_no_filter"
                elif rebuild:
                    # Legitimate but reviewable: an incremental build would read days.
                    pattern = "full_rebuild"
            elif statement_type == "SELECT" and table_bytes >= 100 * GB and rng.random() < 0.18:
                # The same dashboard, re-run all day, against a large table.
                pattern = "repeated_dashboard"

            duration = round(scanned / rng.uniform(3e8, 9e8) + rng.uniform(0.4, 6.0), 2)

            queries.append(
                Query(
                    query_id=f"q{len(queries):07d}",
                    user=rng.choice(USERS[department]),
                    department=department,
                    statement_type=statement_type,
                    table=table,
                    table_bytes=table_bytes,
                    partition_filter=partition_filter,
                    bytes_scanned=scanned,
                    duration_seconds=duration,
                    started_at=started.isoformat(),
                    pattern=pattern,
                )
            )
    return queries


def write_json(queries: list[Query], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(query) for query in queries], indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--queries-per-day", type=int, default=1800)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=Path("data/query_history.json"))
    args = parser.parse_args()

    queries = generate_history(days=args.days, queries_per_day=args.queries_per_day, seed=args.seed)
    write_json(queries, args.output)

    total = sum(query.cost_usd for query in queries)
    avoidable = [query for query in queries if query.avoidable]
    rebuilds = [query for query in queries if query.pattern == "full_rebuild"]
    avoidable_cost = sum(query.cost_usd for query in avoidable)
    rebuild_cost = sum(query.cost_usd for query in rebuilds)

    print(f"Wrote {len(queries):,} queries to {args.output}")
    print(f"Modelled cost: ${total:,.2f} over {args.days} days (${total / args.days * 30:,.0f}/month)")
    print(
        f"Avoidable (SELECT ignoring a partition filter, repeated dashboards): "
        f"{len(avoidable):,} queries, ${avoidable_cost:,.2f} = {avoidable_cost / total:.1%} of cost"
    )
    print(
        f"Reviewable full rebuilds: {len(rebuilds):,} queries, ${rebuild_cost:,.2f} = "
        f"{rebuild_cost / total:.1%} of cost (legitimate, but incremental loads would be cheaper)"
    )


if __name__ == "__main__":
    main()
