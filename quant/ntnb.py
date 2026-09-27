"""Pricer NTN-B (Tesouro IPCA+ com Juros Semestrais) — metodologia oficial STN.

Duas camadas, de propósito:

1. OFICIAL (Decimal + truncamentos/arredondamentos da Tabela 3 da STN):
   usada para marcação e para bater o PU oficial.
     - taxa (% a.a.)                  : T6
     - expoente du/252                : T14
     - fluxo (base 100), 100*(1,06^0,5-1): A6  -> 2,956301
     - fluxo descontado               : A10
     - cotação (%)                    : T4
     - fator pro rata (VNA projetado) : T14
     - projeção IPCA (%)              : A2
     - VNA                            : T6
     - PU = VNA * cotação/100         : T6

2. CONTÍNUA (float, sem truncamentos): usada para duration, DV01, convexidade
   e bumps. Truncar a cotação em 4 casas geraria ruído de ~1e-4 p.p. que
   contaminaria um bump de 1 bp.

Unidades: taxa REAL em % a.a. base 252 (ex.: 7.38). PU e VNA em R$ por título.
DV01 > 0 = ganho (R$) do comprador para uma QUEDA de 1 bp na taxa real.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, getcontext

from . import calendar as cal

getcontext().prec = 40

VENC_2050 = date(2050, 8, 15)
_UM = Decimal(1)
_CUPOM_SEMESTRAL_A6 = Decimal("2.956301")  # 100*(1,06^0,5 - 1) arredondado 6 casas
_FATOR_JUROS_A8 = Decimal("0.02956301")     # para PU de juros (cupom em R$)


def _t(x: Decimal, n: int) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-n), rounding=ROUND_DOWN)


def _a(x: Decimal, n: int) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)


def _D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


# --------------------------------------------------------------------------- fluxos
def datas_cupom(vencimento: date = VENC_2050) -> list[date]:
    """Todas as datas de pagamento (15/fev e 15/ago, ou mês do vencimento ±6) até o vencimento."""
    m1 = vencimento.month
    m2 = (m1 + 6 - 1) % 12 + 1
    datas = [date(a, m, 15) for a in range(2000, vencimento.year + 1) for m in (m1, m2)]
    return sorted(d for d in datas if d <= vencimento)


@dataclass(frozen=True)
class Fluxo:
    data: date
    du: int
    valor: Decimal  # base 100 (cupom 2,956301; no vencimento 102,956301)


def fluxos(liquidacao: date, vencimento: date = VENC_2050) -> list[Fluxo]:
    """Fluxos remanescentes (pagamento estritamente após a liquidação)."""
    out = []
    for d in datas_cupom(vencimento):
        if d <= liquidacao:
            continue
        v = _CUPOM_SEMESTRAL_A6 + (Decimal(100) if d == vencimento else 0)
        out.append(Fluxo(d, cal.du(liquidacao, d), v))
    if not out:
        raise ValueError("título vencido na data de liquidação")
    return out


# --------------------------------------------------------------------------- oficial
def cotacao_oficial(taxa_pct, liquidacao: date, vencimento: date = VENC_2050) -> Decimal:
    """Cotação (% do VNA), truncada em 4 casas."""
    i = _t(_D(taxa_pct), 6) / 100
    s = Decimal(0)
    for f in fluxos(liquidacao, vencimento):
        expo = _t(Decimal(f.du) / Decimal(252), 14)
        s += _a(f.valor / ((_UM + i) ** expo), 10)
    return _t(s, 4)


def pu_oficial(taxa_pct, vna, liquidacao: date, vencimento: date = VENC_2050) -> Decimal:
    """PU = VNA * cotação/100, truncado em 6 casas."""
    return _t(_t(_D(vna), 6) * cotacao_oficial(taxa_pct, liquidacao, vencimento) / 100, 6)


def vna_projetado(vna_ultimo_15, ipca_proj_pct, liquidacao: date) -> Decimal:
    """VNA projetado para a liquidação a partir do VNA do último dia 15 (<= liquidação).

    VNA_liq = VNA_15 * (1 + IPCA_proj)^pr, pr = dc(15 anterior, liq)/dc(15 anterior, 15 seguinte).
    Se a liquidação é o próprio dia 15, pr = 0 e VNA_liq = VNA_15.
    """
    ant = date(liquidacao.year, liquidacao.month, 15)
    if liquidacao < ant:
        ant = date(ant.year - (ant.month == 1), (ant.month - 2) % 12 + 1, 15)
    seg = date(ant.year + (ant.month == 12), ant.month % 12 + 1, 15)
    pr = _t(Decimal(cal.dc(ant, liquidacao)) / Decimal(cal.dc(ant, seg)), 14)
    ipca = _a(_D(ipca_proj_pct), 2) / 100
    return _t(_t(_D(vna_ultimo_15), 6) * (_UM + ipca) ** pr, 6)


def juros_semestrais(vna_data_pagto) -> Decimal:
    """Cupom em R$ por título na data de pagamento: VNA * 0,02956301 (T6)."""
    return _t(_t(_D(vna_data_pagto), 6) * _FATOR_JUROS_A8, 6)


IDX_IPCA_JUN_2000 = Decimal("1614.62")  # número-índice IPCA jun/2000 (base dez/93=100); data-base NTN-B 15/07/2000


def vna_numero_indice(idx_mes_anterior, idx_base=IDX_IPCA_JUN_2000) -> Decimal:
    """VNA no dia 15 do mês M = 1000 * I(M-1)/I(jun/2000). Fator acumulado T16, VNA T6."""
    fator = _t(_D(idx_mes_anterior) / _D(idx_base), 16)
    return _t(Decimal(1000) * fator, 6)


def vna_implicito(pu, taxa_pct, liquidacao: date, vencimento: date = VENC_2050) -> Decimal:
    """VNA implícito = PU / (cotação/100). Usado quando a fonte não publica o VNA.

    Atenção: com PU em 2 casas (Tesouro Direto), o erro do VNA implícito é ~±0,006.
    """
    return _D(pu) / (cotacao_oficial(taxa_pct, liquidacao, vencimento) / 100)


# --------------------------------------------------------------------------- contínua
def _tempos_fluxos(liquidacao: date, vencimento: date):
    fl = fluxos(liquidacao, vencimento)
    return [f.du / 252.0 for f in fl], [float(f.valor) for f in fl]


def cotacao_continua(taxa_pct: float, liquidacao: date, vencimento: date = VENC_2050) -> float:
    y = taxa_pct / 100.0
    t, cf = _tempos_fluxos(liquidacao, vencimento)
    return sum(c * (1 + y) ** -ti for ti, c in zip(t, cf))


@dataclass(frozen=True)
class Sensibilidades:
    taxa_pct: float
    cotacao: float           # % do VNA (sem truncamento)
    duration_macaulay: float  # anos (du/252)
    duration_modificada: float
    convexidade: float       # anos^2
    dv01_cotacao: float      # p.p. de cotação por 1 bp de queda
    pu: float | None         # R$ por título (se VNA informado)
    dv01_pu: float | None    # R$ por título por 1 bp de queda


def sensibilidades(taxa_pct: float, liquidacao: date, vna: float | None = None,
                   vencimento: date = VENC_2050) -> Sensibilidades:
    """Derivadas analíticas em relação à taxa real (composição anual, base 252).

    P(y) = Σ CF_i (1+y)^-t_i
    dP/dy   = -Σ t_i CF_i (1+y)^-(t_i+1)          -> Dmod = -(1/P) dP/dy
    d²P/dy² =  Σ t_i (t_i+1) CF_i (1+y)^-(t_i+2)  -> Conv = (1/P) d²P/dy²
    """
    y = taxa_pct / 100.0
    t, cf = _tempos_fluxos(liquidacao, vencimento)
    pv = [c * (1 + y) ** -ti for ti, c in zip(t, cf)]
    p = sum(pv)
    macaulay = sum(ti * v for ti, v in zip(t, pv)) / p
    dmod = macaulay / (1 + y)
    conv = sum(ti * (ti + 1) * v for ti, v in zip(t, pv)) / (p * (1 + y) ** 2)
    dv01_cot = p * dmod * 1e-4
    pu = dv01_pu = None
    if vna is not None:
        pu = vna * p / 100.0
        dv01_pu = vna * dv01_cot / 100.0
    return Sensibilidades(taxa_pct, p, macaulay, dmod, conv, dv01_cot, pu, dv01_pu)


def dv01_notional(dv01_por_titulo: float, pu: float, notional: float) -> float:
    """DV01 (R$/bp) de uma posição de valor financeiro `notional` a preço `pu`.

    Nº de títulos = notional / PU (fracionário; não arredonda para lote).
    """
    if pu <= 0:
        raise ValueError("PU deve ser positivo")
    return notional / pu * dv01_por_titulo


def taxa_de_cotacao(cotacao_alvo: float, liquidacao: date, vencimento: date = VENC_2050) -> float:
    """Inversa: taxa real (% a.a.) que reproduz uma cotação. Usa a versão contínua."""
    from scipy.optimize import brentq
    return brentq(lambda r: cotacao_continua(r, liquidacao, vencimento) - cotacao_alvo, -5.0, 40.0,
                  xtol=1e-12)
