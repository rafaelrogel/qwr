import os
from dotenv import load_dotenv
load_dotenv()
from typesafe_sdk import TypeSafeClient, Choice

client = TypeSafeClient()

dossier = """
Temos exatamente $34.49 USD de saldo restante na Databento.
Já temos baixados:
  - 1 Ano de OHLCV-1s em Natural Gas (NG.c.0)
  - 3 Meses de TBBO em Natural Gas (NG.c.0)
  - 1 Ano de OHLCV-1s em E-mini S&P 500 (ES.c.0)
  - 1 Mês de TBBO em E-mini S&P 500 (ES.c.0)
  - 1 Ano de OHLCV-1s em COMEX Gold (GC.c.0)
  - 1 Ano de OHLCV-1s em CME Micro Bitcoin (MBT.c.0)

Candidatos para queimar os $34.49 restantes:
Opção A (Foco em Commodities e Desk 5 LIVE):
  - GC TBBO (1 Ano Completo de Ouro): $0.09
  - NG TBBO (1 Ano Completo de Natural Gas - cobre todas as 52 divulgações da EIA de 2025/2026): $24.26
  - MBT TBBO (6 Meses de Micro Bitcoin): $5.84
  Total: $30.19 USD (Sobra $4.30)

Opção B (Foco em Tech / Nasdaq 100 - Modelo Chris Creamer para Kalshi KXNDX15M):
  - GC TBBO (1 Ano Completo de Ouro): $0.09
  - NQ OHLCV-1s (6 Meses de Nasdaq 100 Futuro): $24.52
  - MBT TBBO (6 Meses de Micro Bitcoin): $5.84
  Total: $30.45 USD (Sobra $4.04)

Opção C (Foco Macro em Energia WTI Crude Oil):
  - GC TBBO (1 Ano Completo de Ouro): $0.09
  - CL OHLCV-1s (1 Ano Completo de Petróleo WTI): $24.35
  - MBT TBBO (6 Meses de Micro Bitcoin): $5.84
  Total: $30.28 USD (Sobra $4.21)
"""

questions = {
    "optimal_remaining_burn_combo": Choice(
        instructions="Which combination of datasets extracts the highest statistical alpha for our existing trading fleet to burn the remaining $34.49 USD of Databento credits?",
        criteria={
            "combo_a_natgas_52_eia": "Combo A (NatGas 1 Year Full TBBO + Gold 1 Year TBBO + BTC TBBO): Maximizes the statistical depth for Desk 5 (which trades REAL MONEY) by capturing all 52 weekly EIA inventory shock releases at nanosecond trade-BBO precision, plus 1 year of gold order flow.",
            "combo_b_nasdaq_creamer": "Combo B (Nasdaq 100 1-sec + Gold TBBO + BTC TBBO): Expands our universe into tech/Nasdaq, enabling Chris Creamer's model and Kalshi KXNDX15M cross-correlation.",
            "combo_c_wti_crude_oil": "Combo C (WTI Crude Oil 1 Year + Gold TBBO + BTC TBBO): Adds the oil-gas crack and energy macro cointegration."
        }
    )
}

res = client.system_one(state=dossier, questions=questions)
q = res.answers["optimal_remaining_burn_combo"]
print(f"JEV Verdict: {q.choice.upper()} (Confidence: {q.confidence:.1%})")
for k, v in q.probabilities.items():
    print(f"  - {k}: {v:.1%}")
