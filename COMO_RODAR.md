# Como rodar

    pip install -r requirements.txt
    python -m pytest -q          # 160 testes (inclui o app de ponta a ponta via streamlit.testing)
    streamlit run app.py         # abre em http://localhost:8501

Prints dos gráficos (PNG, pasta prints/):

    python gerar_prints.py

Estrutura: quant/ (cálculo, testado) → quant/app_data.py (dados dos gráficos, testado)
→ app_figs.py (figuras Plotly, só apresentação) → app.py (layout e widgets).
