"""Call europeia sobre o PU da NTN-B 2050 (= put na taxa real) — vencimento no horizonte H.

Payoff em H (R$):  Q * max(PU_H - K_PU, 0),  PU_H = VNA_H * cot(y_H, H)/100,  K_PU = VNA_H * cot(K, H)/100.
Q = notional / PU_0 (fixo na contratação, calculado à taxa de referência).

Forward (sem arbitragem com o TRS/NTN-B financiada a CDI; sem cupom até H):
    PU_fwd = PU_0 * F_CDI(t0, H)           y_f: VNA_H * cot(y_f, H)/100 = PU_fwd
Distribuição: y_H ~ Normal(μ, s²), s = σ[bps/ano]/100 * √T (em p.p.), T = DU(t0,H)/252.

CENTRAGEM (desvio consciente da especificação "Normal(y_f, ·)"): o PU é convexo na taxa,
logo com μ = y_f teríamos E[PU_H] > PU_fwd e a put-call parity em PU quebraria
(≈ R$ 11,6 mil em R$ 10 mi com σ = 70). Por padrão μ é o ajuste de convexidade que torna o
PU martingale sob a medida forward: E[PU(μ + sZ)] = PU_fwd (μ ≈ y_f + 1,05 bp com σ = 70).
`martingale=False` reproduz a especificação literal (só para demonstração).

Integração: o payoff tem quina em y = K; Gauss-Hermite puro erra centenas de reais (n=200: +R$ 243).
Usa-se Gauss-Legendre (n=96) apenas na região de exercício, truncada em ±12 desvios
(call: [-12, min(z_K, 12)]), onde o integrando
é suave (erro < R$ 0,01 vs quadratura adaptativa). Gauss-Hermite é usado onde é exato na
prática: E[PU] (integrando suave) para achar μ.

Prêmio = DF * Q * E[payoff/Q],  DF = 1/F_CDI(t0, H). Tudo em R$. P&L > 0 = ganho do cliente.
Taxas em % a.a. base 252; choques e vol em bps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cached_property
from math import sqrt

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from . import calendar as cal
from . import ntnb
from .curva_di import CurvaDI

NOME_ESTRUTURA = "Call europeia sobre o PU da NTN-B 2050 (= put na taxa real)"

_GL_X, _GL_W = np.polynomial.legendre.leggauss(96)
_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(64)
_GH_W = _GH_W / np.sqrt(2 * np.pi)
_CAUDA_Z = 12.0


@dataclass(frozen=True)
class CallPUNTNB:
    notional: float
    data_inicio: date
    vencimento_opcao: date
    vna_inicio: float        # VNA em t0 (marcação)
    vna_vencimento: float    # VNA_H (encadeado com IPCA_HORIZONTE_PCT)
    curva: CurvaDI
    taxa_ref_pct: float      # taxa real de mercado em t0 (dimensiona Q e o strike ATM)
    vencimento_titulo: date = ntnb.VENC_2050

    def __post_init__(self):
        if self.vencimento_opcao <= self.data_inicio:
            raise ValueError("vencimento da opção deve ser posterior ao início")
        if any(self.data_inicio < c <= self.vencimento_opcao for c in ntnb.datas_cupom(self.vencimento_titulo)):
            raise NotImplementedError("cupom antes do vencimento da opção: fluxo intermediário não modelado")

    # ------------------------------------------------------------------ dados derivados
    @cached_property
    def T(self) -> float:
        return cal.du(self.data_inicio, self.vencimento_opcao) / 252

    @cached_property
    def fator_cdi(self) -> float:
        return self.curva.fator_acumulado(self.data_inicio, self.vencimento_opcao)

    @property
    def DF(self) -> float:
        return 1.0 / self.fator_cdi

    @cached_property
    def _fluxos_H(self):
        fl = ntnb.fluxos(self.vencimento_opcao, self.vencimento_titulo)
        return np.array([f.du / 252 for f in fl]), np.array([float(f.valor) for f in fl])

    def _pu_H(self, y_pct) -> np.ndarray:
        """PU no vencimento da opção (R$/título), vetorizado na taxa real."""
        t, cf = self._fluxos_H
        y = np.asarray(y_pct, dtype=float)[..., None] / 100
        return self.vna_vencimento * (cf * (1 + y) ** -t).sum(-1) / 100

    def pu_spot(self, y_spot_pct: float) -> float:
        return self.vna_inicio * ntnb.cotacao_continua(y_spot_pct, self.data_inicio, self.vencimento_titulo) / 100

    @cached_property
    def quantidade(self) -> float:
        return self.notional / self.pu_spot(self.taxa_ref_pct)

    def pu_forward(self, y_spot_pct: float | None = None) -> float:
        y = self.taxa_ref_pct if y_spot_pct is None else y_spot_pct
        return self.pu_spot(y) * self.fator_cdi

    def taxa_forward(self, y_spot_pct: float | None = None) -> float:
        alvo = self.pu_forward(y_spot_pct)
        return brentq(lambda y: float(self._pu_H(y)) - alvo, -5.0, 40.0, xtol=1e-13)

    @cached_property
    def strike_atm(self) -> float:
        """ATM forward, fixado na contratação (não se move nos bumps de greeks)."""
        return self.taxa_forward(self.taxa_ref_pct)

    def k_pu(self, strike_pct: float) -> float:
        return float(self._pu_H(strike_pct))

    # ------------------------------------------------------------------ distribuição
    def _s(self, sigma_bps: float) -> float:
        return sigma_bps / 100 * sqrt(self.T)  # desvio da taxa no vencimento, em p.p.

    def media(self, sigma_bps: float, y_spot_pct: float | None = None, martingale: bool = True) -> float:
        yf = self.taxa_forward(y_spot_pct)
        s = self._s(sigma_bps)
        if not martingale or s == 0:
            return yf
        alvo = self.pu_forward(y_spot_pct)
        e_pu = lambda m: float((self._pu_H(m + s * _GH_X) * _GH_W).sum())
        return brentq(lambda m: e_pu(m) - alvo, yf - 1.0, yf + 1.0, xtol=1e-13)

    # ------------------------------------------------------------------ preço
    def premio(self, sigma_bps: float, strike_pct: float | None = None, y_spot_pct: float | None = None,
               tipo: str = "call", martingale: bool = True) -> float:
        """Prêmio em R$ na data de início. call = sobre o PU (ganha com queda de taxa)."""
        if sigma_bps < 0:
            raise ValueError("vol negativa")
        k = self.strike_atm if strike_pct is None else strike_pct
        kpu = self.k_pu(k)
        s = self._s(sigma_bps)
        mu = self.media(sigma_bps, y_spot_pct, martingale)
        if s == 0:
            pu = float(self._pu_H(mu))
            payoff = max(pu - kpu, 0.0) if tipo == "call" else max(kpu - pu, 0.0)
            return self.DF * self.quantidade * payoff
        zk = (k - mu) / s
        # região de exercício truncada em ±12 desvios (massa fora < 1e-32)
        if tipo == "call":      # exerce se y < K  (PU > K_PU)
            a, b, sinal = -_CAUDA_Z, min(zk, _CAUDA_Z), 1.0
        elif tipo == "put":     # exerce se y > K
            a, b, sinal = max(zk, -_CAUDA_Z), _CAUDA_Z, -1.0
        else:
            raise ValueError("tipo deve ser 'call' ou 'put'")
        if b <= a:
            return 0.0
        z = (b - a) / 2 * _GL_X + (a + b) / 2
        integrando = sinal * (self._pu_H(mu + s * z) - kpu) * norm.pdf(z)
        esperado = float((integrando * _GL_W).sum() * (b - a) / 2)
        return self.DF * self.quantidade * esperado

    def intrinseco(self, strike_pct: float | None = None, y_spot_pct: float | None = None,
                   tipo: str = "call") -> float:
        """Intrínseco descontado sobre o forward: DF * Q * max(±(PU_fwd - K_PU), 0)."""
        k = self.strike_atm if strike_pct is None else strike_pct
        d = self.pu_forward(y_spot_pct) - self.k_pu(k)
        return self.DF * self.quantidade * max(d if tipo == "call" else -d, 0.0)

    # ------------------------------------------------------------------ conferência Bachelier
    def bachelier(self, sigma_bps: float, strike_pct: float | None = None,
                  y_spot_pct: float | None = None) -> dict:
        """Put na taxa (Bachelier, em bp) × DV01 no forward × DF × Q. Ignora a convexidade."""
        k = self.strike_atm if strike_pct is None else strike_pct
        yf = self.taxa_forward(y_spot_pct)
        s_bp = sigma_bps * sqrt(self.T)
        d = (k - yf) * 100 / s_bp
        put_bp = s_bp * (d * norm.cdf(d) + norm.pdf(d))
        dv01_h = ntnb.sensibilidades(yf, self.vencimento_opcao, self.vna_vencimento,
                                     self.vencimento_titulo).dv01_pu
        dv01_0 = ntnb.sensibilidades(self.taxa_ref_pct if y_spot_pct is None else y_spot_pct,
                                     self.data_inicio, self.vna_inicio, self.vencimento_titulo).dv01_pu
        q, df = self.quantidade, self.DF
        return {
            "premio_bp": put_bp,
            "premio": df * q * dv01_h * put_bp,
            # dy_f/dy_spot = DV01_0 * F / DV01_H  => delta = -Q * DV01_0 * N(d)
            "delta": -q * dv01_0 * norm.cdf(d),
            "gamma": q * dv01_0 * norm.pdf(d) / s_bp * (dv01_0 * self.fator_cdi / dv01_h),
            "vega": df * q * dv01_h * sqrt(self.T) * norm.pdf(d),
        }

    # ------------------------------------------------------------------ greeks por bump
    def greeks(self, sigma_bps: float, strike_pct: float | None = None, y_spot_pct: float | None = None,
               h_bp: float = 1.0, h_vol: float = 1.0) -> dict:
        """delta (R$/bp de ALTA da taxa spot; < 0), gamma (R$/bp²), vega (R$ por 1 bp/ano de vol).

        Strike e Q fixos. A taxa spot move PU_0 e, portanto, o forward.
        """
        y = self.taxa_ref_pct if y_spot_pct is None else y_spot_pct
        k = self.strike_atm if strike_pct is None else strike_pct
        p = lambda yy, ss: self.premio(ss, k, yy)
        h = h_bp / 100
        p0, pu_, pd_ = p(y, sigma_bps), p(y + h, sigma_bps), p(y - h, sigma_bps)
        return {
            "premio": p0,
            "delta": (pu_ - pd_) / (2 * h_bp),
            "gamma": (pu_ - 2 * p0 + pd_) / h_bp ** 2,
            "vega": (p(y, sigma_bps + h_vol) - p(y, sigma_bps - h_vol)) / (2 * h_vol),
        }
