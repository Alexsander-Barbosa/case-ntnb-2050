"""TRS / asset swap sobre a NTN-B 2050 (recebe retorno do título, paga CDI).

Cliente RECEBE o retorno total da NTN-B 2050 (IPCA + taxa real de 7,38% na contratação,
com os fluxos do título) e PAGA CDI sobre o notional.

Nota: o swap DI x IPCA padrão da B3 e o DAP são BULLET (zero-cupom): duration ≈ prazo,
logo DV01 por notional muito maior que o deste TRS. A comparação entre estruturas
(NTN-B, TRS, DAP, opção) é feita por DV01, não por notional.

Estrutura:
- Ponta ativa (IPCA): Q "títulos sintéticos" com os MESMOS fluxos da NTN-B 2050
  (cupom 6% a.a. semestral sobre o VNA + principal), marcados pela taxa real de mercado.
  Q = notional / PU(taxa_fixa, VNA_0, t0)  => na contratação a ponta vale o notional.
- Ponta passiva (CDI): notional * fator de CDI acumulado desde t0 (curva DI x pré).
Economicamente = NTN-B financiada a CDI.

Valor(t) = Q * VNA_t * cot(y_t, t)/100 - notional * F_CDI(t0, t)

P&L no horizonte H com choque Δ na taxa real (y_H = y_0 + Δ):
  carry    = Q*VNA_H*cot(y_0, H)/100 - notional*F_CDI       (tempo passa, taxa parada)
  marcação = Q*VNA_H*[cot(y_0+Δ, H) - cot(y_0, H)]/100      (só Δ taxa real)
  total    = carry + marcação   (identidade exata)
Carry aberto em 3 parcelas que somam exatamente:
  real = Q*VNA_0*[cot(y_0,H) - cot(y_0,t0)]/100            (accrual da taxa real)
  ipca = Q*(VNA_H - VNA_0)*cot(y_0,H)/100                  (correção do VNA; inclui o termo cruzado)
  cdi  = -notional*(F_CDI - 1)
O IPCA entra SÓ via VNA_H — não há dupla contagem.
Sem cupom no horizonte, carry = notional*[(VNA_H/VNA_0)*(1+y_0)^(du/252) - F_CDI].

Valoração pela camada CONTÍNUA da NTN-B (sem truncamentos): P&L e DV01 suaves em Δ.
P&L > 0 = ganho do cliente. Δ em bps; queda de taxa = Δ < 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from . import calendar as cal
from . import ntnb
from .curva_di import CurvaDI

NOME_ESTRUTURA = "TRS / asset swap sobre a NTN-B 2050 (recebe retorno do título, paga CDI)"


# --------------------------------------------------------------------------- VNA
def vna_encadeado(vna_15_ancora, data_ancora: date, ipca_mensal_pct: dict, data: date) -> Decimal:
    """VNA em `data` encadeando VNA_15 mês a mês e projetando pro rata até `data`.

    VNA_15/(m+1) = VNA_15/m * (1 + IPCA_m)   (T6), IPCA_m = mês de referência m.
    Depois: ntnb.vna_projetado(VNA_15 anterior a `data`, IPCA do mês desse 15, data).
    """
    if data_ancora.day != 15:
        raise ValueError("âncora deve ser um dia 15")
    if data < data_ancora:
        raise ValueError("data anterior à âncora")
    vna = ntnb._t(ntnb._D(vna_15_ancora), 6)
    a, m = data_ancora.year, data_ancora.month
    while True:
        prox = date(a + (m == 12), m % 12 + 1, 15)
        if prox > data:
            break
        vna = ntnb._t(vna * (1 + _ipca(ipca_mensal_pct, a, m) / 100), 6)
        a, m = prox.year, prox.month
    return ntnb.vna_projetado(vna, _ipca(ipca_mensal_pct, a, m), data)


def _ipca(tab: dict, a: int, m: int) -> Decimal:
    try:
        return Decimal(str(tab[(a, m)]))
    except KeyError:
        raise ValueError(f"IPCA de {m:02d}/{a} não informado (fora do horizonte de premissas)")


# --------------------------------------------------------------------------- swap
@dataclass(frozen=True)
class DecomposicaoPnL:
    marcacao: float
    carry: float
    carry_real: float
    carry_ipca: float
    carry_cdi: float
    total: float
    fator_cdi: float
    vna_h: float


@dataclass(frozen=True)
class TRSNTNB:
    notional: float
    taxa_fixa_pct: float
    data_inicio: date
    vna_inicio: float
    vencimento: date = ntnb.VENC_2050

    @property
    def quantidade(self) -> float:
        pu0 = self.vna_inicio * ntnb.cotacao_continua(self.taxa_fixa_pct, self.data_inicio,
                                                       self.vencimento) / 100
        return self.notional / pu0

    def _cupom_no_intervalo(self, d1: date, d2: date) -> bool:
        return any(d1 < c <= d2 for c in ntnb.datas_cupom(self.vencimento))

    def ponta_ipca(self, data: date, taxa_real_pct: float, vna: float) -> float:
        return self.quantidade * vna * ntnb.cotacao_continua(taxa_real_pct, data, self.vencimento) / 100

    def ponta_cdi(self, data: date, curva: CurvaDI) -> float:
        return self.notional * curva.fator_acumulado(self.data_inicio, data)

    def valor(self, data: date, taxa_real_pct: float, vna: float, curva: CurvaDI) -> float:
        """MtM para o cliente (recebe retorno da NTN-B, paga CDI)."""
        if self._cupom_no_intervalo(self.data_inicio, data):
            raise NotImplementedError("cupom entre início e data: fluxo intermediário não modelado")
        return self.ponta_ipca(data, taxa_real_pct, vna) - self.ponta_cdi(data, curva)

    def dv01(self, data: date, taxa_real_pct: float, vna: float) -> float:
        """R$ por 1 bp de QUEDA da taxa real (> 0). A ponta CDI não depende da taxa real."""
        s = ntnb.sensibilidades(taxa_real_pct, data, vna, self.vencimento)
        return self.quantidade * s.dv01_pu

    def pnl_horizonte(self, horizonte: date, delta_bps: float, vna_horizonte: float,
                      curva: CurvaDI, taxa_real_inicial_pct: float | None = None) -> DecomposicaoPnL:
        """P&L de t0 até `horizonte` com choque paralelo `delta_bps` na taxa real."""
        if horizonte < self.data_inicio:
            raise ValueError("horizonte anterior ao início")
        if self._cupom_no_intervalo(self.data_inicio, horizonte):
            raise NotImplementedError("cupom no horizonte: fluxo intermediário não modelado")
        y0 = self.taxa_fixa_pct if taxa_real_inicial_pct is None else taxa_real_inicial_pct
        q, v0, vh = self.quantidade, self.vna_inicio, float(vna_horizonte)
        cot_0 = ntnb.cotacao_continua(y0, self.data_inicio, self.vencimento)
        cot_h = ntnb.cotacao_continua(y0, horizonte, self.vencimento)
        cot_h_choque = ntnb.cotacao_continua(y0 + delta_bps / 100, horizonte, self.vencimento)
        f = curva.fator_acumulado(self.data_inicio, horizonte)

        valor_0 = q * v0 * cot_0 / 100 - self.notional  # = 0 se y0 == taxa_fixa
        carry_real = q * v0 * (cot_h - cot_0) / 100
        carry_ipca = q * (vh - v0) * cot_h / 100
        carry_cdi = -self.notional * (f - 1)
        carry = carry_real + carry_ipca + carry_cdi
        marcacao = q * vh * (cot_h_choque - cot_h) / 100
        total = (q * vh * cot_h_choque / 100 - self.notional * f) - valor_0
        return DecomposicaoPnL(marcacao, carry, carry_real, carry_ipca, carry_cdi, total, f, vh)
