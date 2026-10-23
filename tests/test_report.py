import json

import pandas as pd
import pytest

from finops_optimizer import alerts, report, runner


def test_payload_kpis_reconcile_with_the_models(history_frame):
    result = runner.run_models(history_frame)
    payload = report.build_payload(result, [])

    per_query = result.frame("cost_per_query")
    assert payload["kpis"]["total_cost_usd"] == pytest.approx(per_query["cost_usd"].sum(), abs=0.01)
    assert payload["kpis"]["queries"] == len(per_query)
    assert payload["window"]["days"] == per_query["query_date"].nunique()
    # The KPI is rounded to cents before it reaches the page.
    assert payload["kpis"]["monthly_run_rate_usd"] == pytest.approx(
        payload["kpis"]["total_cost_usd"] / payload["window"]["days"] * 30, abs=0.05
    )


def test_payload_publishes_the_assumptions_and_models(history_frame):
    result = runner.run_models(history_frame)

    payload = report.build_payload(result, [], input_path="data/query_history.json")

    assert payload["assumptions"]["price_per_tb_usd"] == 6.25
    assert payload["models_run"] == result.models_run
    assert payload["input"] == "data/query_history.json"


def test_render_embeds_strict_json(history_frame, tmp_path):
    result = runner.run_models(history_frame)
    findings = alerts.evaluate(result, budgets=None)
    findings.append(
        alerts.Finding(
            rule="single_query_over_threshold",
            severity="critical",
            subject="q0000001 (ana.marketing)",
            message="One SELECT scanned 900 GB for $5.63.",
            cost_usd=5.63,
            recommendation="Filter on the partition column",
        )
    )
    payload = report.build_payload(result, findings)

    path = report.render(payload, tmp_path / "report.html")
    html = path.read_text()

    assert "__PAYLOAD__" not in html
    assert 'id="trend-chart"' in html
    embedded = json.loads(
        html.split("window.__REPORT__ = ", 1)[1].split(";\n", 1)[0],
        parse_constant=lambda value: pytest.fail(f"non-standard JSON constant: {value}"),
    )
    assert embedded["kpis"]["total_cost_usd"] > 0
    assert embedded["findings"]


def test_missing_values_become_null_not_nan():
    frame = pd.DataFrame({"a": [1.0, float("nan")], "b": ["x", "y"]})

    records = report._records(frame)

    assert records[0] == {"a": 1.0, "b": "x"}
    assert records[1]["a"] is None


def test_records_can_be_limited_and_projected(history_frame):
    result = runner.run_models(history_frame)
    payload = report.build_payload(result, [])

    assert len(payload["users"]) <= 12
    assert len(payload["top_offenders"]) <= 15
    assert set(payload["top_offenders"][0]) >= {"query_id", "user", "cost_usd", "recommendation"}
