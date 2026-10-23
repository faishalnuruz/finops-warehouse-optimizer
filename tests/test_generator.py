import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_query_history import (
    GB,
    REBUILD_TYPES,
    TABLES,
    generate_history,
)

PARTITIONED = {name for name, column, _ in TABLES if column}
SIZES = {name: size for name, _, size in TABLES}


def test_generation_is_deterministic_for_a_seed_and_start():
    # `start` defaults to now, so pin it to compare two runs.
    when = datetime(2026, 1, 1, tzinfo=UTC)
    first = generate_history(days=1, queries_per_day=50, seed=3, start=when)
    second = generate_history(days=1, queries_per_day=50, seed=3, start=when)
    other = generate_history(days=1, queries_per_day=50, seed=4, start=when)

    assert [asdict(query) for query in first] == [asdict(query) for query in second]
    assert [asdict(query) for query in first] != [asdict(query) for query in other]


def test_every_query_scans_at_most_its_table():
    for query in generate_history(days=2, queries_per_day=300, seed=5):
        assert 0 < query.bytes_scanned <= query.table_bytes
        assert query.table_bytes == SIZES[query.table]


def test_filtering_reduces_what_is_scanned():
    """The whole point of the report: filters are cheap, full scans are not."""
    queries = generate_history(days=3, queries_per_day=400, seed=6)
    filtered = [q for q in queries if q.partition_filter]
    unfiltered = [q for q in queries if not q.partition_filter and q.table in PARTITIONED]

    assert filtered
    assert unfiltered
    mean_filtered = sum(q.bytes_scanned for q in filtered) / len(filtered)
    mean_unfiltered = sum(q.bytes_scanned for q in unfiltered) / len(unfiltered)
    assert mean_filtered < mean_unfiltered / 10


def test_avoidable_queries_are_always_avoidable():
    """A query is only flagged if a filter genuinely existed and was skipped."""
    for query in generate_history(days=2, queries_per_day=400, seed=8):
        if query.pattern == "select_star_no_filter":
            assert query.table in PARTITIONED
            assert query.partition_filter is False
            assert query.statement_type == "SELECT"
        if query.pattern == "repeated_dashboard":
            assert query.statement_type == "SELECT"
            assert query.table_bytes >= 100 * GB
        if query.pattern == "full_rebuild":
            assert query.statement_type in REBUILD_TYPES
            assert query.table in PARTITIONED
            assert query.partition_filter is False


def test_nightly_rebuilds_are_labelled_separately_from_waste():
    """Full rebuilds are legitimate work; calling them waste would be wrong."""
    queries = generate_history(days=2, queries_per_day=400, seed=9)
    rebuilds = [query for query in queries if query.pattern == "full_rebuild"]

    assert rebuilds
    assert all(query.avoidable is False for query in rebuilds)
    assert all(query.statement_type != "SELECT" for query in rebuilds)


def test_departments_and_users_stay_consistent():
    queries = generate_history(days=1, queries_per_day=200, seed=10)
    by_department: dict[str, set[str]] = {}

    for query in queries:
        by_department.setdefault(query.department, set()).add(query.user)

    assert len(by_department) >= 4
    # Each department keeps its own people, so attribution means something.
    seen: dict[str, str] = {}
    for department, users in by_department.items():
        for user in users:
            assert seen.get(user, department) == department
            seen[user] = department
