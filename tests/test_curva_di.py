import csv
from datetime import date

import pytest

from quant import calendar as cal
from quant import premissas as P
from quant.curva_di import CurvaDI


@pytest.fixture(scope="module")
def curva_b():
    return CurvaDI.de_csv(P.CURVA_DI_CSV, P.CDI_DIA_PCT)


@pytest.fixture(scope="module")
def curva_a():
    return CurvaDI.flat(P.DATA_REF, P.CDI_DIA_PCT)


def _linhas_csv():
    with open(P.CURVA_DI_CSV, newline="") as f:
        return list(csv.DictReader(f))


def test_csv_74_vertices(curva_b):
    assert len(curva_b.dus) == 74 and curva_b.data_ref == P.DATA_REF


def test_curva_reproduz_vertices(curva_b):
    pior = 0.0
    for l in _linhas_csv():
        venc = date.fromisoformat(l["vencimento"])
        r = curva_b.cdi_medio(P.DATA_REF, venc)
        pior = max(pior, abs(r - float(l["taxa_252_pct"])))
    print(f"\nmaior erro nos 74 vértices: {pior:.3e} p.p.")
    assert pior < 1e-8


@pytest.mark.parametrize("d1, d2", [
    (date(2026, 9, 25), date(2026, 9, 28)), (date(2026, 9, 25), date(2026, 12, 28)),
    (date(2026, 11, 3), date(2027, 3, 15)), (date(2026, 9, 25), date(2030, 1, 2)),
])
def test_curva_flat_cdi_medio_constante(curva_a, d1, d2):
    assert curva_a.cdi_medio(d1, d2) == pytest.approx(P.CDI_DIA_PCT, abs=1e-10)


@pytest.mark.parametrize("du_a, du_b", [(44, 54), (104, 114), (66, 75)])
def test_flat_forward_constante_entre_vertices(curva_b, du_a, du_b):
    i, j = curva_b.dus.index(du_a), curva_b.dus.index(du_b)
    assert j == i + 1, "vértices devem ser consecutivos"
    fa = (1 + curva_b.taxas_pct[i] / 100) ** (du_a / 252)
    fb = (1 + curva_b.taxas_pct[j] / 100) ** (du_b / 252)
    fwd_vertices = ((fb / fa) ** (252 / (du_b - du_a)) - 1) * 100
    fwds = []
    for k in range(du_a, du_b):
        d1, d2 = cal.add_du(P.DATA_REF, k), cal.add_du(P.DATA_REF, k + 1)
        fwds.append(curva_b.cdi_medio(d1, d2))
    print(f"\n{du_a}->{du_b} DU: forward={fwd_vertices:.8f}%  diários min={min(fwds):.8f} max={max(fwds):.8f}")
    assert max(fwds) - min(fwds) < 1e-9
    assert fwds[0] == pytest.approx(fwd_vertices, abs=1e-9)


def test_cdi_medio_horizonte_padrao(curva_b):
    r = curva_b.cdi_medio(P.DATA_REF, P.HORIZONTE_PADRAO)
    print(f"\nCDI médio 25/09->28/12 (curva B) = {r:.6f}%")
    assert cal.du(P.DATA_REF, P.HORIZONTE_PADRAO) == 62
    assert r == pytest.approx(13.55, abs=0.01)


def test_antes_do_primeiro_vertice_usa_cdi():
    c = CurvaDI(P.DATA_REF, 13.65, (10,), (14.00,))
    assert c.taxa_du(5) == pytest.approx(13.65, abs=1e-12)
    assert c.taxa_du(10) == pytest.approx(14.00, abs=1e-12)


def test_limites(curva_b):
    assert curva_b.fator_acumulado(P.DATA_REF, P.DATA_REF) == 1.0
    with pytest.raises(ValueError):
        curva_b.cdi_medio(P.DATA_REF, date(2027, 12, 1))  # além de 182 DU: sem extrapolação
    with pytest.raises(ValueError):
        CurvaDI(P.DATA_REF, 13.65, (10, 5), (13.6, 13.6))
