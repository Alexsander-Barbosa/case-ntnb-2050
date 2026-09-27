"""PU calculado vs PU oficial.

1) Exemplo hipotético da metodologia STN: validação ponta a ponta (inclui VNA projetado).
2) Tesouro Direto: o CSV NÃO publica VNA. Para não ser circular, o VNA de cada data é
   inferido das OUTRAS NTN-Bs do mesmo dia (mediana de PU/cotação) e aplicado à 2050.
   Lado Venda (recompra) liquida em D+0; lado Compra em D+1 (evidência empírica, ver notas).
   Tolerância R$ 0,02/título: PU publicado em 2 casas + erro do VNA inferido (~R$ 0,005).
"""
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from quant import calendar as cal
from quant import ntnb

TOL_PU = 0.02
INICIO_REGIME = date(2023, 12, 26)  # antes disso o TD publica convenção diferente (ver notas)


def test_exemplo_stn_ntnb_completo():
    liq, venc = date(2008, 5, 21), date(2010, 8, 15)
    assert ntnb.cotacao_oficial("8.29", liq, venc) == Decimal("97.0813")
    vna = ntnb.vna_projetado("1726.926459", "0.46", liq)
    assert vna == Decimal("1728.461136")
    assert ntnb.pu_oficial("8.29", vna, liq, venc) == Decimal("1678.012540")
    assert ntnb.juros_semestrais("1726.926459") == Decimal("51.053144")


def test_fluxos_2050():
    fl = ntnb.fluxos(date(2026, 9, 25))
    assert fl[0].data == date(2027, 2, 15) and fl[-1].data == date(2050, 8, 15)
    assert len(fl) == 48
    assert fl[-1].valor == Decimal("102.956301")


def test_cupom_na_data_de_liquidacao_nao_entra():
    fl = ntnb.fluxos(date(2026, 8, 17))
    assert fl[0].data == date(2027, 2, 15)


def _vna_das_outras(g, dia, liq, lado):
    tx, pu = (f"Taxa {lado} Manha", f"PU {lado} Manha")
    outras = g[(g.venc != ntnb.VENC_2050) & (g.venc > liq)]  # exclui vencidos na liquidação
    v = [float(ntnb.vna_implicito(r[pu], r[tx], liq, r.venc)) for _, r in outras.iterrows()]
    assert len(v) >= 3
    return float(np.median(v)), max(v) - min(v)


def _compara(td, dia, lado, lag):
    g = td[td.db == dia]
    liq = cal.add_du(dia, lag)
    vna, amp = _vna_das_outras(g, dia, liq, lado)
    r = g[g.venc == ntnb.VENC_2050].iloc[0]
    pu_calc = float(ntnb.pu_oficial(r[f"Taxa {lado} Manha"], round(vna, 6), liq))
    return pu_calc, float(r[f"PU {lado} Manha"]), vna, amp


DATAS = [
    date(2024, 1, 2),    # início do regime atual
    date(2025, 3, 12),
    date(2026, 8, 14),   # véspera de pagamento de cupom (15/08, sábado)
    date(2026, 8, 17),   # primeiro DU ex-cupom
    date(2026, 9, 25),   # data de referência
]


@pytest.mark.parametrize("dia", DATAS)
def test_pu_venda_d0_vs_oficial(td, dia):
    pu_calc, pu_of, vna, amp = _compara(td, dia, "Venda", 0)
    print(f"\n{dia} Venda D+0: VNA={vna:.6f} (amp {amp:.4f}) calc={pu_calc:.6f} oficial={pu_of:.2f} dif={pu_calc-pu_of:+.6f}")
    assert abs(pu_calc - pu_of) < TOL_PU


@pytest.mark.parametrize("dia", DATAS)
def test_pu_compra_d1_vs_oficial(td, dia):
    pu_calc, pu_of, vna, amp = _compara(td, dia, "Compra", 1)
    print(f"\n{dia} Compra D+1: VNA={vna:.6f} (amp {amp:.4f}) calc={pu_calc:.6f} oficial={pu_of:.2f} dif={pu_calc-pu_of:+.6f}")
    assert abs(pu_calc - pu_of) < TOL_PU


def test_pu_venda_todo_regime_atual(td):
    """Backtest diário de toda a série desde 26/12/2023."""
    difs = []
    for dia, g in td[td.db >= INICIO_REGIME].groupby("db"):
        if (g.venc == ntnb.VENC_2050).sum() == 0:
            continue
        pu_calc, pu_of, _, _ = _compara(td, dia, "Venda", 0)
        difs.append(pu_calc - pu_of)
    d = np.abs(difs)
    print(f"\nBacktest {len(d)} dias: |dif| média={d.mean():.6f} máx={d.max():.6f} p99={np.quantile(d,0.99):.6f}")
    assert len(d) > 600
    assert d.max() < TOL_PU
