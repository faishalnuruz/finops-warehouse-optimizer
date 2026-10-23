"""Command line entry point.

    python -m finops_optimizer.cli --input data/query_history.json

Runs the SQL models, evaluates the alert rules, prints a summary, and writes the
static report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finops_optimizer import alerts, report, runner
from finops_optimizer.cost import DEFAULT_MODEL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("data/query_history.json"))
    parser.add_argument("--models-dir", type=Path, default=runner.MODELS_DIR)
    parser.add_argument("--budgets", type=Path, default=Path("config/budgets.json"))
    parser.add_argument("--report", type=Path, default=report.DEFAULT_OUTPUT)
    parser.add_argument("--monthly-days", type=int, default=30)
    parser.add_argument("--no-report", action="store_true", help="skip writing the HTML report")
    parser.add_argument("--json", action="store_true", help="print the payload instead of a summary")
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="exit with code 3 when a critical finding exists (for scheduled jobs)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    history = runner.load_history(args.input)
    result = runner.run_models(history, models_dir=args.models_dir)
    budgets = json.loads(args.budgets.read_text()) if args.budgets.exists() else None
    findings = alerts.evaluate(result, budgets=budgets, monthly_days=args.monthly_days)

    payload = report.build_payload(
        result, findings, monthly_days=args.monthly_days, input_path=args.input
    )

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        kpis = payload["kpis"]
        print(
            f"{payload['window']['days']} days, {kpis['queries']:,} queries, "
            f"${kpis['total_cost_usd']:,.2f} scanned"
        )
        print(f"  run rate        ${kpis['monthly_run_rate_usd']:,.0f} / month")
        print(
            f"  recoverable     ${kpis['recoverable_usd']:,.2f} "
            f"({kpis['recoverable_share']:.1%} of spend, by the stated assumptions)"
        )
        print(f"  queries over ${DEFAULT_MODEL.single_query_alert_usd:,.0f}  {kpis['expensive_queries']:,}")
        print(f"\n{len(findings)} finding(s):")
        for finding in findings:
            print(f"  [{finding.severity:8}] {finding.subject}: {finding.message}")

    if not args.no_report:
        print(f"\nReport: {report.render(payload, args.report)}")

    if args.fail_on_critical and any(finding.severity == "critical" for finding in findings):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
