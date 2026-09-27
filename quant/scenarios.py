"""Cenários no horizonte (= vencimento da opção, 28/12/2026) para as três estruturas.

Choque Δ (bps) na taxa real spot NO HORIZONTE: y_H = y_0 + Δ.  VNA_H determinístico
(IPCA_HORIZONTE_PCT).  P&L em R$ no horizonte, EM EXCESSO AO CDI (curva B), cliente comprado:

  NTN-B (excesso ao CDI):  Q*PU_H(y_H) - N*F_CDI        (absoluto: Q*PU_H(y_H) - N)
  TRS:                     TRSNTNB.pnl_horizonte(...).total   (idêntico à NTN-B em excesso)
  Opção (call no PU):      Q*max(PU_H(y_H) - K_PU, 0) - prêmio*F_CDI   (prêmio capitalizado)

Q = N/PU_0 é o mesmo nas três (mesma camada contínua do pricer).
Métricas: capital, perda máxima (limitada só na opção), break-even em bp (brentq) e
"ganho por bp de queda" HOJE (> 0): DV01 da NTN-B/TRS e -delta da opção.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cached_property

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from . import ntnb
from . import premissas as P
from .curva_di import CurvaDI
from .option import CallPUNTNB
from .swap import TRSNTNB, vna_encadeado

ESTRUTURAS = ("NTN-B", "TRS", "Opção")


@dataclass(frozen=True)
class Cenarios:
    data_inicio: date
    horizonte: date
    notional: float
    taxa_ref_pct: float
    vna_inicio: float
    vna_h: float
    curva: CurvaDI
    sigma_bps: float
    margem_trs_pct: float
    strike_pct: float | None = None  # None = ATM forward

    # ------------------------------------------------------------------ objetos
    @cached_property
    def trs(self) -> TRSNTNB:
        return TRSNTNB(self.notional, self.taxa_ref_pct, self.data_inicio, self.vna_inicio)

    @cached_property
    def opcao(self) -> CallPUNTNB:
        return CallPUNTNB(self.notional, self.data_inicio, self.horizonte, self.vna_inicio,
                          self.vna_h, self.curva, self.taxa_ref_pct)

    @cached_property
    def Q(self) -> float:
        return self.opcao.quantidade

    @cached_property
    def F(self) -> float:
        return self.curva.fator_acumulado(self.data_inicio, self.horizonte)

    @cached_property
    def strike(self) -> float:
        return self.opcao.strike_atm if self.strike_pct is None else self.strike_pct

    @cached_property
    def k_pu(self) -> float:
        return self.opcao.k_pu(self.strike)

    @cached_property
    def premio(self) -> float:
        return self.opcao.premio(self.sigma_bps, self.strike)

    @property
    def premio_capitalizado(self) -> float:
        return self.premio * self.F

    def pu_h(self, delta_bps: float) -> float:
        return float(self.opcao._pu_H(self.taxa_ref_pct + delta_bps / 100))

    # ------------------------------------------------------------------ P&L por Δ
    def pnl_ntnb_excesso(self, d: float) -> float:
        return self.Q * self.pu_h(d) - self.notional * self.F

    def pnl_ntnb_absoluto(self, d: float) -> float:
        return self.Q * self.pu_h(d) - self.notional

    def pnl_trs(self, d: float) -> float:
        return self.trs.pnl_horizonte(self.horizonte, d, self.vna_h, self.curva).total

    def pnl_opcao(self, d: float) -> float:
        return self.Q * max(self.pu_h(d) - self.k_pu, 0.0) - self.premio_capitalizado

    def _pnl(self, estrutura: str):
        return {"NTN-B": self.pnl_ntnb_excesso, "TRS": self.pnl_trs, "Opção": self.pnl_opcao}[estrutura]

    # ------------------------------------------------------------------ grade
    def grade(self, limite_bps: int = 100, passo_bps: int = 5) -> pd.DataFrame:
        ds = np.arange(-limite_bps, limite_bps + passo_bps / 2, passo_bps)
        return pd.DataFrame({
            "delta_bps": ds,
            "taxa_H_pct": self.taxa_ref_pct + ds / 100,
            "ntnb_excesso_cdi": [self.pnl_ntnb_excesso(d) for d in ds],
            "ntnb_absoluto": [self.pnl_ntnb_absoluto(d) for d in ds],
            "trs": [self.pnl_trs(d) for d in ds],
            "opcao": [self.pnl_opcao(d) for d in ds],
        })

    # ------------------------------------------------------------------ métricas
    @property
    def delta_exercicio_bps(self) -> float:
        """Δ a partir do qual a opção expira fora do dinheiro (y_H >= K)."""
        return (self.strike - self.taxa_ref_pct) * 100

    def break_even(self, estrutura: str) -> float:
        """Δ (bps) com P&L = 0 no horizonte (em excesso ao CDI)."""
        f = self._pnl(estrutura)
        hi = self.delta_exercicio_bps if estrutura == "Opção" else 500.0
        return brentq(f, -500.0, hi, xtol=1e-10)

    def break_even_ntnb_absoluto(self) -> float:
        return brentq(self.pnl_ntnb_absoluto, -500.0, 500.0, xtol=1e-10)

    @cached_property
    def ganho_por_bp_queda_hoje(self) -> dict:
        dv01 = self.trs.dv01(self.data_inicio, self.taxa_ref_pct, self.vna_inicio)
        delta_opc = self.opcao.greeks(self.sigma_bps, self.strike)["delta"]
        return {"NTN-B": dv01, "TRS": dv01, "Opção": -delta_opc}

    def metricas(self, limite_bps: int = 100) -> pd.DataFrame:
        borda = float(limite_bps)
        linhas = []
        for e in ESTRUTURAS:
            capital = {"NTN-B": self.notional, "TRS": self.margem_trs_pct * self.notional,
                       "Opção": self.premio}[e]
            limitada = e == "Opção"
            perda = -self.premio_capitalizado if limitada else self._pnl(e)(borda)
            linhas.append({
                "estrutura": e,
                "capital": capital,
                "perda_maxima": perda,
                "perda_limitada": limitada,
                "perda_maxima_nota": "limitada ao prêmio capitalizado" if limitada
                                     else f"não limitada (valor na borda +{limite_bps} bp)",
                "break_even_bps": self.break_even(e),
                "ganho_por_bp_queda_hoje": self.ganho_por_bp_queda_hoje[e],
            })
        return pd.DataFrame(linhas).set_index("estrutura")


def cenarios_padrao(curva: CurvaDI | None = None, sigma_bps: float | None = None,
                    margem_trs_pct: float | None = None, strike_pct: float | None = None,
                    notional: float | None = None) -> Cenarios:
    curva = curva or CurvaDI.de_csv(P.CURVA_DI_CSV, P.CDI_DIA_PCT)
    v15 = ntnb.vna_numero_indice(P.IDX_IPCA_AGO_2026)
    vna_h = float(vna_encadeado(v15, date(2026, 9, 15), P.IPCA_HORIZONTE_PCT, P.HORIZONTE_PADRAO))
    return Cenarios(
        data_inicio=P.DATA_REF, horizonte=P.HORIZONTE_PADRAO,
        notional=P.NOTIONAL_PADRAO if notional is None else notional,
        taxa_ref_pct=P.TAXA_REAL_REF_PCT, vna_inicio=P.VNA_REF, vna_h=vna_h, curva=curva,
        sigma_bps=P.VOL_TAXA_REAL_BASE_BPS if sigma_bps is None else sigma_bps,
        margem_trs_pct=P.MARGEM_TRS_PCT_NOTIONAL if margem_trs_pct is None else margem_trs_pct,
        strike_pct=strike_pct,
    )
