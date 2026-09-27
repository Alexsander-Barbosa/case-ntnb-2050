"""Cenários no horizonte (28/12/2026): NTN-B, TRS e opção, P&L em excesso ao CDI."""
import numpy as np
import pytest

from quant import ntnb
from quant import premissas as P
from quant.scenarios import ESTRUTURAS, cenarios_padrao
from refs import TAXA_REF

CARRY_TRS_B = -10_054.38


@pytest.fixture(scope="module")
def cen():
    return cenarios_padrao()


@pytest.fixture(scope="module")
def grade(cen):
    return cen.grade()


def test_grade_formato(grade):
    assert len(grade) == 41
    assert grade.delta_bps.iloc[0] == -100 and grade.delta_bps.iloc[-1] == 100
    assert np.allclose(np.diff(grade.delta_bps), 5)
    assert np.allclose(grade.taxa_H_pct, TAXA_REF + grade.delta_bps / 100)


def test_premissa_margem_declarada(cen):
    assert P.MARGEM_TRS_PCT_NOTIONAL == 0.10
    assert cen.metricas().loc["TRS", "capital"] == pytest.approx(1_000_000)


def test_delta_zero_trs_igual_carry(cen):
    assert cen.pnl_trs(0.0) == pytest.approx(CARRY_TRS_B, abs=0.01)


def test_ntnb_excesso_igual_trs_em_toda_grade(grade):
    dif = (grade.ntnb_excesso_cdi - grade.trs).abs().max()
    print(f"\nmax |NTN-B excesso CDI - TRS| na grade = {dif:.3e}")
    assert dif < 0.01


def test_ntnb_absoluto_menos_excesso_e_custo_do_cdi(cen, grade):
    # absoluto - excesso = N*(F_CDI - 1) em todo Δ
    assert np.allclose(grade.ntnb_absoluto - grade.ntnb_excesso_cdi, cen.notional * (cen.F - 1), atol=1e-6)


def test_opcao_expira_fora_e_perda_limitada(cen, grade):
    perda = cen.premio_capitalizado
    dk = cen.delta_exercicio_bps
    fora = grade[grade.delta_bps >= dk]
    print(f"\nprêmio={cen.premio:,.2f}  capitalizado={perda:,.2f}  Δ_K={dk:.4f} bp  pontos fora do dinheiro={len(fora)}")
    assert dk == pytest.approx((cen.strike - TAXA_REF) * 100)
    assert np.allclose(fora.opcao, -perda, atol=1e-6)
    assert grade.opcao.min() >= -perda - 1e-6
    for d in (dk, dk + 0.01, 50, 300):  # também fora da grade
        assert cen.pnl_opcao(d) == pytest.approx(-perda, abs=1e-6)


def test_break_even_trs_igual_forward(cen):
    be = cen.break_even("TRS")
    yf = cen.opcao.taxa_forward()
    print(f"\nBE TRS = {be:.4f} bp   forward - spot = {(yf - TAXA_REF) * 100:.4f} bp")
    assert be == pytest.approx(-0.9, abs=0.05)
    assert be == pytest.approx((yf - TAXA_REF) * 100, abs=1e-6)  # break-even = taxa forward
    assert cen.break_even("NTN-B") == pytest.approx(be, abs=1e-6)


def test_break_even_opcao(cen):
    be = cen.break_even("Opção")
    dv01_h = ntnb.sensibilidades(cen.strike, cen.horizonte, cen.vna_h).dv01_pu
    aprox = cen.delta_exercicio_bps - cen.premio_capitalizado / (cen.Q * dv01_h)
    print(f"\nBE opção brentq={be:.4f} bp  aproximação linear={aprox:.4f} bp  (Q*DV01_H={cen.Q * dv01_h:,.2f} R$/bp)")
    assert cen.pnl_opcao(be) == pytest.approx(0.0, abs=1e-4)
    assert be == pytest.approx(-15, abs=1.0)
    assert aprox < be < aprox + 0.5  # convexidade: precisa de um pouco menos de queda que o linear


@pytest.mark.parametrize("col", ["ntnb_excesso_cdi", "ntnb_absoluto", "trs"])
def test_monotonicidade_estrita_ntnb_trs(grade, col):
    assert (np.diff(grade[col]) < 0).all()


def test_monotonicidade_opcao(cen, grade):
    assert (np.diff(grade.opcao) <= 1e-9).all()
    dentro = grade[grade.delta_bps < cen.delta_exercicio_bps]
    assert (np.diff(dentro.opcao) < 0).all()


@pytest.mark.parametrize("col", ["ntnb_excesso_cdi", "trs"])
@pytest.mark.parametrize("d", [25, 50, 100])
def test_assimetria_convexidade(grade, col, d):
    p = grade.set_index("delta_bps")[col]
    ganho, perda = p[-d] - p[0], p[0] - p[d]
    print(f"\n{col} ±{d} bp: ganho na queda={ganho:,.2f}  perda na alta={perda:,.2f}  assimetria={ganho - perda:,.2f}")
    assert ganho > perda > 0


@pytest.mark.parametrize("col", ["ntnb_excesso_cdi", "ntnb_absoluto", "trs", "opcao"])
def test_sinal_queda_de_taxa_ganho(grade, col):
    p = grade.set_index("delta_bps")[col]
    assert p[-25] > p[0] >= p[25]


def test_metricas(cen):
    m = cen.metricas()
    print("\n" + m.to_string(float_format=lambda x: f"{x:,.2f}"))
    assert list(m.index) == list(ESTRUTURAS)
    assert (m.ganho_por_bp_queda_hoje > 0).all()
    assert m.loc["NTN-B", "ganho_por_bp_queda_hoje"] == pytest.approx(11_203, abs=5)
    assert m.loc["Opção", "ganho_por_bp_queda_hoje"] == pytest.approx(5_737, abs=5)
    assert m.loc["Opção", "perda_maxima"] == pytest.approx(-cen.premio_capitalizado)
    assert m.loc["Opção", "capital"] == pytest.approx(cen.premio)
    assert bool(m.loc["Opção", "perda_limitada"]) and not bool(m.loc["TRS", "perda_limitada"])
    assert m.loc["NTN-B", "perda_maxima"] == pytest.approx(cen.pnl_ntnb_excesso(100))


def test_parametros_propagam(cen):
    c100 = cenarios_padrao(curva=cen.curva, sigma_bps=100.0)
    assert c100.premio > cen.premio
    assert c100.break_even("Opção") < cen.break_even("Opção")
    assert c100.break_even("TRS") == pytest.approx(cen.break_even("TRS"))
