import pandas as pd

from finops_optimizer import alerts, runner
from finops_optimizer.cost import CostModel

GB = 1_000_000_000

BASE = {
    "query_id": "q1",
    "user": "ana.marketing",
    "department": "Marketing",
    "statement_type": "SELECT",
    "table": "warehouse.stg_events",
    "table_bytes": 900 * GB,
    "partition_filter": False,
    "bytes_scanned": 900 * GB,
    "duration_seconds": 12.0,
    "started_at": "2026-01-01T02:00:00+00:00",
    "pattern": "select_star_no_filter",
}


def result_for(rows: list[dict]):
    frame = pd.DataFrame.from_records([{**BASE, **row} for row in rows])
    frame["query_id"] = [f"q{index}" for index in range(len(frame))]
    return runner.run_models(frame)


def test_a_single_expensive_query_is_a_critical_finding():
    # 900 GB at $6.25/TB is $5.63, just under the default $10 threshold.
    result = result_for([{"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB}])

    findings = alerts.evaluate(result)

    critical = [finding for finding in findings if finding.severity == "critical"]
    assert critical
    assert critical[0].rule == "single_query_over_threshold"
    assert "ana.marketing" in critical[0].subject
    assert critical[0].cost_usd > CostModel().single_query_alert_usd
    assert critical[0].recommendation


def test_cheap_queries_produce_no_finding():
    result = result_for([
        {
            "bytes_scanned": 2 * GB,
            "table_bytes": 900 * GB,
            "partition_filter": True,
            "pattern": "",
        }
    ])

    assert alerts.evaluate(result) == []


def test_many_expensive_queries_are_summarised_not_spammed():
    result = result_for([{"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB} for _ in range(9)])

    findings = alerts.evaluate(result, max_single_query_findings=5)

    single = [f for f in findings if f.rule == "single_query_over_threshold"]
    assert len(single) == 6  # five examples plus one summary
    summary = single[-1]
    assert "9 queries" in summary.subject
    assert summary.severity == "warning"


def test_department_over_budget_warns_and_far_over_budget_pages():
    result = result_for([{"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB}])

    # One $12.50 query in a one-day window extrapolates to $375/month, so a $300
    # budget is a warning (1.25x plan) and a $100 budget is a breach (3.75x plan).
    warning = alerts.evaluate(result, budgets={"Marketing": 300, "default": 10_000})
    critical = alerts.evaluate(result, budgets={"Marketing": 100, "default": 10_000})

    def budget_findings(findings):
        return [finding for finding in findings if finding.rule == "department_budget_breach"]

    assert len(budget_findings(warning)) == 1
    assert budget_findings(warning)[0].severity == "warning"
    assert len(budget_findings(critical)) == 1
    assert budget_findings(critical)[0].severity == "critical"
    assert "budget" in budget_findings(critical)[0].message


def test_no_budgets_means_no_budget_findings():
    result = result_for([{"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB}])

    findings = alerts.evaluate(result, budgets=None)

    assert all(finding.rule != "department_budget_breach" for finding in findings)


def test_dominant_pattern_needs_to_clear_the_floor():
    result = result_for([{"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB}])

    quiet = alerts.evaluate(result, dominant_pattern_floor_usd=1_000_000)
    loud = alerts.evaluate(result, dominant_pattern_floor_usd=1)

    assert all(f.rule != "dominant_avoidable_pattern" for f in quiet)
    assert any(f.rule == "dominant_avoidable_pattern" for f in loud)


def test_findings_are_sorted_by_severity_then_cost():
    result = result_for([
        {"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB},
        {"bytes_scanned": 1000 * GB, "table_bytes": 1000 * GB},
    ])

    findings = alerts.evaluate(result, budgets={"Marketing": 20, "default": 10_000})
    severities = [f.severity for f in findings]
    print([(f.rule, f.severity, f.cost_usd) for f in findings])

    assert severities == sorted(severities, key=lambda value: alerts.SEVERITY_ORDER[value])
    critical_costs = [f.cost_usd for f in findings if f.severity == "critical"]
    assert critical_costs == sorted(critical_costs, reverse=True)


def test_finding_serialises_for_the_report():
    result = result_for([{"bytes_scanned": 2000 * GB, "table_bytes": 2000 * GB}])

    payload = alerts.evaluate(result)[0].as_dict()

    assert set(payload) == {"rule", "severity", "subject", "message", "cost_usd", "recommendation"}
    assert isinstance(payload["cost_usd"], float)
