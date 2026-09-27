"""Call europeia sobre o PU da NTN-B 2050 (= put na taxa real), vencimento 28/12/2026."""
from datetime import date

import numpy as np
import pytest
from scipy import integrate, stats

from quant import ntnb
from quant import premissas as P
from quant.curva_di import CurvaDI
from quant.option import NOME_ESTRUTURA, CallPUNTNB
from quant.swap import vna_encadeado
from refs import TAXA_REF, VNA_REF

S_BASE, S_ESTRESSE = P.VOL_TAXA_REAL_BASE_BPS, P.VOL_TAXA_REAL_ESTRESSE_BPS
STRIKES = [7.20, None, 7.55]  # OTM, ATM forward, ITM (para a call no PU)
# Call no PU exerce se y_H < K: K = 7,55% está ITM (K_PU < PU_fwd); K = 7,20% está OTM.


@pytest.fixture(scope="module")
def opc():
    curva = CurvaDI.de_csv(P.CURVA_DI_CSV, P.CDI_DIA_PCT)
    vh = float(vna_encadeado(ntnb.vna_numero_indice(P.IDX_IPCA_AGO_2026), date(2026, 9, 15),
                             P.IPCA_HORIZONTE_PCT, P.HORIZONTE_PADRAO))
    return CallPUNTNB(P.NOTIONAL_PADRAO, P.DATA_REF, P.HORIZONTE_PADRAO, VNA_REF, vh, curva, TAXA_REF)


def test_premissas_vol():
    assert (S_BASE, S_ESTRESSE) == (70.0, 100.0)
    assert NOME_ESTRUTURA.startswith("Call europeia sobre o PU da NTN-B 2050")


def test_forward(opc):
    yf = opc.taxa_forward()
    print(f"\ny_f = {yf:.6f}%  ({(yf - TAXA_REF) * 100:+.3f} bp vs spot)  DF={opc.DF:.6f}  T={opc.T:.6f}")
    assert yf == pytest.approx(7.3711, abs=1e-4)  # 0,01 bp
    assert opc.k_pu(yf) == pytest.approx(opc.pu_forward(), abs=1e-6)


def test_forward_coerente_com_carry_do_trs(opc):
    # carry do TRS ≈ -10.054 => forward ≈ spot - carry/DV01 ≈ -0,9 bp
    assert (opc.taxa_forward() - TAXA_REF) * 100 == pytest.approx(-10_054.38 / 11_203, abs=0.02)


def test_quadratura_vs_adaptativa(opc):
    """Gauss-Legendre na região de exercício vs scipy.quad (referência)."""
    s = opc._s(S_BASE)
    mu, k = opc.media(S_BASE), opc.strike_atm
    kpu = opc.k_pu(k)
    ref, _ = integrate.quad(lambda z: (float(opc._pu_H(mu + s * z)) - kpu) * stats.norm.pdf(z),
                            -12, (k - mu) / s, epsabs=1e-11, limit=200)
    ref *= opc.DF * opc.quantidade
    gl = opc.premio(S_BASE)
    x, w = np.polynomial.hermite_e.hermegauss(200)
    gh = opc.DF * opc.quantidade * float((np.maximum(opc._pu_H(mu + s * x) - kpu, 0) * w).sum() / np.sqrt(2 * np.pi))
    print(f"\nGL96={gl:,.4f}  quad={ref:,.4f}  dif={gl - ref:+.2e}   (Gauss-Hermite puro n=200: {gh:,.2f}, erro {gh - ref:+,.2f})")
    assert abs(gl - ref) < 0.01
    assert abs(gh - ref) > 100  # por que não usar GH puro com a quina do payoff


@pytest.mark.parametrize("sigma", [S_BASE, S_ESTRESSE, 1.0, 0.01])
@pytest.mark.parametrize("k", STRIKES)
def test_premio_maior_igual_intrinseco(opc, sigma, k):
    for tipo in ("call", "put"):
        p, i = opc.premio(sigma, k, tipo=tipo), opc.intrinseco(k, tipo=tipo)
        assert p >= i - 1e-6, (tipo, p, i)


@pytest.mark.parametrize("k", STRIKES)
def test_converge_ao_intrinseco_quando_vol_zero(opc, k):
    difs = [opc.premio(s, k) - opc.intrinseco(k) for s in (70, 10, 1, 0.1, 0.0)]
    print(f"\nK={k}: prêmio - intrínseco para σ=70,10,1,0.1,0: " + ", ".join(f"{d:,.4f}" for d in difs))
    assert all(a >= b - 1e-6 for a, b in zip(difs, difs[1:]))  # monotônico
    assert abs(difs[-1]) < 1e-6                                  # σ = 0: exatamente o intrínseco
    if k is None:
        # ATM: valor tempo é LINEAR em σ (≈ vega × σ) — converge em O(σ)
        vega = opc.greeks(1.0, h_vol=0.5)["vega"]
        assert difs[-2] == pytest.approx(vega * 0.1, rel=1e-2)
        assert difs[-3] == pytest.approx(vega * 1.0, rel=1e-2)
    else:
        # fora do dinheiro/dentro: valor tempo cai exponencialmente
        assert abs(difs[-3]) < 1e-2 and abs(difs[-2]) < 1e-2


@pytest.mark.parametrize("sigma", [S_BASE, S_ESTRESSE])
@pytest.mark.parametrize("k", STRIKES)
def test_put_call_parity_em_pu(opc, sigma, k):
    kk = opc.strike_atm if k is None else k
    c, p = opc.premio(sigma, kk, tipo="call"), opc.premio(sigma, kk, tipo="put")
    rhs = opc.DF * opc.quantidade * (opc.pu_forward() - opc.k_pu(kk))
    print(f"\nσ={sigma} K={kk:.4f}: C={c:,.4f} P={p:,.4f} C-P={c - p:,.4f} DF*Q*(PUfwd-K_PU)={rhs:,.4f}")
    assert c - p == pytest.approx(rhs, abs=0.05)


def test_parity_quebra_sem_ajuste_de_convexidade(opc):
    """Especificação literal (y ~ Normal(y_f)) viola a parity: documenta o motivo do ajuste."""
    k = opc.strike_atm
    c = opc.premio(S_BASE, k, tipo="call", martingale=False)
    p = opc.premio(S_BASE, k, tipo="put", martingale=False)
    quebra = (c - p) - opc.DF * opc.quantidade * (opc.pu_forward() - opc.k_pu(k))
    print(f"\nsem ajuste: C={c:,.2f} P={p:,.2f} quebra da parity={quebra:,.2f}  "
          f"ajuste μ-y_f={(opc.media(S_BASE) - opc.taxa_forward()) * 100:.3f} bp")
    assert 11_000 < quebra < 12_500


@pytest.mark.parametrize("sigma", [S_BASE, S_ESTRESSE])
def test_bachelier_vs_integracao_atm(opc, sigma):
    exato = opc.premio(sigma)
    b = opc.bachelier(sigma)
    dif = exato - b["premio"]
    print(f"\nσ={sigma}: exato={exato:,.2f}  Bachelier {b['premio_bp']:.3f} bp × DV01 × DF × Q = {b['premio']:,.2f}  "
          f"dif={dif:+,.2f} ({dif / exato:+.4%})")
    assert 0 < dif < 1e-3 * exato  # pequena e positiva: convexidade


def test_premio_atm_niveis(opc):
    p70, p100 = opc.premio(S_BASE), opc.premio(S_ESTRESSE)
    print(f"\nATM forward: σ=70 -> R$ {p70:,.2f} ({opc.bachelier(70)['premio_bp']:.2f} bp) | "
          f"σ=100 -> R$ {p100:,.2f} ({opc.bachelier(100)['premio_bp']:.2f} bp)")
    assert p70 == pytest.approx(150_000, rel=0.03)
    assert p100 == pytest.approx(215_000, rel=0.03)
    assert opc.bachelier(70)["premio_bp"] == pytest.approx(13.8, abs=0.1)


def test_premio_crescente_no_strike_em_taxa(opc):
    ps = [opc.premio(S_BASE, k) for k in (7.20, 7.30, 7.371118, 7.45, 7.55)]
    assert all(b > a for a, b in zip(ps, ps[1:]))


@pytest.mark.parametrize("sigma", [S_BASE, S_ESTRESSE])
def test_greeks_bump_vs_bachelier_e_sinais(opc, sigma):
    g = opc.greeks(sigma)
    b = opc.bachelier(sigma)
    print(f"\nσ={sigma}: delta bump={g['delta']:,.2f} bach={b['delta']:,.2f} | gamma bump={g['gamma']:,.3f} "
          f"bach={b['gamma']:,.3f} | vega bump={g['vega']:,.2f} bach={b['vega']:,.2f}  (R$/bp, R$/bp², R$ por bp/ano)")
    assert g["delta"] < 0 and g["gamma"] > 0 and g["vega"] > 0
    assert g["vega"] == pytest.approx(b["vega"], rel=1e-3)
    assert g["delta"] == pytest.approx(b["delta"], rel=5e-2)   # Bachelier ignora convexidade
    assert g["gamma"] == pytest.approx(b["gamma"], rel=1.5e-1)


def test_greeks_bump_convergido(opc):
    g1, g2 = opc.greeks(S_BASE, h_bp=1.0, h_vol=1.0), opc.greeks(S_BASE, h_bp=0.25, h_vol=0.25)
    assert g1["delta"] == pytest.approx(g2["delta"], rel=1e-4)
    assert g1["vega"] == pytest.approx(g2["vega"], rel=1e-4)
    assert g1["gamma"] == pytest.approx(g2["gamma"], rel=1e-2)


def test_queda_de_taxa_aumenta_call(opc):
    k = opc.strike_atm
    assert opc.premio(S_BASE, k, y_spot_pct=TAXA_REF - 0.10) > opc.premio(S_BASE, k) > \
        opc.premio(S_BASE, k, y_spot_pct=TAXA_REF + 0.10)


def test_cupom_antes_do_vencimento(opc):
    with pytest.raises(NotImplementedError):
        CallPUNTNB(P.NOTIONAL_PADRAO, P.DATA_REF, date(2027, 2, 16), VNA_REF, opc.vna_vencimento,
                   opc.curva, TAXA_REF)
