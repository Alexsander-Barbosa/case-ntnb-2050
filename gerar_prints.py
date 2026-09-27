"""Exporta os 5 gráficos (parâmetros padrão, Δ = −50 bp) para prints/*.png."""
from pathlib import Path

import app_figs as F
from quant import app_data as D

OUT = Path(__file__).parent / "prints"
OUT.mkdir(exist_ok=True)
cen, dl = D.construir_cenarios("B"), -50
figs = {
    "1_payoff": F.fig_payoff(D.dados_payoff(cen, dl), mostrar_absoluto=True),
    "2_convexidade": F.fig_preco_taxa(D.dados_preco_taxa(cen)),
    "3_heatmap": F.fig_heatmap(D.dados_heatmap(cen)),
    "4_waterfall": F.fig_waterfall(D.dados_waterfall(cen, dl), dl),
    "5_historico": F.fig_historico(D.dados_historico(cen)),
}
for nome, fig in figs.items():
    fig.write_image(OUT / f"{nome}.png", width=1300, height=fig.layout.height or 500, scale=1.4)
    print(OUT / f"{nome}.png")
