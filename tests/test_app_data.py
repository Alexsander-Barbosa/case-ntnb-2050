"""Camada de dados do app: formas, sinais e valores de referência já validados."""
import re

import numpy as np
import pandas as pd
import pytest

from quant import app_data as D
from quant import premissas as P
from quant.option import NOME_ESTRUTURA as NOME_OPCAO
from quant.swap import NOME_ESTRUTURA as NOME_TRS

DELTA = -50


@pytest.fixture(scope="module")
def cen():
    return D.construir_cenarios("B")


def test_fmt_brl():
    assert D.fmt_brl(1234567.891, 2) == "R$ 1.234.567,89"
    assert D.fmt_brl(-10054.38) == "−R$ 10.054"
    assert D.fmt_num(-0.8882, 2) == "−0,89"


def test_construir_cenarios_curvas():
    a = D.construir_cenarios("A")
    assert a.curva.dus == () and a.pnl_trs(0) == pytest.approx(-12_289.17, abs=1.0)
    with pytest.raises(ValueError):
        D.construir_cenarios("C")


def test_resumo_referencias(cen):
    r = D.resumo(cen)
    assert r["carry_trs"] == pytest.approx(-10_054.38, abs=0.01)
    assert r["premio"] == pytest.approx(152_105.63, abs=0.01)
    assert r["taxa_forward"] == pytest.approx(7.3711, abs=1e-4)
    assert r["dv01"] == pytest.approx(11_203.04, abs=0.01)
    assert r["du_horizonte"] == 62 and r["cdi_medio"] == pytest.approx(13.55, abs=1e-6)


def test_payoff(cen):
    d = D.dados_payoff(cen, DELTA)
    L = d["linhas"]
    assert len(L) == 201 and L.delta_bps.iloc[0] == -100 and L.delta_bps.iloc[-1] == 100
    # linhas vetorizadas = funções validadas dos cenários
    for dd in (-100, -50, -25, 0, 25, 100):
        row = L[L.delta_bps == dd].iloc[0]
        assert row.ntnb_trs == pytest.approx(cen.pnl_trs(dd), abs=0.01)
        assert row.opcao == pytest.approx(cen.pnl_opcao(dd), abs=0.01)
        assert row.ntnb_absoluto == pytest.approx(cen.pnl_ntnb_absoluto(dd), abs=0.01)
    assert (np.diff(L.ntnb_trs) < 0).all() and (np.diff(L.opcao) <= 1e-9).all()
    assert d["break_evens"]["TRS"]["delta_bps"] == pytest.approx(-0.89, abs=0.01)
    assert d["break_evens"]["Opção"]["delta_bps"] == pytest.approx(-14.58, abs=0.01)
    v = d["verticais"]
    assert v["spot"] == 7.38 and v["cenario"] == pytest.approx(6.88) and v["strike"] == pytest.approx(v["forward"])
    assert d["cenario"]["ntnb_trs"] == pytest.approx(581_022.01, abs=1.0)
    assert d["cenario"]["opcao"] == pytest.approx(424_085.83, abs=1.0)


def test_preco_taxa(cen):
    d = D.dados_preco_taxa(cen)
    c = d["curva"]
    assert d["ponto"]["pu"] == pytest.approx(4076.567, abs=0.01)
    assert (c.convexidade >= -1e-9).all()                 # PU sempre acima da tangente
    i0 = (c.taxa_pct - 7.38).abs().idxmin()
    assert c.convexidade.min() == pytest.approx(0, abs=0.01) and abs(c.taxa_pct[i0] - 7.38) < 0.03
    assert (np.diff(c.pu) < 0).all()                     # PU cai com a taxa
    assert d["sens"]["dv01_titulo"] == pytest.approx(4.567, abs=1e-3)
    assert d["sens"]["duration_modificada"] == pytest.approx(11.20, abs=0.01)


def test_heatmap(cen):
    m = D.dados_heatmap(cen)
    assert list(m.index) == ["NTN-B", "TRS", "Opção"]
    assert list(m.columns) == [-100, -75, -50, -25, 0, 25, 50, 75, 100]
    assert m.loc["TRS", 0] == pytest.approx(-10_054.38, abs=0.01)
    assert m.loc["Opção", 100] == pytest.approx(-cen.premio_capitalizado, abs=1e-6)
    assert np.allclose(m.loc["NTN-B"], m.loc["TRS"], atol=0.01)
    assert m.loc["NTN-B", -100] == pytest.approx(1_226_804.00, abs=1.0)


def test_tabela_metricas(cen):
    t = D.tabela_metricas(cen)
    assert list(t.Estrutura) == [D.NOME_NTNB, NOME_TRS, NOME_OPCAO]
    assert list(t["Break-even (bp)"]) == ["−0,89", "−0,89", "−14,58"]
    assert "premissa ilustrativa" in t.Capital[1] and "limitada" in t.Perda[2] and "não limitada" in t.Perda[0]
    assert all(not s.startswith("−") for s in t["Ganho por bp de queda (hoje)"])  # > 0 nas três


@pytest.mark.parametrize("delta", [-100, -50, 0, 50])
def test_waterfall_soma(cen, delta):
    w = D.dados_waterfall(cen, delta)
    trs, opc = w["TRS"], w["Opção"]
    assert trs.valor.iloc[:-1].sum() == pytest.approx(trs.valor.iloc[-1], abs=1e-6)
    assert trs.valor.iloc[-1] == pytest.approx(cen.pnl_trs(delta), abs=1e-6)
    assert opc.valor.iloc[:-1].sum() == pytest.approx(opc.valor.iloc[-1], abs=1e-6)
    assert opc.valor.iloc[-1] == pytest.approx(cen.pnl_opcao(delta), abs=1e-6)
    assert list(trs.medida) == ["relative"] * 4 + ["total"]
    if delta == 0:
        assert trs.valor.iloc[3] == 0.0 and trs.valor.iloc[-1] == pytest.approx(-10_054.38, abs=0.01)


def test_historico(cen):
    d = D.dados_historico(cen)
    s, L = d["serie"], d["leque"]
    assert len(s) == 3570 and s.data.is_monotonic_increasing
    assert s.taxa_venda.iloc[-1] == 7.38 and s.data.iloc[-1] == pd.Timestamp("2026-09-25")
    assert L.du.iloc[0] == 0 and L.du.iloc[-1] == 62
    assert (L.sup.iloc[0], L.inf.iloc[0]) == (7.38, 7.38)
    assert d["um_sigma_horizonte_bps"] == pytest.approx(70 * np.sqrt(62 / 252), abs=1e-9)
    assert (L.sup.iloc[-1] - 7.38) * 100 == pytest.approx(d["um_sigma_horizonte_bps"])
    assert D.dados_historico(cen, 100)["um_sigma_horizonte_bps"] > d["um_sigma_horizonte_bps"]


def test_tabela_premissas_cobre_todas_as_constantes():
    t = D.tabela_premissas()
    constantes = {k for k in vars(P) if re.fullmatch(r"[A-Z][A-Z0-9_]+", k)}
    faltando = constantes - set(t.constante)
    assert not faltando, f"constantes sem fonte no painel: {faltando}"
    assert t["fonte / motivo"].str.len().min() > 10
    assert (t.tipo == "PREMISSA ILUSTRATIVA").sum() == 1
    assert t.set_index("constante").loc["MARGEM_TRS_PCT_NOTIONAL", "tipo"] == "PREMISSA ILUSTRATIVA"


def test_parametros_propagam():
    base, est = D.resumo(D.construir_cenarios("B")), D.resumo(D.construir_cenarios("B", sigma_bps=100))
    assert est["premio"] == pytest.approx(217_309.93, abs=0.01) and est["carry_trs"] == base["carry_trs"]
    dobro = D.resumo(D.construir_cenarios("B", notional=20_000_000))
    assert dobro["premio"] == pytest.approx(2 * base["premio"], rel=1e-9)
    assert dobro["dv01"] == pytest.approx(2 * base["dv01"], rel=1e-9)
