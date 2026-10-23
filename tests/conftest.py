import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_query_history import generate_history


@pytest.fixture(scope="session")
def history():
    """A small, deterministic slice of the synthetic warehouse."""
    return generate_history(days=3, queries_per_day=400, seed=11)


@pytest.fixture(scope="session")
def history_frame(history):
    from dataclasses import asdict

    import pandas as pd

    return pd.DataFrame.from_records([asdict(query) for query in history])
