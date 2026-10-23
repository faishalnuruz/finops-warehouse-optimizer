"""The cost model, in one place.

Every number the report produces traces back to these constants, and every
savings figure is an *estimate* with a stated assumption rather than a promise.
Being explicit about the assumption is what makes the difference between a cost
report an engineer trusts and one they ignore.
"""

from __future__ import annotations

from dataclasses import dataclass

BYTES_PER_TB = 1_000_000_000_000


@dataclass(frozen=True)
class CostModel:
    """Pricing and the assumptions behind each recommendation."""

    price_per_tb_usd: float = 6.25
    # A query that filters on the partition column reads days, not months.
    filter_selectivity: float = 0.02
    # A dashboard result served from a materialised table stops rescanning the source.
    materialization_reduction: float = 0.90
    # An incremental rebuild reads a slice of the table instead of all of it,
    # and only half of that is realistically removable (late data, backfills).
    incremental_reduction: float = 0.50
    # A single query is worth shouting about above this many dollars.
    single_query_alert_usd: float = 10.0

    def cost_usd(self, bytes_scanned: int) -> float:
        return round(bytes_scanned / BYTES_PER_TB * self.price_per_tb_usd, 4)

    def estimated_saving_usd(self, bytes_scanned: int, table_bytes: int, pattern: str) -> float:
        """Estimate the recoverable part of one query's cost.

        Returns 0 for queries with no defensible recommendation, so the report
        never inflates the opportunity by counting ordinary work as waste.
        """
        if pattern == "select_star_no_filter":
            recoverable = max(bytes_scanned - table_bytes * self.filter_selectivity, 0)
        elif pattern == "repeated_dashboard":
            recoverable = bytes_scanned * self.materialization_reduction
        elif pattern == "full_rebuild":
            recoverable = max(bytes_scanned - table_bytes * self.filter_selectivity, 0) * (
                self.incremental_reduction
            )
        else:
            return 0.0
        return round(recoverable / BYTES_PER_TB * self.price_per_tb_usd, 4)

    def assumptions(self) -> dict[str, object]:
        return {
            "price_per_tb_usd": self.price_per_tb_usd,
            "filter_selectivity": self.filter_selectivity,
            "materialization_reduction": self.materialization_reduction,
            "incremental_reduction": self.incremental_reduction,
            "single_query_alert_usd": self.single_query_alert_usd,
        }

    def template_context(self) -> dict[str, str]:
        """Placeholders available to the SQL models."""
        return {
            "price_per_tb": f"{self.price_per_tb_usd}",
            "filter_selectivity": f"{self.filter_selectivity}",
            "materialization_reduction": f"{self.materialization_reduction}",
            "incremental_reduction": f"{self.incremental_reduction}",
        }


DEFAULT_MODEL = CostModel()
