"""Dados dos gráficos do app — funções puras sobre `Cenarios` e `premissas`.

Nenhum cálculo financeiro novo aqui: só montagem de DataFrames/dicts a partir de funções já
validadas (ntnb, swap, option, scenarios). O app.py apenas desenha.
Convenção de exibição: "ganho por bp de queda" > 0; P&L > 0 = ganho do cliente.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import calendar as cal
from . import ntnb
from . import premissas as P
from .curva_di import CurvaDI
from .option import NOME_ESTRUTURA as NOME_OPCAO
from .scenarios import Cenarios, cenarios_padrao
from .swap import NOME_ESTRUTURA as NOME_TRS

NOME_NTNB = "NTN-B 2050 (compra direta)"
NOMES = {"NTN-B": NOME_NTNB, "TRS": NOME_TRS, "Opção": NOME_OPCAO}
CURVAS = {"B": "B — DI futuro (B3, 25/09/2026)", "A": "A — CDI flat (13,65%)"}
_SERIE_2050 = Path(__file__).resolve().parent.parent / "data" / "ntnb_2050_tesouro_direto.csv"


# --------------------------------------------------------------------------- formatação
def fmt_brl(x: float, casas: int = 0) -> str:
    """R$ com separador brasileiro: 1.234.567,89."""
    s = f"{abs(x):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if x < 0 else ''}R$ {s}"


def fmt_num(x: float, casas: int = 2) -> str:
    s = f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.replace("-", "−")


# --------------------------------------------------------------------------- construção
def construir_cenarios(curva: str = "B", sigma_bps: float | None = None, strike_pct: float | None = None,
                       margem_pct: float | None = None, notional: float | None = None) -> Cenarios:
    if curva == "B":
        c = CurvaDI.de_csv(P.CURVA_DI_CSV, P.CDI_DIA_PCT)
    elif curva == "A":
        c = CurvaDI.flat(P.DATA_REF, P.CDI_DIA_PCT)
    else:
        raise ValueError("curva deve ser 'A' ou 'B'")
    return cenarios_padrao(curva=c, sigma_bps=sigma_bps, margem_trs_pct=margem_pct,
                           strike_pct=strike_pct, notional=notional)


def resumo(cen: Cenarios) -> dict:
    """Números de topo (cabeçalho do app)."""
    return {
        "taxa_spot": cen.taxa_ref_pct,
        "taxa_forward": cen.opcao.taxa_forward(),
        "strike": cen.strike,
        "pu_spot": cen.opcao.pu_spot(cen.taxa_ref_pct),
        "vna_inicio": cen.vna_inicio,
        "vna_h": cen.vna_h,
        "quantidade": cen.Q,
        "fator_cdi": cen.F,
        "cdi_medio": cen.curva.cdi_medio(cen.data_inicio, cen.horizonte),
        "premio": cen.premio,
        "premio_capitalizado": cen.premio_capitalizado,
        "carry_trs": cen.pnl_trs(0.0),
        "dv01": cen.ganho_por_bp_queda_hoje["TRS"],
        "du_horizonte": cal.du(cen.data_inicio, cen.horizonte),
    }


# --------------------------------------------------------------------------- gráfico 1
def dados_payoff(cen: Cenarios, delta_cenario: float, limite_bps: int = 100, passo_bps: float = 1.0) -> dict:
    ds = np.arange(-limite_bps, limite_bps + passo_bps / 2, passo_bps)
    pu = cen.opcao._pu_H(cen.taxa_ref_pct + ds / 100)            # vetorizado; mesma função dos cenários
    linhas = pd.DataFrame({
        "delta_bps": ds,
        "taxa_H_pct": cen.taxa_ref_pct + ds / 100,
        "ntnb_trs": cen.Q * pu - cen.notional * cen.F,             # = Cenarios.pnl_ntnb_excesso = pnl_trs
        "ntnb_absoluto": cen.Q * pu - cen.notional,
        "opcao": cen.Q * np.maximum(pu - cen.k_pu, 0.0) - cen.premio_capitalizado,
    })
    be_trs, be_opc = cen.break_even("TRS"), cen.break_even("Opção")
    return {
        "linhas": linhas,
        "verticais": {
            "spot": cen.taxa_ref_pct,
            "forward": cen.opcao.taxa_forward(),
            "strike": cen.strike,
            "cenario": cen.taxa_ref_pct + delta_cenario / 100,
        },
        "break_evens": {
            "TRS": {"delta_bps": be_trs, "taxa": cen.taxa_ref_pct + be_trs / 100},
            "Opção": {"delta_bps": be_opc, "taxa": cen.taxa_ref_pct + be_opc / 100},
        },
        "cenario": {"delta_bps": delta_cenario, "ntnb_trs": cen.pnl_trs(delta_cenario),
                    "opcao": cen.pnl_opcao(delta_cenario),
                    "ntnb_absoluto": cen.pnl_ntnb_absoluto(delta_cenario)},
    }


# --------------------------------------------------------------------------- gráfico 2
def dados_preco_taxa(cen: Cenarios, y_min: float = 5.0, y_max: float = 10.0, n: int = 201) -> dict:
    """PU hoje × taxa real, com a tangente da duration em y0 (a distância é a convexidade)."""
    y0 = cen.taxa_ref_pct
    s = ntnb.sensibilidades(y0, cen.data_inicio, cen.vna_inicio)
    ys = np.linspace(y_min, y_max, n)
    pu = np.array([cen.opcao.pu_spot(y) for y in ys])
    tangente = s.pu + (-s.dv01_pu) * (ys - y0) * 100               # DV01 em R$/título por bp
    return {
        "curva": pd.DataFrame({"taxa_pct": ys, "pu": pu, "tangente": tangente, "convexidade": pu - tangente}),
        "ponto": {"taxa": y0, "pu": s.pu},
        "sens": {"duration_macaulay": s.duration_macaulay, "duration_modificada": s.duration_modificada,
                 "convexidade": s.convexidade, "dv01_titulo": s.dv01_pu},
    }


# --------------------------------------------------------------------------- gráfico 3
def dados_heatmap(cen: Cenarios, limite_bps: int = 100, passo_bps: int = 25) -> pd.DataFrame:
    """Linhas = estruturas; colunas = Δ (bp); valores = P&L em excesso ao CDI (R$)."""
    g = cen.grade(limite_bps, passo_bps)
    m = pd.DataFrame({"NTN-B": g.ntnb_excesso_cdi.values, "TRS": g.trs.values, "Opção": g.opcao.values},
                     index=g.delta_bps.astype(int).values).T
    m.columns.name = "delta_bps"
    return m


def tabela_metricas(cen: Cenarios) -> pd.DataFrame:
    m = cen.metricas()
    return pd.DataFrame({
        "Estrutura": [NOMES[e] for e in m.index],
        "Capital": [fmt_brl(v) + (" (premissa ilustrativa)" if e == "TRS" else "")
                    for e, v in m.capital.items()],
        "Perda máxima": [fmt_brl(v) for v in m.perda_maxima],
        "Perda": m.perda_maxima_nota.values,
        "Break-even (bp)": [fmt_num(v, 2) for v in m.break_even_bps],
        "Ganho por bp de queda (hoje)": [fmt_brl(v) for v in m.ganho_por_bp_queda_hoje],
    })


# --------------------------------------------------------------------------- gráfico 4
def dados_waterfall(cen: Cenarios, delta_bps: float) -> dict:
    d = cen.trs.pnl_horizonte(cen.horizonte, delta_bps, cen.vna_h, cen.curva)
    payoff = cen.pnl_opcao(delta_bps) + cen.premio_capitalizado
    trs = pd.DataFrame({
        "item": ["Carry real (taxa 7,38%)", "Carry IPCA (VNA)", "Custo CDI", "Marcação (Δ taxa)", "Total TRS"],
        "valor": [d.carry_real, d.carry_ipca, d.carry_cdi, d.marcacao, d.total],
        "medida": ["relative"] * 4 + ["total"],
    })
    opc = pd.DataFrame({
        "item": ["Payoff no vencimento", "Prêmio capitalizado (CDI)", "Total opção"],
        "valor": [payoff, -cen.premio_capitalizado, payoff - cen.premio_capitalizado],
        "medida": ["relative", "relative", "total"],
    })
    return {"TRS": trs, "Opção": opc}


# --------------------------------------------------------------------------- gráfico 5
def dados_historico(cen: Cenarios, sigma_bps: float | None = None) -> dict:
    s = cen.sigma_bps if sigma_bps is None else sigma_bps
    h = pd.read_csv(_SERIE_2050, sep=";", decimal=",")
    serie = pd.DataFrame({"data": pd.to_datetime(h["Data Base"], dayfirst=True),
                          "taxa_venda": h["Taxa Venda Manha"]}).sort_values("data").reset_index(drop=True)
    datas, dus = [], []
    d = cen.data_inicio
    while d <= cen.horizonte:
        datas.append(pd.Timestamp(d))
        dus.append(cal.du(cen.data_inicio, d))
        d = cal.add_du(d, 1)
    dus = np.array(dus)
    larg = s / 100 * np.sqrt(dus / 252)                             # 1σ em p.p.
    leque = pd.DataFrame({"data": datas, "du": dus, "centro": cen.taxa_ref_pct,
                          "sup": cen.taxa_ref_pct + larg, "inf": cen.taxa_ref_pct - larg})
    return {"serie": serie, "leque": leque, "sigma_bps": s, "quebra": pd.Timestamp(date(2023, 12, 26)),
            "um_sigma_horizonte_bps": s * np.sqrt(dus[-1] / 252)}


# --------------------------------------------------------------------------- premissas
def tabela_premissas() -> pd.DataFrame:
    """Todas as constantes de premissas.py com valor, tipo e fonte (painel do app)."""
    f = P.IPCA_FOCUS_PCT
    lin = [
        ("DATA_REF", "Data de referência", "25/09/2026 (sexta), liquidação D+0", "dado", "Último DU com preço no Tesouro Direto"),
        ("HORIZONTE_PADRAO", "Horizonte = vencimento da opção", "28/12/2026 (62 DU)", "premissa", "Escolha do case: 3 meses; 25/12 é feriado (calendário ANBIMA)"),
        ("NOTIONAL_PADRAO", "Notional padrão", fmt_brl(P.NOTIONAL_PADRAO), "premissa", "Escolha do case (ajustável na barra lateral)"),
        ("TAXA_REAL_REF_PCT", "Taxa real NTN-B 2050", f"{fmt_num(P.TAXA_REAL_REF_PCT)}% a.a.", "dado", "Tesouro Direto, Taxa Venda Manhã 25/09/2026 (proxy de mercado; indicativa ANBIMA a verificar)"),
        ("VNA_REF", "VNA em 25/09/2026", fmt_num(P.VNA_REF, 6), "dado derivado", "Implícito nas NTN-Bs do TD (mediana PU/cotação); conferido pelo número-índice (dif. R$ 0,004)"),
        ("IDX_IPCA_AGO_2026", "Número-índice IPCA ago/2026", fmt_num(float(P.IDX_IPCA_AGO_2026)), "dado", "IBGE/SIDRA 1737 (a conferir); base jun/2000 = 1.614,62"),
        ("CDI_DIA_PCT", "CDI do dia", f"{fmt_num(P.CDI_DIA_PCT)}% a.a.", "dado", "BCB/SGS 4389, 24/09/2026 (último disponível)"),
        ("CURVA_DI_CSV", "Curva DI x pré", "74 vértices, 1 a 182 DU", "dado", "B3 — Taxas referenciais DI x pré, 25/09/2026; flat forward 252"),
        ("IPCA_FOCUS_PCT", "IPCA mensal (Focus)",
         f"set {fmt_num(float(f[(2026, 9)]))} | out {fmt_num(float(f[(2026, 10)]))} | nov {fmt_num(float(f[(2026, 11)]))} | dez {fmt_num(float(f[(2026, 12)]))} (%)",
         "dado", "Focus/BCB 18/09/2026 (medianas); dez derivado do anual 4,92%"),
        ("IPCA_SET_2026_EMBUTIDO_PCT", "IPCA set/2026 embutido no preço", f"{fmt_num(float(P.IPCA_SET_2026_EMBUTIDO_PCT))}%", "dado derivado", "Implícito no VNA do TD (projeção ANBIMA, a confirmar)"),
        ("IPCA_HORIZONTE_PCT", "IPCA usado até o horizonte", "set 0,56 (embutido) + out–dez Focus", "premissa", "Evita carry fantasma de ≈ −R$ 4,1 mil (decisão 26/09)"),
        ("VOL_TAXA_REAL_BASE_BPS", "Vol da taxa real — base", f"{fmt_num(P.VOL_TAXA_REAL_BASE_BPS, 0)} bps/ano", "premissa", "Variações de 21 DU, regime desde 26/12/2023 (erro ≈ ±12%)"),
        ("VOL_TAXA_REAL_ESTRESSE_BPS", "Vol da taxa real — estresse", f"{fmt_num(P.VOL_TAXA_REAL_ESTRESSE_BPS, 0)} bps/ano", "premissa", "Variações de 21 DU, série completa 2012–2026"),
        ("MARGEM_TRS_PCT_NOTIONAL", "Margem do TRS", f"{fmt_num(P.MARGEM_TRS_PCT_NOTIONAL * 100, 0)}% do notional", "PREMISSA ILUSTRATIVA", "Não é dado de mercado; cobre até ≈ +95 bp; a verificar (B3/CORE)"),
    ]
    return pd.DataFrame(lin, columns=["constante", "item", "valor", "tipo", "fonte / motivo"])
