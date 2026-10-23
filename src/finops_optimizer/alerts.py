"""Turn the aggregates into findings worth interrupting somebody for.

The point of a FinOps alert is to arrive *before* the invoice, while the query
that caused it is still in someone's memory and can still be fixed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from finops_optimizer.cost import DEFAULT_MODEL, CostModel
from finops_optimizer.runner import RunResult

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    rule: str
    severity: str
    subject: str
    message: str
    cost_usd: float
    recommendation: str

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate(
    result: RunResult,
    budgets: dict | None = None,
    model: CostModel = DEFAULT_MODEL,
    monthly_days: int = 30,
    dominant_pattern_floor_usd: float = 250.0,
    max_single_query_findings: int = 5,
) -> list[Finding]:
    """Apply the three rules a warehouse owner actually cares about."""
    findings: list[Finding] = []
    per_query = result.frame("cost_per_query")
    window_days = max(per_query["query_date"].nunique(), 1)

    # Rule 1: a single query expensive enough to be an incident on its own.
    expensive = per_query[per_query["cost_usd"] >= model.single_query_alert_usd]
    expensive = expensive.sort_values("cost_usd", ascending=False)
    for row in expensive.head(max_single_query_findings).itertuples():
        findings.append(
            Finding(
                rule="single_query_over_threshold",
                severity="critical",
                subject=f"{row.query_id} ({row.user})",
                message=(
                    f"One {row.statement_type} on {row.table} scanned "
                    f"{row.bytes_scanned / 1e9:,.0f} GB for ${row.cost_usd:,.2f} "
                    f"(threshold ${model.single_query_alert_usd:,.2f})."
                ),
                cost_usd=float(row.cost_usd),
                recommendation=row.recommendation or "Review the query with its author",
            )
        )
    if len(expensive) > max_single_query_findings:
        findings.append(
            Finding(
                rule="single_query_over_threshold",
                severity="warning",
                subject=f"{len(expensive)} queries over threshold",
                message=(
                    f"{len(expensive)} queries exceeded ${model.single_query_alert_usd:,.2f}; "
                    f"the five costliest are listed above."
                ),
                cost_usd=float(expensive["cost_usd"].sum()),
                recommendation="Triage the full list by writing them back to the owning team",
            )
        )

    # Rule 2: a department heading for a budget breach at this run rate.
    if budgets:
        for row in result.frame("cost_by_department").itertuples():
            budget = budgets.get(row.department, budgets.get("default"))
            if not budget:
                continue
            run_rate = row.total_cost_usd / window_days * monthly_days
            if run_rate <= budget:
                continue
            over = run_rate / budget
            findings.append(
                Finding(
                    rule="department_budget_breach",
                    severity="critical" if over >= 1.5 else "warning",
                    subject=row.department,
                    message=(
                        f"{row.department} is running at ${run_rate:,.0f}/month against a "
                        f"${budget:,.0f} budget ({over:.0%} of plan); "
                        f"${row.estimated_saving_usd:,.0f} of the window is flagged as avoidable."
                    ),
                    cost_usd=float(row.estimated_saving_usd),
                    recommendation="Share the top-offender list with the team before the next cycle",
                )
            )

    # Rule 3: one pattern-and-table pair carrying a lot of avoidable spend.
    for row in result.frame("recommendations").itertuples():
        if row.estimated_saving_usd < dominant_pattern_floor_usd:
            continue
        findings.append(
            Finding(
                rule="dominant_avoidable_pattern",
                severity="warning",
                subject=f"{row.pattern} on {row.table}",
                message=(
                    f"{row.occurrences} queries with pattern {row.pattern} on {row.table} "
                    f"cost ${row.total_cost_usd:,.2f}, of which ${row.estimated_saving_usd:,.2f} "
                    f"looks recoverable."
                ),
                cost_usd=float(row.estimated_saving_usd),
                recommendation=row.recommendation,
            )
        )

    findings.sort(key=lambda finding: (SEVERITY_ORDER.get(finding.severity, 9), -finding.cost_usd))
    return findings
