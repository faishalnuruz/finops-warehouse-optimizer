import json
from pathlib import Path

import pytest

from finops_optimizer import runner
from finops_optimizer.cost import DEFAULT_MODEL


def test_models_build_the_expected_views(history_frame):
    result = runner.run_models(history_frame)

    assert set(result.views) == {
        "cost_per_query",
        "cost_by_department",
        "cost_by_user",
        "top_offenders",
        "daily_trend",
        "recommendations",
    }
    assert result.models_run == sorted(result.models_run)
    assert result.models_run[0].startswith("01_")


def test_cost_per_query_matches_the_model(history_frame):
    result = runner.run_models(history_frame)
    per_query = result.frame("cost_per_query")

    assert len(per_query) == len(history_frame)
    expected = history_frame["bytes_scanned"].sum() / 1e12 * DEFAULT_MODEL.price_per_tb_usd
    # The model rounds each row to four decimals, so allow a cent of slack.
    assert per_query["cost_usd"].sum() == pytest.approx(expected, abs=0.01)


def test_aggregates_reconcile_with_the_query_level_view(history_frame):
    result = runner.run_models(history_frame)
    per_query = result.frame("cost_per_query")

    departments = result.frame("cost_by_department")
    assert departments["queries"].sum() == len(per_query)
    assert departments["total_cost_usd"].sum() == pytest.approx(per_query["cost_usd"].sum(), rel=1e-4)

    trend = result.frame("daily_trend")
    assert trend["queries"].sum() == len(per_query)
    assert trend["cost_usd"].sum() == pytest.approx(per_query["cost_usd"].sum(), rel=1e-4)

    top = result.frame("top_offenders")
    assert top["cost_usd"].is_monotonic_decreasing


def test_recommendations_only_contain_flagged_patterns(history_frame):
    result = runner.run_models(history_frame)
    recommendations = result.frame("recommendations")

    assert len(recommendations) > 0
    assert set(recommendations["pattern"]) <= {
        "select_star_no_filter",
        "repeated_dashboard",
        "full_rebuild",
    }
    assert (recommendations["estimated_saving_usd"] > 0).all()
    assert (recommendations["recommendation"] != "").all()


def test_models_are_idempotent(history_frame):
    first = runner.run_models(history_frame).frame("cost_per_query")
    second = runner.run_models(history_frame).frame("cost_per_query")

    assert first.equals(second)


def test_missing_history_file_says_how_to_create_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="generate_query_history"):
        runner.load_history(tmp_path / "absent.json")


def test_history_round_trips_through_json(tmp_path, history):
    from dataclasses import asdict

    path = tmp_path / "history.json"
    path.write_text(json.dumps([asdict(query) for query in history]))

    frame = runner.load_history(path)

    assert len(frame) == len(history)
    assert "cost_usd" not in frame.columns  # cost is derived by the models, never stored


def test_models_dir_defaults_next_to_the_package():
    assert Path(runner.MODELS_DIR).name == "models"
    assert list(Path(runner.MODELS_DIR).glob("*.sql"))
