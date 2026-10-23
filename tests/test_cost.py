import pytest

from finops_optimizer.cost import DEFAULT_MODEL, CostModel

TB = 1_000_000_000_000
GB = 1_000_000_000


def test_cost_is_bytes_times_the_list_price():
    # 2 TB at $6.25/TB
    assert DEFAULT_MODEL.cost_usd(2 * TB) == pytest.approx(12.50)
    # 300 GB, the classic single-table scan
    assert DEFAULT_MODEL.cost_usd(300 * GB) == pytest.approx(1.875)


def test_a_partition_filter_removes_almost_all_of_the_saving():
    model = CostModel()
    full_scan = 300 * GB
    table = 300 * GB

    saving = model.estimated_saving_usd(full_scan, table, "select_star_no_filter")

    # What is left after a filter reads 2% of the table, converted to dollars.
    assert saving == pytest.approx(model.cost_usd(full_scan - table * 0.02))
    assert saving < model.cost_usd(full_scan)


def test_materialisation_saving_is_a_fraction_of_the_rescans():
    model = CostModel(materialization_reduction=0.9)

    saving = model.estimated_saving_usd(10 * GB, 500 * GB, "repeated_dashboard")

    assert saving == pytest.approx(model.cost_usd(int(10 * GB * 0.9)))


def test_incremental_saving_is_conservative():
    model = CostModel()
    table = 900 * GB

    full = model.estimated_saving_usd(table, table, "full_rebuild")
    naive = model.cost_usd(table - table * model.filter_selectivity)

    # Both sides are rounded to four decimals on the way out, so compare at cent scale.
    assert full == pytest.approx(naive * model.incremental_reduction, abs=0.01)
    assert full < naive


def test_ordinary_queries_never_claim_a_saving():
    """Otherwise the report would inflate the opportunity by counting real work."""

    assert DEFAULT_MODEL.estimated_saving_usd(500 * GB, 900 * GB, "") == 0
    assert DEFAULT_MODEL.estimated_saving_usd(500 * GB, 900 * GB, "unpartitioned_join") == 0


def test_assumptions_are_published_with_templates():
    model = CostModel()

    assumptions = model.assumptions()
    context = model.template_context()

    assert assumptions["price_per_tb_usd"] == 6.25
    assert set(context) == {
        "price_per_tb",
        "filter_selectivity",
        "materialization_reduction",
        "incremental_reduction",
    }
    assert context["filter_selectivity"] == "0.02"
