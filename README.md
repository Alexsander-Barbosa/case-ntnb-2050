# NTN-B 2050: três formas de expressar a queda da taxa real

Estrutura, marcação e comparação de três produtos para um cliente que quer se beneficiar
da queda da taxa real da NTN-B 2050 (vencimento 15/08/2050): compra direta do título,
TRS/asset swap pagando CDI e call europeia sobre o PU (= put na taxa real).

Data de referência: 25/09/2026. Horizonte: 28/12/2026 (62 DU). Notional: R$ 10 milhões.

## Como rodar
    pip install -r requirements.txt
    python -m pytest -q      # 160 testes
    streamlit run app.py

## Estrutura
- `quant/ntnb.py`: pricer da NTN-B pela metodologia do Tesouro (VNA, truncamentos, DV01, convexidade)
- `quant/calendar.py`: dias úteis pelo calendário ANBIMA
- `quant/curva_di.py`: curva DI x pré da B3 com interpolação flat forward 252
- `quant/swap.py`: TRS sobre a NTN-B 2050 (recebe o retorno do título, paga CDI)
- `quant/option.py`: call sobre o PU, com distribuição normal na taxa e ajuste de convexidade
- `quant/scenarios.py`: P&L no horizonte de −100 a +100 bp, em excesso ao CDI
- `quant/premissas.py`: todas as premissas, com fonte
- `app.py`: painel interativo (Streamlit + Plotly)

## Validação
- PU calculado contra o PU oficial do Tesouro Direto: backtest de 688 dias, erro máximo de R$ 0,009 por título
- VNA conferido por dois caminhos independentes (número-índice IPCA e implícito nos preços)
- DV01 e convexidade analíticos contra bump; TRS vale zero na contratação; put-call parity fecha
- Prêmio da opção conferido por Monte Carlo independente

## Principais resultados (σ = 70 bps/ano, strike ATM forward)
| Δ taxa real até 28/12 | NTN-B / TRS | Opção |
|---|---|---|
| −50 bp | +R$ 581 mil | +R$ 424 mil |
| 0 bp | −R$ 10 mil | −R$ 157 mil |
| +100 bp | −R$ 1,05 mi | −R$ 157 mil |

## Premissas e limitações
- Taxa de mercado: Taxa Venda do Tesouro Direto como proxy (indicativa ANBIMA a verificar)
- Vol da taxa real estimada do histórico em variações de 21 DU; não há mercado líquido de opções
- Margem do TRS (10%) é premissa ilustrativa, não dado de mercado
- Choques paralelos na taxa real; IPCA do horizonte pelo Focus; sem cupom dentro do horizonte

Fontes: Tesouro Nacional (metodologia e preços), B3 (curva DI x pré), BCB (CDI e Focus), ANBIMA (feriados), IBGE (IPCA).