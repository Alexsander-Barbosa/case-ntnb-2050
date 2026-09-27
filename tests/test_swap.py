"""TRS / asset swap sobre a NTN-B 2050: cliente recebe o retorno do título (IPCA + 7,38%) e paga CDI."""
from datetime import date

import pytest

from quant import calendar as cal
from quant import ntnb
from quant import premissas as P
from quant.curva_di import CurvaDI
from quant.swap import NOME_ESTRUTURA, TRSNTNB, vna_encadeado
from refs import PU_OFICIAL_REF, TAXA_REF, VNA_REF

ANCORA_15 = date(2026, 9, 15)
H = P.HORIZONTE_PADRAO


@pytest.fixture(scope="module")
def curva_b():
    return CurvaDI.de_csv(P.CURVA_DI_CSV, P.CDI_DIA_PCT)


@pytest.fixture(scope="module")
def curva_a():
    return CurvaDI.flat(P.DATA_REF, P.CDI_DIA_PCT)


@pytest.fixture(scope="module")
def swap():
    return TRSNTNB(P.NOTIONAL_PADRAO, TAXA_REF, P.DATA_REF, VNA_REF)


@pytest.fixture(scope="module")
def vna_h():
    v15 = ntnb.vna_numero_indice(P.IDX_IPCA_AGO_2026)
    return float(vna_encadeado(v15, ANCORA_15, P.IPCA_HORIZONTE_PCT, H))


# ------------------------------------------------------------------ VNA no horizonte
def test_vna_encadeado_horizonte(vna_h):
    # 15/09 -> 15/10 (set 0,56% embutido) -> 15/11 (out) -> 15/12 (nov) -> 28/12 pro rata dez (13/31)
    esperado = 4727.570573 * 1.0056 * 1.0033 * 1.0035 * 1.0054 ** (13 / 31)
    print(f"\nVNA 28/12/2026 = {vna_h:.6f} (fórmula direta {esperado:.6f})")
    assert vna_h == pytest.approx(esperado, abs=2e-3)  # truncamentos T6/T14 intermediários


def test_vna_encadeado_sem_ipca_disponivel():
    with pytest.raises(ValueError):
        vna_encadeado(4727.570573, ANCORA_15, P.IPCA_HORIZONTE_PCT, date(2027, 1, 20))


def test_premissas_ipca_horizonte():
    from decimal import Decimal
    assert P.IPCA_FOCUS_PCT[(2026, 9)] == Decimal("0.52")      # dado bruto do Focus intacto
    assert P.IPCA_HORIZONTE_PCT[(2026, 9)] == Decimal("0.56")  # override: projeção embutida no preço
    assert all(P.IPCA_HORIZONTE_PCT[k] == P.IPCA_FOCUS_PCT[k] for k in P.IPCA_FOCUS_PCT if k != (2026, 9))


def test_vna_horizonte_coerente_com_vna_ref():
    # com set=0,56% o encadeamento até 25/09 reproduz o VNA de referência (dif. de R$ 0,004, já conhecida)
    v15 = ntnb.vna_numero_indice(P.IDX_IPCA_AGO_2026)
    v = float(vna_encadeado(v15, ANCORA_15, P.IPCA_HORIZONTE_PCT, P.DATA_REF))
    assert abs(v - VNA_REF) < 0.01


def test_nome_estrutura():
    assert NOME_ESTRUTURA.startswith("TRS / asset swap sobre a NTN-B 2050")


# ------------------------------------------------------------------ contratação
@pytest.mark.parametrize("nome", ["B", "A"])
def test_swap_vale_zero_na_contratacao(swap, curva_b, curva_a, nome):
    c = curva_b if nome == "B" else curva_a
    v0 = swap.valor(P.DATA_REF, TAXA_REF, VNA_REF, c)
    print(f"\ncurva {nome}: V0 = {v0:.10f}")
    assert abs(v0) < 1e-6


def test_dimensionamento_vs_pu_oficial(swap):
    # Q é dimensionado pela camada contínua; pelo PU oficial (truncado) a diferença é ínfima
    dif = swap.quantidade * float(ntnb.pu_oficial(TAXA_REF, VNA_REF, P.DATA_REF)) - P.NOTIONAL_PADRAO
    print(f"\nQ={swap.quantidade:.4f}  Q*PU_oficial - notional = R$ {dif:+.4f}")
    assert abs(dif) < 10.0  # < 0,001 bp de DV01


def test_taxa_fixa_fora_do_mercado_nao_vale_zero(curva_b):
    sw = TRSNTNB(P.NOTIONAL_PADRAO, 7.48, P.DATA_REF, VNA_REF)  # recebe 7,48% com mercado a 7,38%
    v0 = sw.valor(P.DATA_REF, TAXA_REF, VNA_REF, curva_b)
    assert v0 > 0 and v0 == pytest.approx(sw.dv01(P.DATA_REF, 7.43, VNA_REF) * 10, rel=1e-3)


# ------------------------------------------------------------------ P&L
@pytest.mark.parametrize("nome", ["B", "A"])
def test_sem_choque_pnl_igual_carry(swap, curva_b, curva_a, vna_h, nome):
    c = curva_b if nome == "B" else curva_a
    r = swap.pnl_horizonte(H, 0.0, vna_h, c)
    print(f"\ncurva {nome}: carry={r.carry:,.2f} (real {r.carry_real:,.2f} | ipca {r.carry_ipca:,.2f} "
          f"| cdi {r.carry_cdi:,.2f})  total={r.total:,.2f}  F_CDI={r.fator_cdi:.10f}")
    assert r.marcacao == 0.0
    assert r.total == pytest.approx(r.carry, abs=1e-6)
    assert r.carry == pytest.approx({"B": -10_054.38, "A": -12_289.17}[nome], abs=1.0)
    assert r.carry_real + r.carry_ipca + r.carry_cdi == pytest.approx(r.carry, abs=1e-6)


def test_carry_forma_fechada_sem_dupla_contagem(swap, curva_b, vna_h):
    """carry = N*[(VNA_H/VNA_0)*(1+y)^(du/252) - F_CDI]: IPCA entra uma única vez."""
    r = swap.pnl_horizonte(H, 0.0, vna_h, curva_b)
    du = cal.du(P.DATA_REF, H)
    fechada = P.NOTIONAL_PADRAO * ((vna_h / VNA_REF) * (1 + TAXA_REF / 100) ** (du / 252) - r.fator_cdi)
    assert r.carry == pytest.approx(fechada, abs=1e-4)


@pytest.mark.parametrize("delta", [-100, -25, -1, 1, 25, 100])
def test_identidade_total_igual_carry_mais_marcacao(swap, curva_b, vna_h, delta):
    r = swap.pnl_horizonte(H, delta, vna_h, curva_b)
    assert r.total == pytest.approx(r.carry + r.marcacao, abs=1e-6)


@pytest.mark.parametrize("delta", [-1, 1])
def test_horizonte_zero_pnl_igual_menos_dv01_vezes_delta(swap, curva_b, delta):
    r = swap.pnl_horizonte(P.DATA_REF, delta, VNA_REF, curva_b)
    dv01 = swap.dv01(P.DATA_REF, TAXA_REF, VNA_REF)
    print(f"\nΔ={delta:+d} bp: P&L={r.total:,.4f}  -DV01*Δ={-dv01*delta:,.4f}")
    assert r.carry == pytest.approx(0.0, abs=1e-6)
    assert r.total == pytest.approx(-dv01 * delta, rel=1e-3)


@pytest.mark.parametrize("delta", [-50, 50])
def test_horizonte_zero_choque_grande_segunda_ordem(swap, curva_b, delta):
    r = swap.pnl_horizonte(P.DATA_REF, delta, VNA_REF, curva_b)
    s = ntnb.sensibilidades(TAXA_REF, P.DATA_REF, VNA_REF)
    dy = delta / 1e4
    aprox = P.NOTIONAL_PADRAO * (-s.duration_modificada * dy + 0.5 * s.convexidade * dy ** 2)
    print(f"\nΔ={delta:+d} bp: P&L={r.total:,.2f}  2ª ordem={aprox:,.2f}  só DV01={-swap.dv01(P.DATA_REF, TAXA_REF, VNA_REF)*delta:,.2f}")
    assert r.total == pytest.approx(aprox, rel=5e-3)


def test_sinal_queda_de_taxa_ganho(swap, curva_b, vna_h):
    assert swap.pnl_horizonte(P.DATA_REF, -10, VNA_REF, curva_b).total > 0
    assert swap.pnl_horizonte(P.DATA_REF, +10, VNA_REF, curva_b).total < 0
    assert swap.pnl_horizonte(H, -10, vna_h, curva_b).marcacao > 0
    assert swap.dv01(P.DATA_REF, TAXA_REF, VNA_REF) > 0


def test_dv01_swap_igual_ntnb_mesmo_notional(swap):
    dv01_swap = swap.dv01(P.DATA_REF, TAXA_REF, VNA_REF)
    s = ntnb.sensibilidades(TAXA_REF, P.DATA_REF, VNA_REF)
    dv01_ntnb = ntnb.dv01_notional(s.dv01_pu, PU_OFICIAL_REF, P.NOTIONAL_PADRAO)
    print(f"\nDV01 swap={dv01_swap:,.2f}  DV01 NTN-B R$10mi={dv01_ntnb:,.2f}  dif={dv01_swap-dv01_ntnb:+.2f}")
    assert dv01_swap == pytest.approx(dv01_ntnb, abs=1.0)
    assert dv01_swap == pytest.approx(11_203, abs=5.0)


def test_carry_curva_b_vs_flat(swap, curva_b, curva_a, vna_h):
    rb = swap.pnl_horizonte(H, 0.0, vna_h, curva_b)
    ra = swap.pnl_horizonte(H, 0.0, vna_h, curva_a)
    dif = rb.carry - ra.carry
    du = cal.du(P.DATA_REF, H)
    # 28/12 é vértice (13,55%): diferença exata = N * [(1,1365)^(62/252) - (1,1355)^(62/252)]
    exata = P.NOTIONAL_PADRAO * ((1.1365) ** (du / 252) - (1.1355) ** (du / 252))
    print(f"\ncarry B={rb.carry:,.2f}  A={ra.carry:,.2f}  B-A={dif:,.2f}  forma fechada={exata:,.2f}")
    assert dif == pytest.approx(exata, abs=0.01)
    assert 2_000 < dif < 2_600  # "≈ R$ 2,5 mil" (estimativa linear 0,10 p.p. x 1/4 de ano)


def test_cupom_no_horizonte_nao_suportado(swap, curva_b):
    with pytest.raises(NotImplementedError):
        swap.pnl_horizonte(date(2027, 2, 16), 0.0, VNA_REF, curva_b)
