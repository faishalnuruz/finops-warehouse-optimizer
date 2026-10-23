"""A very small SQL model runner.

The transformations are plain SQL files that build views in order, in the spirit
of dbt but without the dependency: ``01_x.sql`` can select from the view created
by ``01_`` .. ``NN_`` before it. Cost assumptions are injected as template
values so the pricing never gets copy-pasted into SQL.
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from finops_optimizer.cost import DEFAULT_MODEL, CostModel

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


@dataclass
class RunResult:
    """The materialised views and what built them."""

    views: dict[str, pd.DataFrame]
    models_run: list[str]

    def frame(self, name: str) -> pd.DataFrame:
        if name not in self.views:
            raise KeyError(f"model {name!r} was not built (have: {sorted(self.views)})")
        return self.views[name]


def load_history(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Generate it first: python scripts/generate_query_history.py"
        )
    records = json.loads(path.read_text())
    return pd.DataFrame.from_records(records)


def _render(sql: str, context: dict[str, str]) -> str:
    return string.Template(sql).substitute(context)


def run_models(
    history: pd.DataFrame,
    models_dir: Path = MODELS_DIR,
    model: CostModel = DEFAULT_MODEL,
) -> RunResult:
    """Execute every SQL model in filename order and capture the resulting views."""
    connection = duckdb.connect()
    connection.register("query_history", history)
    context = model.template_context()

    views: dict[str, pd.DataFrame] = {}
    models_run: list[str] = []

    for sql_file in sorted(models_dir.glob("*.sql")):
        sql = _render(sql_file.read_text(), context)
        connection.execute(sql)
        models_run.append(sql_file.stem)
        # Naming convention: the created view matches the file stem after the order prefix.
        view_name = sql_file.stem.split("_", 1)[1]
        views[view_name] = connection.execute(f"SELECT * FROM {view_name}").fetchdf()

    connection.close()
    return RunResult(views=views, models_run=models_run)
