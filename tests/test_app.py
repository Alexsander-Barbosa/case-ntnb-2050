"""O app.py roda de ponta a ponta sem exceção (streamlit.testing), com e sem mudança de widgets."""
from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(scope="module")
def at():
    a = AppTest.from_file(APP, default_timeout=120)
    a.run()
    return a


def test_app_roda_sem_excecao(at):
    assert not at.exception, at.exception
    assert len(at.get("plotly_chart")) == 5
    assert len(at.dataframe) == 2          # métricas + premissas


def test_app_metricas_topo(at):
    vals = {m.label: m.value for m in at.metric}
    print("\n" + "\n".join(f"{k}: {v}" for k, v in vals.items()))
    assert vals["Carry do TRS até 28/12"] == "−R$ 10.054"
    assert vals["Prêmio da opção (hoje)"] == "R$ 152.106"
    assert vals["Taxa real forward (28/12)"] == "7,371%"


def test_app_premissa_ilustrativa_na_tela(at):
    assert any("Premissa ilustrativa" in w.value for w in at.warning)


def test_app_widgets_estresse_curva_a_strike(at):
    at.sidebar.radio[0].set_value("Estresse (100)")
    at.sidebar.radio[1].set_value("A")
    at.sidebar.checkbox[0].uncheck()
    at.run()
    at.sidebar.number_input[0].set_value(7.25)
    at.sidebar.slider[0].set_value(25)
    at.run()
    assert not at.exception, at.exception
    assert len(at.get("plotly_chart")) == 5
