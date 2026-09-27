"""Figuras Plotly do app — apenas apresentação (dados vêm de quant.app_data)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quant.app_data import NOMES, fmt_brl, fmt_num

AZUL, LARANJA, CINZA, VERDE, VERMELHO = "#1f4e79", "#e8731a", "#7f7f7f", "#2e7d32", "#c62828"
_LAYOUT = dict(template="plotly_white", font=dict(size=13), margin=dict(l=60, r=30, t=70, b=55),
               separators=",.")


def _mil(v):
    return f"{fmt_num(v / 1e3, 0)} mil"


def fig_payoff(d: dict, mostrar_absoluto: bool = False) -> go.Figure:
    L, V, BE, C = d["linhas"], d["verticais"], d["break_evens"], d["cenario"]
    f = go.Figure()
    f.add_trace(go.Scatter(x=L.taxa_H_pct, y=L.ntnb_trs, name=f"NTN-B = TRS (idênticos em excesso ao CDI)",
                           line=dict(color=AZUL, width=3),
                           hovertemplate="taxa %{x:.2f}%<br>P&L R$ %{y:,.0f}<extra>NTN-B/TRS</extra>"))
    f.add_trace(go.Scatter(x=L.taxa_H_pct, y=L.opcao, name=NOMES["Opção"], line=dict(color=LARANJA, width=3),
                           hovertemplate="taxa %{x:.2f}%<br>P&L R$ %{y:,.0f}<extra>Opção</extra>"))
    if mostrar_absoluto:
        f.add_trace(go.Scatter(x=L.taxa_H_pct, y=L.ntnb_absoluto, name="NTN-B absoluta (sem descontar CDI)",
                               line=dict(color=AZUL, width=1.5, dash="dash")))
    f.add_hline(y=0, line=dict(color="black", width=1))
    rotulos = [("spot", f"spot {fmt_num(V['spot'])}%", CINZA, "top left", "dot"),
               ("forward", f"forward {fmt_num(V['forward'], 3)}%"
                + (" = strike ATM" if abs(V["strike"] - V["forward"]) <= 1e-6 else ""), AZUL, "bottom right", "dot"),
               ("cenario", f"cenário {fmt_num(V['cenario'])}%", VERDE, "top right", "dash")]
    for k, txt, cor, pos, dash in rotulos:
        f.add_vline(x=V[k], line=dict(color=cor, dash=dash, width=1.5), annotation_text=txt,
                    annotation_position=pos, annotation_font_color=cor)
    if abs(V["strike"] - V["forward"]) > 1e-6:
        f.add_vline(x=V["strike"], line=dict(color=LARANJA, dash="dot", width=1.5),
                    annotation_text=f"strike {fmt_num(V['strike'], 3)}%", annotation_position="bottom left",
                    annotation_font_color=LARANJA)
    for nome, cor in (("TRS", AZUL), ("Opção", LARANJA)):
        b = BE[nome]
        f.add_trace(go.Scatter(x=[b["taxa"]], y=[0], mode="markers+text", marker=dict(size=11, color=cor, symbol="x"),
                               text=[f"BE {fmt_num(b['delta_bps'], 1)} bp"], textposition="top center",
                               textfont=dict(color=cor), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=[V["cenario"]] * 2, y=[C["ntnb_trs"], C["opcao"]], mode="markers",
                           marker=dict(size=10, color=[AZUL, LARANJA], line=dict(color="black", width=1)),
                           showlegend=False,
                           hovertext=[f"NTN-B/TRS {fmt_brl(C['ntnb_trs'])}", f"Opção {fmt_brl(C['opcao'])}"],
                           hoverinfo="text"))
    f.update_layout(**_LAYOUT, title=f"1. P&L em 28/12/2026 × taxa real no horizonte (R$, em excesso ao CDI)",
                    xaxis_title="Taxa real da NTN-B 2050 em 28/12/2026 (% a.a.)  ← queda de taxa = ganho",
                    yaxis_title="P&L (R$)", legend=dict(orientation="h", y=-0.22), height=520)
    f.update_yaxes(tickformat=",.0f")
    return f


def fig_preco_taxa(d: dict) -> go.Figure:
    c, p, s = d["curva"], d["ponto"], d["sens"]
    f = go.Figure()
    f.add_trace(go.Scatter(x=c.taxa_pct, y=c.tangente, name=f"Tangente (duration mod. {fmt_num(s['duration_modificada'])})",
                           line=dict(color=CINZA, dash="dash", width=2)))
    f.add_trace(go.Scatter(x=c.taxa_pct, y=c.pu, name="PU da NTN-B 2050 (hoje)", line=dict(color=AZUL, width=3),
                           fill="tonexty", fillcolor="rgba(46,125,50,0.15)"))
    f.add_trace(go.Scatter(x=[p["taxa"]], y=[p["pu"]], mode="markers+text", marker=dict(size=11, color="black"),
                           text=[f"  7,38% → {fmt_brl(p['pu'], 2)}"], textposition="middle right", showlegend=False))
    x0 = c.taxa_pct.iloc[4]
    f.add_annotation(x=x0, y=(c.pu.iloc[4] + c.tangente.iloc[4]) / 2, ax=6.1, ay=float(c.pu.max()) * 1.0,
                     axref="x", ayref="y", showarrow=True, arrowhead=2, align="left", xanchor="left",
                     text=f"Convexidade: em {fmt_num(c.taxa_pct.iloc[0], 1)}% ({fmt_num((c.taxa_pct.iloc[0] - p['taxa']) * 100, 0)} bp)"
                          f"<br>o PU fica {fmt_brl(c.convexidade.iloc[0], 0)}/título acima da tangente"
                          "<br>→ ganha mais na queda do que perde na alta")
    f.update_layout(**_LAYOUT, title=f"2. PU × taxa real hoje — DV01 {fmt_brl(s['dv01_titulo'], 3)}/título/bp, "
                                     f"convexidade {fmt_num(s['convexidade'], 1)}",
                    xaxis_title="Taxa real (% a.a.)", yaxis_title="PU (R$ por título)",
                    legend=dict(orientation="h", y=-0.2), height=500)
    f.update_yaxes(tickformat=",.0f")
    return f


def fig_heatmap(m) -> go.Figure:
    z = m.values
    txt = [[_mil(v) for v in row] for row in z]
    f = go.Figure(go.Heatmap(z=z, x=[f"{c:+d} bp" if c else "0 bp" for c in m.columns],
                             y=[NOMES[e].replace(" (", "<br>(") for e in m.index],
                             text=txt, texttemplate="%{text}", colorscale="RdYlGn", zmid=0,
                             colorbar=dict(title="R$"), hovertemplate="%{y}<br>Δ %{x}: R$ %{z:,.0f}<extra></extra>"))
    f.update_layout(**_LAYOUT, title="3. P&L em 28/12/2026 por cenário de Δ taxa real (R$, em excesso ao CDI)",
                    xaxis_title="Δ taxa real até 28/12 (bp)  ← queda | alta →", height=360)
    f.update_yaxes(autorange="reversed")
    return f


def fig_waterfall(d: dict, delta_bps: float) -> go.Figure:
    f = make_subplots(rows=1, cols=2, column_widths=[0.62, 0.38], horizontal_spacing=0.08,
                      subplot_titles=(NOMES["TRS"], NOMES["Opção"]))
    for col, k in ((1, "TRS"), (2, "Opção")):
        t = d[k]
        f.add_trace(go.Waterfall(x=t.item, y=t.valor, measure=t.medida, text=[_mil(v) for v in t.valor],
                                 textposition="outside", increasing=dict(marker_color=VERDE),
                                 decreasing=dict(marker_color=VERMELHO), totals=dict(marker_color=AZUL),
                                 showlegend=False), row=1, col=col)
    f.update_layout(**_LAYOUT, title=f"4. Decomposição do P&L no cenário Δ = {fmt_num(delta_bps, 0)} bp (R$, em 28/12/2026)",
                    height=520)
    f.update_yaxes(tickformat=",.0f")
    return f


def fig_historico(d: dict) -> go.Figure:
    s, L = d["serie"], d["leque"]
    f = go.Figure()
    f.add_trace(go.Scatter(x=s.data, y=s.taxa_venda, name="Taxa Venda (TD, manhã)", line=dict(color=AZUL, width=1.5)))
    f.add_trace(go.Scatter(x=L.data, y=L.sup, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=L.data, y=L.inf, fill="tonexty", fillcolor="rgba(232,115,26,0.30)", line=dict(width=0),
                           name=f"±1σ até 28/12 (σ = {fmt_num(d['sigma_bps'], 0)} bps/ano → ±{fmt_num(d['um_sigma_horizonte_bps'], 0)} bp)"))
    # add_vline com anotação falha em eixo de datas (bug do Plotly): shape + annotation separados
    f.add_shape(type="line", x0=d["quebra"], x1=d["quebra"], y0=0, y1=1, yref="paper",
                line=dict(color=CINZA, dash="dot"))
    f.add_annotation(x=d["quebra"], y=1, yref="paper", text="regime atual (26/12/2023)", showarrow=False,
                     xanchor="right", yanchor="bottom", font=dict(color=CINZA))
    fim = L.data.iloc[-1]
    f.add_annotation(x=fim, y=L.sup.iloc[-1], text=f"{fmt_num(L.sup.iloc[-1])}%", showarrow=False, xanchor="left")
    f.add_annotation(x=fim, y=L.inf.iloc[-1], text=f"{fmt_num(L.inf.iloc[-1])}%", showarrow=False, xanchor="left")
    f.update_layout(**_LAYOUT, title="5. Histórico da taxa real da NTN-B 2050 e faixa de ±1σ para o horizonte",
                    yaxis_title="Taxa real (% a.a.)", legend=dict(orientation="h", y=-0.15), height=480)
    f.update_xaxes(range=["2024-01-01", (fim + pd.Timedelta(days=45)).strftime("%Y-%m-%d")],
                   rangeselector=dict(buttons=[dict(count=1, label="1 ano", step="year", stepmode="backward"),
                                               dict(count=3, label="3 anos", step="year", stepmode="backward"),
                                               dict(step="all", label="desde 2012")]))
    f.update_yaxes(range=[5.0, 8.3])
    return f
