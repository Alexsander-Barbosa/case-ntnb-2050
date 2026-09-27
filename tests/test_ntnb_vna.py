"""VNA independente (número-índice IPCA), ramos do VNA projetado e DV01 por notional.

Fontes:
- I(jun/2000) = 1.614,62: número-índice IPCA (base dez/1993 = 100), IBGE/SIDRA tabela 1737;
  conferido na tabela IPCA/IBGE da Secovi (jun/2000: 1.614,620; var. 0,23%).
- I(ago/2026) = 7.633,23: fornecido pelo usuário (a conferir na SIDRA 1737). Consistência:
  jun/2026 = 7.652,37 (Secovi) x jul/2026 +0,07% (IBGE) => ago/2026 implica -0,32%,
  coerente com o IPCA-15 de ago/2026 (-0,40%).
- IPCA set/2026 projetado = 0,56%: implícito nos preços do TD; a confirmar com projeção ANBIMA.
"""
from datetime import date
from decimal import Decimal

import pytest

from quant import ntnb
from refs import DATA_REF, PU_OFICIAL_REF, TAXA_REF, VNA_REF

IDX_AGO_2026 = "7633.23"
IPCA_SET_2026_PROJ = "0.56"
VNA_15_09_2026 = Decimal("4727.570573")


def test_vna_numero_indice():
    vna_15 = ntnb.vna_numero_indice(IDX_AGO_2026)          # 1000 * 7633,23/1614,62
    assert vna_15 == VNA_15_09_2026
    vna_liq = ntnb.vna_projetado(vna_15, IPCA_SET_2026_PROJ, DATA_REF)  # pr = 10/30
    pu = ntnb.pu_oficial(TAXA_REF, vna_liq, DATA_REF)
    print(f"\nVNA 15/09={vna_15} VNA 25/09={vna_liq} (implícito {VNA_REF}, dif {float(vna_liq)-VNA_REF:+.6f}) "
          f"PU={pu} oficial={PU_OFICIAL_REF} dif={float(pu)-PU_OFICIAL_REF:+.6f}")
    assert abs(float(pu) - PU_OFICIAL_REF) < 0.02
    assert abs(float(vna_liq) - VNA_REF) < 0.02


@pytest.mark.parametrize("liq, esperado", [
    (date(2027, 1, 10), Decimal("4749.764898")),   # antes do dia 15 + virada de ano: 15/12->15/01, pr=26/31
    (date(2026, 12, 20), Decimal("4731.830643")),  # depois do dia 15, período 15/12->15/01, pr=5/31
    (date(2026, 12, 15), VNA_15_09_2026),          # no próprio dia 15: pr = 0
])
def test_vna_projetado_ramos(liq, esperado):
    v = ntnb.vna_projetado(VNA_15_09_2026, IPCA_SET_2026_PROJ, liq)
    print(f"\n{liq}: {v}")
    assert v == esperado


def test_vna_projetado_ramo_dezembro_formula_independente():
    # conferência do valor fixo acima por fórmula direta (float)
    assert float(ntnb.vna_projetado(VNA_15_09_2026, "0.56", date(2026, 12, 20))) == pytest.approx(
        4727.570573 * 1.0056 ** (5 / 31), abs=1e-6)


def test_dv01_notional():
    s = ntnb.sensibilidades(TAXA_REF, DATA_REF, vna=VNA_REF)
    dv01 = ntnb.dv01_notional(s.dv01_pu, PU_OFICIAL_REF, 10_000_000)
    print(f"\nDV01/título={s.dv01_pu:.6f}  títulos={10_000_000/PU_OFICIAL_REF:.2f}  DV01 R$10mi={dv01:.2f}")
    assert dv01 == pytest.approx(11_203, abs=1.0)
    assert ntnb.dv01_notional(s.dv01_pu, PU_OFICIAL_REF, 20_000_000) == pytest.approx(2 * dv01)
    with pytest.raises(ValueError):
        ntnb.dv01_notional(s.dv01_pu, 0, 1e7)
