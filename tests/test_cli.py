import json
from dataclasses import asdict

import pytest

from finops_optimizer import cli


@pytest.fixture
def history_path(tmp_path, history):
    path = tmp_path / "history.json"
    path.write_text(json.dumps([asdict(query) for query in history]))
    return path


def test_summary_run_writes_a_report(history_path, tmp_path, capsys):
    report_path = tmp_path / "report.html"

    code = cli.main([
        "--input", str(history_path),
        "--report", str(report_path),
        "--budgets", str(tmp_path / "absent-budgets.json"),
    ])

    output = capsys.readouterr().out
    assert code == 0
    assert "days," in output and "queries" in output
    assert "run rate" in output
    assert report_path.exists()


def test_json_payload_is_parseable(history_path, capsys):
    cli.main(["--input", str(history_path), "--no-report", "--json"])

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["kpis"]["queries"] > 0
    assert payload["daily"]


def test_no_report_flag_skips_the_file(history_path, tmp_path, capsys):
    cli.main(["--input", str(history_path), "--no-report", "--report", str(tmp_path / "never.html")])

    assert not (tmp_path / "never.html").exists()


def test_fail_on_critical_uses_a_distinct_exit_code(tmp_path, capsys):
    """Scheduled jobs can alert on the exit code without parsing output."""
    import pandas as pd

    GB = 1_000_000_000
    records = [{
        "query_id": f"q{index}",
        "user": "ana.marketing",
        "department": "Marketing",
        "statement_type": "SELECT",
        "table": "warehouse.stg_events",
        "table_bytes": 2000 * GB,
        "partition_filter": False,
        "bytes_scanned": 2000 * GB,
        "duration_seconds": 30.0,
        "started_at": "2026-01-01T02:00:00+00:00",
        "pattern": "select_star_no_filter",
    } for index in range(3)]
    path = tmp_path / "expensive.json"
    path.write_text(pd.DataFrame(records).to_json(orient="records"))

    code = cli.main(["--input", str(path), "--no-report", "--fail-on-critical"])
    benign = cli.main(["--input", str(path), "--no-report"])

    assert code == 3
    assert benign == 0
    assert "critical" in capsys.readouterr().out


def test_missing_input_explains_itself(tmp_path):
    with pytest.raises(FileNotFoundError, match="generate_query_history"):
        cli.main(["--input", str(tmp_path / "absent.json"), "--no-report"])
