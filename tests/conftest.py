from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def _todas_ntnb() -> pd.DataFrame:
    df = pd.read_csv(DATA / "ntnb_todas_tesouro_direto.csv", sep=";", decimal=",")
    df["db"] = pd.to_datetime(df["Data Base"], dayfirst=True).dt.date
    df["venc"] = pd.to_datetime(df["Data Vencimento"], dayfirst=True).dt.date
    return df[(df.venc > df.db) & (df["PU Venda Manha"] > 0) & (df["Taxa Venda Manha"] > 0)]


@pytest.fixture(scope="session")
def td():
    return _todas_ntnb()
