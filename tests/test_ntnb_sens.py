"""Duration, DV01 e convexidade: analítico vs bump."""
from datetime import date

import pytest

from quant import ntnb
from refs import DATA_REF, TAXA_REF, VNA_REF

BP = 0.01  # 1 bp em % a.a.
CASOS = [(date(2026, 9, 25), 7.38), (date(2026, 9, 25), 4.00), (date(2026, 9, 25), 10.0),
         (date(2024, 1, 2), 5.60), (date(2050, 2, 14), 7.38)]


@pytest.mark.parametrize("liq, taxa", CASOS)
def test_dv01_analitico_vs_bump(liq, taxa):
    s = ntnb.sensibilidades(taxa, liq)
    down = ntnb.cotacao_continua(taxa - BP, liq)
    up = ntnb.cotacao_continua(taxa + BP, liq)
    dv01_bump = (down - up) / 2
    print(f"\n{liq} {taxa}%: DV01 analít={s.dv01_cotacao:.10f} bump={dv01_bump:.10f} "
          f"rel={(dv01_bump/s.dv01_cotacao-1):+.2e}")
    assert dv01_bump == pytest.approx(s.dv01_cotacao, rel=1e-6)


@pytest.mark.parametrize("liq, taxa", CASOS)
def test_convexidade_analitica_vs_bump(liq, taxa):
    s = ntnb.sensibilidades(taxa, liq)
    p0 = ntnb.cotacao_continua(taxa, liq)
    h = 1e-4  # em decimal; 1 bp
    down = ntnb.cotacao_continua(taxa - 100 * h, liq)
    up = ntnb.cotacao_continua(taxa + 100 * h, liq)
    conv_bump = (up + down - 2 * p0) / (p0 * h * h)
    assert conv_bump == pytest.approx(s.convexidade, rel=1e-4)


def test_dv01_pricer_oficial_vs_analitico():
    """Com truncamentos oficiais (cotação T4) o bump fica ruidoso, mas próximo."""
    liq, taxa, vna = DATA_REF, TAXA_REF, VNA_REF
    s = ntnb.sensibilidades(taxa, liq, vna)
    up = float(ntnb.pu_oficial(taxa + BP, vna, liq))
    down = float(ntnb.pu_oficial(taxa - BP, vna, liq))
    dv01_of = (down - up) / 2
    print(f"\nDV01 R$/título: analít={s.dv01_pu:.6f} bump oficial={dv01_of:.6f}")
    assert dv01_of == pytest.approx(s.dv01_pu, rel=2e-3)


def test_sinais_e_consistencia():
    s = ntnb.sensibilidades(TAXA_REF, DATA_REF, vna=VNA_REF)
    assert s.dv01_pu > 0 and s.convexidade > 0
    assert s.duration_modificada == pytest.approx(s.duration_macaulay / 1.0738)
    # queda de taxa => PU sobe (visão do cliente)
    assert ntnb.cotacao_continua(7.28, date(2026, 9, 25)) > ntnb.cotacao_continua(7.38, date(2026, 9, 25))
    # aproximação de 2ª ordem vs repricing em -100 bp
    p0 = s.cotacao
    exato = ntnb.cotacao_continua(6.38, date(2026, 9, 25)) - p0
    aprox = p0 * (s.duration_modificada * 0.01 + 0.5 * s.convexidade * 0.01 ** 2)
    assert aprox == pytest.approx(exato, rel=1e-2)


def test_continua_proxima_da_oficial():
    liq = date(2026, 9, 25)
    assert ntnb.cotacao_continua(7.38, liq) == pytest.approx(float(ntnb.cotacao_oficial(7.38, liq)), abs=2e-4)


def test_inversa_taxa():
    liq = date(2026, 9, 25)
    assert ntnb.taxa_de_cotacao(ntnb.cotacao_continua(7.38, liq), liq) == pytest.approx(7.38, abs=1e-8)
