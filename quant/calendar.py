"""Calendário de dias úteis ANBIMA (feriados nacionais, 2001–2099).

Convenção: du(d1, d2) = nº de dias úteis entre d1 (inclusive) e d2 (exclusive),
exatamente como na metodologia do Tesouro/ANBIMA. Datas não úteis em d2
(ex.: cupom em 15/02 caindo num domingo) são aceitas: o DU conta até ela.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np

_FERIADOS_CSV = Path(__file__).resolve().parent.parent / "data" / "feriados_anbima.csv"
_MIN, _MAX = date(2001, 1, 1), date(2099, 12, 31)


@lru_cache(maxsize=1)
def feriados() -> np.ndarray:
    linhas = _FERIADOS_CSV.read_text().strip().splitlines()[1:]
    return np.array(linhas, dtype="datetime64[D]")


def _checa(d: date) -> None:
    if not (_MIN <= d <= _MAX):
        raise ValueError(f"{d} fora da cobertura do calendário ANBIMA (2001–2099)")


def is_du(d: date) -> bool:
    _checa(d)
    return bool(np.is_busday(np.datetime64(d, "D"), holidays=feriados()))


def du(d1: date, d2: date) -> int:
    """Dias úteis em [d1, d2). Negativo se d2 < d1."""
    _checa(d1)
    _checa(d2)
    return int(np.busday_count(np.datetime64(d1, "D"), np.datetime64(d2, "D"),
                               holidays=feriados()))


def add_du(d: date, n: int) -> date:
    """Avança (n>0) ou recua (n<0) n dias úteis a partir de d (d ajustado para DU seguinte/anterior)."""
    _checa(d)
    roll = "forward" if n >= 0 else "backward"
    r = np.busday_offset(np.datetime64(d, "D"), n, roll=roll, holidays=feriados())
    return r.astype(object)


def dc(d1: date, d2: date) -> int:
    """Dias corridos."""
    return (d2 - d1).days


def proximo_du(d: date) -> date:
    return add_du(d, 0)
