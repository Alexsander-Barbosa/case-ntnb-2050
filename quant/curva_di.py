"""Curva DI x pré (CDI esperado) com interpolação flat forward 252.

F(du) = fator acumulado de CDI da data de referência até du dias úteis à frente.
- Vértices: F_i = (1 + r_i)^(du_i/252).
- Entre vértices (flat forward): F(du) = F_i * (F_{i+1}/F_i)^((du-du_i)/(du_{i+1}-du_i)).
- Antes do 1º vértice: CDI do dia, F(du) = (1 + CDI)^(du/252).
- Após o último vértice: erro (sem extrapolação silenciosa).
Curva flat (Opção A) = caso particular sem vértices: F(du) = (1 + CDI)^(du/252) para todo du.
"""
from __future__ import annotations

import bisect
import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import calendar as cal


@dataclass(frozen=True)
class CurvaDI:
    data_ref: date
    cdi_dia_pct: float
    dus: tuple[int, ...] = ()
    taxas_pct: tuple[float, ...] = ()
    _fatores: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self):
        if len(self.dus) != len(self.taxas_pct):
            raise ValueError("dus e taxas com tamanhos diferentes")
        if any(b <= a for a, b in zip(self.dus, self.dus[1:])) or (self.dus and self.dus[0] <= 0):
            raise ValueError("vértices devem ter DU positivos e estritamente crescentes")
        fat = tuple((1 + r / 100) ** (d / 252) for d, r in zip(self.dus, self.taxas_pct))
        object.__setattr__(self, "_fatores", fat)

    # ---------------------------------------------------------------- construtores
    @classmethod
    def flat(cls, data_ref: date, cdi_dia_pct: float) -> "CurvaDI":
        return cls(data_ref, cdi_dia_pct)

    @classmethod
    def de_csv(cls, caminho: Path, cdi_dia_pct: float) -> "CurvaDI":
        with open(caminho, newline="") as f:
            linhas = list(csv.DictReader(f))
        refs = {l["data_referencia"] for l in linhas}
        if len(refs) != 1:
            raise ValueError(f"CSV com mais de uma data de referência: {refs}")
        data_ref = date.fromisoformat(refs.pop())
        dus, taxas = [], []
        for l in linhas:
            venc = date.fromisoformat(l["vencimento"])
            du = int(l["dias_uteis"])
            if cal.du(data_ref, venc) != du:  # garante coerência com o calendário ANBIMA
                raise ValueError(f"DU do CSV ({du}) difere do calendário para {venc}")
            dus.append(du)
            taxas.append(float(l["taxa_252_pct"]))
        return cls(data_ref, cdi_dia_pct, tuple(dus), tuple(taxas))

    # ---------------------------------------------------------------- núcleo
    def _fator_du(self, du: int) -> float:
        if du < 0:
            raise ValueError("data anterior à data de referência da curva")
        cdi = (1 + self.cdi_dia_pct / 100)
        if not self.dus or du <= self.dus[0]:
            if self.dus and du == self.dus[0]:
                return self._fatores[0]
            return cdi ** (du / 252)
        if du > self.dus[-1]:
            raise ValueError(f"{du} DU além do último vértice ({self.dus[-1]} DU)")
        j = bisect.bisect_left(self.dus, du)
        if self.dus[j] == du:
            return self._fatores[j]
        d0, d1 = self.dus[j - 1], self.dus[j]
        f0, f1 = self._fatores[j - 1], self._fatores[j]
        return f0 * (f1 / f0) ** ((du - d0) / (d1 - d0))

    def taxa_du(self, du: int) -> float:
        """Taxa spot (% a.a. base 252) da data de referência até du."""
        if du <= 0:
            raise ValueError("du deve ser positivo")
        return (self._fator_du(du) ** (252 / du) - 1) * 100

    def fator_acumulado(self, d1: date, d2: date) -> float:
        """Fator de CDI esperado entre d1 e d2 (d1 <= d2, ambos >= data_ref)."""
        if d2 < d1:
            raise ValueError("d2 anterior a d1")
        return self._fator_du(cal.du(self.data_ref, d2)) / self._fator_du(cal.du(self.data_ref, d1))

    def cdi_medio(self, d1: date, d2: date) -> float:
        """CDI médio esperado (% a.a. base 252) entre d1 e d2."""
        n = cal.du(d1, d2)
        if n <= 0:
            raise ValueError("intervalo sem dias úteis")
        return (self.fator_acumulado(d1, d2) ** (252 / n) - 1) * 100
