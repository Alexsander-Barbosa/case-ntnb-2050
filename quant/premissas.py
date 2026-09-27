"""Premissas de mercado do Case 2 (fonte única; valores com procedência).

Qualquer mudança aqui deve ser registrada no 00_decisoes.md.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

DATA_REF = date(2026, 9, 25)
HORIZONTE_PADRAO = date(2026, 12, 28)   # 62 DU (25/12 é feriado)
NOTIONAL_PADRAO = 10_000_000.0

# CDI do dia, % a.a. base 252 — BCB/SGS 4389, referência 24/09/2026 (último disponível;
# sem Copom entre 24 e 25/09).
CDI_DIA_PCT = 13.65

# Curva DI x pré — B3 "Taxas referenciais", 25/09/2026, 74 vértices, taxas em 2 casas.
CURVA_DI_CSV = Path(__file__).resolve().parent.parent / "data" / "curva_di_pre_b3_2026-09-25.csv"

# Taxa real da NTN-B 2050 em 25/09/2026 — Tesouro Direto, Taxa Venda Manhã (proxy de mercado).
TAXA_REAL_REF_PCT = 7.38

# Número-índice IPCA ago/2026 (base dez/93=100) — fornecido; a conferir na SIDRA 1737.
# VNA 15/09/2026 = 1000 * 7633,23 / 1614,62 = 4.727,570573.
IDX_IPCA_AGO_2026 = Decimal("7633.23")

# IPCA mensal projetado (% a.m.) — Focus/BCB de 18/09/2026 (publicado 21/09/2026), medianas.
# dez/2026 derivado: IPCA 2026 Focus 4,92% ÷ acumulado jan–ago/2026 3,11% (IBGE) ÷ set–nov
# do Focus (acumulado jan–ago a conferir na SIDRA).
# Chave (ano, mês) = mês de REFERÊNCIA do IPCA; ele corrige o VNA de 15/(m) a 15/(m+1).
IPCA_FOCUS_PCT = {
    (2026, 9): Decimal("0.52"),
    (2026, 10): Decimal("0.33"),
    (2026, 11): Decimal("0.35"),
    (2026, 12): Decimal("0.54"),
}

# IPCA usado no ENCADEAMENTO do VNA até o horizonte (decisão 26/09, Achado 2, opção a):
# set/2026 = 0,56% — projeção já embutida no preço/VNA de 25/09 (implícita no Tesouro Direto,
# via projeção ANBIMA; a confirmar). Out–dez = Focus. Sem isso, o carry absorveria ≈ −R$ 4,1 mil
# que não são carry (revisão da projeção de setembro). IPCA_FOCUS_PCT permanece o dado bruto.
IPCA_SET_2026_EMBUTIDO_PCT = Decimal("0.56")
IPCA_HORIZONTE_PCT = {**IPCA_FOCUS_PCT, (2026, 9): IPCA_SET_2026_EMBUTIDO_PCT}

# Vol da taxa real NTN-B 2050 (bps/ano), série Taxa Venda Manhã do TD (decisão 26/09, Chat 99).
# Base = 70: desvio de variações de 21 DU (sobrepostas) no regime desde 26/12/2023, anualizado
#   por √(252/21) — escala coerente com a opção de 3 meses (32 obs. não sobrepostas, erro ≈ ±12%).
# Estresse = 100: mesma medida (21 DU) na série completa 2012–2026 (inclui 2013, 2015, 2020).
# NÃO usar a vol diária (106 / 125): autocorrelação diária ≈ −0,22 (provável artefato do retrato
#   de varejo, 1 cotação/manhã) superestima a variância no horizonte (razão de variâncias 21 DU ≈ 0,44).
VOL_TAXA_REAL_BASE_BPS = 70.0
VOL_TAXA_REAL_ESTRESSE_BPS = 100.0

# VNA da NTN-B em 25/09/2026 (liquidação D+0) — implícito: mediana de PU/cotação das outras
# NTN-Bs do dia (lado Venda, TD). Conferido pelo número-índice (4.736,378949; dif. R$ 0,004).
VNA_REF = 4736.374859

# PREMISSA ILUSTRATIVA (não é dado de mercado): margem/garantia do TRS como % do notional.
# 10% ≈ perda de um choque de ~+95 bp na taxa real (DV01 ≈ R$ 11,2 mil/bp em R$ 10 mi).
# A verificar com a mesa / metodologia de margem da B3 (CORE) antes de uso real.
MARGEM_TRS_PCT_NOTIONAL = 0.10
