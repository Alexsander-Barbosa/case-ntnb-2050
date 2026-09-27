from datetime import date

import pytest

from quant import calendar as cal


@pytest.mark.parametrize("d2, esperado", [
    (date(2008, 8, 15), 61), (date(2009, 2, 15), 190), (date(2009, 8, 15), 314),
    (date(2010, 2, 15), 439), (date(2010, 8, 15), 564),
])
def test_du_exemplo_stn_ntnb(d2, esperado):
    # Exemplo NTN-B da metodologia STN (liquidação 21/05/2008)
    assert cal.du(date(2008, 5, 21), d2) == esperado


def test_du_exemplo_stn_ltn():
    assert cal.du(date(2008, 5, 21), date(2010, 7, 1)) == 532


def test_du_exemplo_stn_lft():
    assert cal.du(date(2008, 5, 21), date(2014, 3, 7)) == 1459


def test_feriados_nao_sao_du():
    assert not cal.is_du(date(2026, 11, 20))  # Consciência Negra (nacional desde 2024)
    assert not cal.is_du(date(2026, 12, 25))
    assert not cal.is_du(date(2026, 9, 26))   # sábado
    assert cal.is_du(date(2026, 9, 25))


def test_du_convencao_inclusive_exclusive():
    assert cal.du(date(2026, 9, 25), date(2026, 9, 25)) == 0
    assert cal.du(date(2026, 9, 25), date(2026, 9, 28)) == 1  # sex -> seg


def test_add_du():
    assert cal.add_du(date(2026, 9, 25), 1) == date(2026, 9, 28)
    assert cal.add_du(date(2026, 11, 19), 1) == date(2026, 11, 23)  # pula 20/11


def test_fora_da_cobertura():
    with pytest.raises(ValueError):
        cal.du(date(2000, 1, 3), date(2001, 1, 3))
