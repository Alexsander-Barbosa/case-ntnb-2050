"""Case 2 — Itaú BBA: exposição à queda da taxa real da NTN-B 2050.

Somente layout e widgets. Todos os números vêm de quant/ (testados com pytest).
Rodar:  streamlit run app.py
"""
import streamlit as st

import app_figs as F
from quant import app_data as D
from quant import premissas as P

st.set_page_config(page_title="NTN-B 2050 — três estruturas", layout="wide")


# ------------------------------------------------------------------ cache (chave = parâmetros)
@st.cache_resource(show_spinner="Calculando cenários…")
def cenarios(curva, sigma, strike, margem, notional):
    return D.construir_cenarios(curva, sigma, strike, margem, notional)


@st.cache_data(show_spinner=False)
def atm_forward(curva):
    return cenarios(curva, P.VOL_TAXA_REAL_BASE_BPS, None, P.MARGEM_TRS_PCT_NOTIONAL, P.NOTIONAL_PADRAO).strike


# ------------------------------------------------------------------ barra lateral
sb = st.sidebar
sb.header("Parâmetros")
delta = sb.slider("Cenário: Δ taxa real até 28/12/2026 (bp)", -100, 100, -50, 5,
                  help="Negativo = queda da taxa real (a visão do cliente).")
modo_vol = sb.radio("Vol da taxa real (bps/ano)", ["Base (70)", "Estresse (100)", "Livre"], horizontal=True)
sigma = {"Base (70)": P.VOL_TAXA_REAL_BASE_BPS, "Estresse (100)": P.VOL_TAXA_REAL_ESTRESSE_BPS}.get(modo_vol)
if sigma is None:
    sigma = sb.number_input("σ livre (bps/ano)", 10.0, 250.0, 70.0, 5.0)
curva = sb.radio("Curva de CDI", ["B", "A"], format_func=D.CURVAS.get)
atm = atm_forward(curva)
usar_atm = sb.checkbox(f"Strike ATM forward ({D.fmt_num(atm, 4)}%)", value=True)
strike = None if usar_atm else sb.number_input("Strike (taxa real, % a.a.)", 6.00, 9.00, round(atm, 2), 0.05,
                                               format="%.2f", help="Call no PU exerce se a taxa em 28/12 < strike.")
margem = sb.slider("Margem do TRS (% do notional) — PREMISSA ILUSTRATIVA", 5, 30,
                   int(round(P.MARGEM_TRS_PCT_NOTIONAL * 100)), 1) / 100
notional = sb.number_input("Notional (R$)", 1_000_000, 100_000_000, int(P.NOTIONAL_PADRAO), 1_000_000, format="%d")
mostrar_abs = sb.checkbox("Mostrar NTN-B absoluta (sem descontar o CDI)", value=False)

cen = cenarios(curva, float(sigma), strike, margem, float(notional))
r = D.resumo(cen)

# ------------------------------------------------------------------ cabeçalho
st.title("Queda da taxa real da NTN-B 2050: três formas de expressar a mesma visão")
# "$" é delimitador de LaTeX no markdown do Streamlit: escapar os de "R$"
st.caption((f"Data de referência 25/09/2026 · horizonte 28/12/2026 ({r['du_horizonte']} DU) · "
            f"notional {D.fmt_brl(notional)} · curva {D.CURVAS[curva]} · σ = {D.fmt_num(sigma, 0)} bps/ano · "
            "P&L > 0 = ganho do cliente; valores em R$ no horizonte, **em excesso ao CDI**.").replace("$", "\\$"))
c = st.columns(5)
c[0].metric("Taxa real spot", f"{D.fmt_num(r['taxa_spot'])}%")
# delta com hífen ASCII: com "−" (U+2212) o Streamlit não reconhece o sinal e desenha a seta para cima
c[1].metric("Taxa real forward (28/12)", f"{D.fmt_num(r['taxa_forward'], 3)}%",
            f"{D.fmt_num((r['taxa_forward'] - r['taxa_spot']) * 100, 2).replace('−', '-')} bp", delta_color="off")
c[2].metric("Ganho por bp de queda (NTN-B/TRS)", D.fmt_brl(r["dv01"]))
c[3].metric("Carry do TRS até 28/12", D.fmt_brl(r["carry_trs"]))
c[4].metric("Prêmio da opção (hoje)", D.fmt_brl(r["premio"]))
st.warning("**Premissa ilustrativa:** margem do TRS "
           f"({D.fmt_num(margem * 100, 0)}% do notional) não é dado de mercado. "
           "Vol, IPCA e CDI do horizonte são premissas com fonte — ver o painel *Premissas e fontes*.", icon="⚠️")

# ------------------------------------------------------------------ 1. payoff
st.plotly_chart(F.fig_payoff(D.dados_payoff(cen, delta), mostrar_abs), width="stretch")

# ------------------------------------------------------------------ 2. convexidade
st.plotly_chart(F.fig_preco_taxa(D.dados_preco_taxa(cen)), width="stretch")

# ------------------------------------------------------------------ 3. heatmap + métricas
st.plotly_chart(F.fig_heatmap(D.dados_heatmap(cen)), width="stretch")
st.dataframe(D.tabela_metricas(cen), hide_index=True, width="stretch")
st.caption("NTN-B e TRS têm o mesmo P&L em excesso ao CDI (o TRS é a NTN-B financiada a CDI); diferem no capital. "
           "Swap DI×IPCA padrão B3 e DAP são bullet: a comparação entre estruturas é por DV01, não por notional.")

# ------------------------------------------------------------------ 4. waterfall
st.plotly_chart(F.fig_waterfall(D.dados_waterfall(cen, delta), delta), width="stretch")

# ------------------------------------------------------------------ 5. histórico
st.plotly_chart(F.fig_historico(D.dados_historico(cen)), width="stretch")
st.caption("Série Taxa Venda Manhã do Tesouro Direto (varejo). Vol medida em variações de 21 DU: "
           "a vol diária (≈106 bps/ano) superestima o risco em 3 meses por autocorrelação negativa.")

# ------------------------------------------------------------------ premissas
with st.expander("Premissas e fontes", expanded=False):
    tp = D.tabela_premissas()
    st.dataframe(tp.style.apply(lambda s: ["background-color: #fff3cd" if "ILUSTRATIVA" in str(v) else ""
                                           for v in s], subset=["tipo"]),
                 hide_index=True, width="stretch")
