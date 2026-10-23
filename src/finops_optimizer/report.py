"""Build the FinOps report payload and render it as one static HTML page."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from finops_optimizer.alerts import Finding
from finops_optimizer.cost import DEFAULT_MODEL, CostModel
from finops_optimizer.runner import RunResult

TEMPLATE = Path(__file__).with_name("report.html")
DEFAULT_OUTPUT = Path("docs/generated/finops-report.html")


def _records(frame: pd.DataFrame, columns: list[str] | None = None, limit: int | None = None) -> list[dict]:
    """JSON-ready records: missing values become null, never NaN."""
    selected = frame.loc[:, columns] if columns else frame
    if limit is not None:
        selected = selected.head(limit)
    return selected.astype(object).where(pd.notna(selected), None).to_dict(orient="records")


def build_payload(
    result: RunResult,
    findings: list[Finding],
    model: CostModel = DEFAULT_MODEL,
    monthly_days: int = 30,
    input_path: Path | None = None,
) -> dict:
    per_query = result.frame("cost_per_query")
    trend = result.frame("daily_trend")
    window_days = max(per_query["query_date"].nunique(), 1)

    total_cost = float(per_query["cost_usd"].sum())
    recoverable = float(per_query["estimated_saving_usd"].sum())
    engine_queries = int(per_query["queries"].sum()) if "queries" in per_query else len(per_query)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "input": str(input_path) if input_path else "query_history",
        "window": {
            "days": window_days,
            "from": str(trend["query_date"].min()),
            "to": str(trend["query_date"].max()),
            "queries": len(per_query),
        },
        "kpis": {
            "total_cost_usd": round(total_cost, 2),
            "daily_cost_usd": round(total_cost / window_days, 2),
            "monthly_run_rate_usd": round(total_cost / window_days * monthly_days, 2),
            "recoverable_usd": round(recoverable, 2),
            "recoverable_share": round(recoverable / total_cost, 4) if total_cost else 0.0,
            "queries": engine_queries,
            "expensive_queries": int((per_query["cost_usd"] >= model.single_query_alert_usd).sum()),
        },
        "assumptions": model.assumptions(),
        "daily": _records(trend),
        "departments": _records(result.frame("cost_by_department")),
        "users": _records(result.frame("cost_by_user"), limit=12),
        "top_offenders": _records(result.frame("top_offenders"), limit=15),
        "recommendations": _records(result.frame("recommendations")),
        "findings": [finding.as_dict() for finding in findings],
        "models_run": result.models_run,
    }


def render(payload: dict, output: Path = DEFAULT_OUTPUT) -> Path:
    document = TEMPLATE.read_text()
    serialized = json.dumps(payload, default=str).replace("</", "<\\/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document.replace("__PAYLOAD__", serialized))
    return output
