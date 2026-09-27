# Regras para o Claude Code neste repositório

- quant/ e tests/ estão validados (160 testes, revisão independente). NÃO alterar a lógica financeira.
- Ajustes de apresentação vão em app_figs.py e app.py apenas.
- Toda premissa vem de quant/premissas.py; não criar números novos no app.
- Convenções: taxas em % a.a. base 252; choques em bp; queda de taxa = Δ negativo;
  P&L > 0 = ganho do cliente; sensibilidades exibidas como "ganho por bp de queda".
- Nomes: "TRS / asset swap sobre a NTN-B 2050" (nunca "swap DI × IPCA");
  a opção é "call sobre o PU (= put na taxa real)".
- Depois de qualquer mudança: python -m pytest -q deve continuar com 160 passed.
- Não fazer commit nem push sem pedir.