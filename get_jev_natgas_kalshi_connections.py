import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

from dotenv import load_dotenv; load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

with open("jev_natgas_dataset_audit_response.json", "r", encoding="utf-8") as f:
    audit_data = json.load(f)

state = f"""
EVENT DRIVEN & KALSHI PREDICTION MARKET IMPLICATIONS: 30-YEAR NATURAL GAS DATASET (1997-2026)
Source: DataHub (core/natural-gas) | EIA Henry Hub.
Empirical Findings:
- Historical Mean: $3.88/MMBtu | Median: $3.20 | Min: $1.21 | Max: $30.72
- Extreme Kurtosis: 12.01 (Heavy fat tails, explosive asymmetric shocks).
- Regimes:
  * Pre-Shale (1997-2008): Mean $5.49
  * Shale Glut (2009-2020): Mean $3.03 (Fracking deflation floor)
  * LNG Globalized (2021-2026): Mean $3.68 (European export arbitrage)
- Seasonality:
  * Highest: Dec-Feb ($4.30-$4.60/MMBtu)
  * Summer Burn: Jul-Aug ($3.80-$3.95/MMBtu)
  * Shoulder Troughs: Apr-May ($3.30-$3.45/MMBtu)

Context: Trader operates quantitative algorithmic prediction market engines on Kalshi and Polymarket. Kalshi offers EIA Storage and Henry Hub price milestone contracts.
"""

client = TypeSafeClient()

questions = {
    "kalshi_eia_storage_edge": Choice(
        instructions="How can an algorithmic trader exploit binary prediction markets (such as Kalshi EIA Storage and Natural Gas settlement contracts) using this dataset?",
        criteria={
            "weather_forecast_arbitrage": "Weather & Degree-Day Arbitrage: Anticipating EIA storage inventory withdrawals by tracking NOAA Heating Degree Days (HDD) models ahead of weekly EIA releases.",
            "naive_momentum": "Naive Price Momentum: Betting that price direction continues regardless of physical storage levels.",
            "unexploitable": "Unexploitable: Market makers price EIA inventory deviations with zero slippage."
        }
    ),
    "the_widowmaker_lesson": Choice(
        instructions="What is the foundational risk lesson of the 'Widowmaker' reputation in Natural Gas for algorithmic quantitative traders?",
        criteria={
            "physical_delivery_and_storage_inelasticity": "Physical Inelasticity: Unlike financial or crypto assets, natural gas cannot be digitally duplicated or easily stored without pipeline bottleneck; when storage capacity fills or freezes, spot price elasticity goes to infinity.",
            "exchange_counterparty_risk": "Exchange Risk: Futures exchanges frequently alter margin rules arbitrarily.",
            "pure_whale_manipulation": "Whale Manipulation: Hedge funds unilaterally control the settlement price."
        }
    )
}

print("[*] Consultando JEV sobre conexões com a Kalshi e lições de risco...")
response = client.system_one(state=state, questions=questions)

ans1 = response.answers["kalshi_eia_storage_edge"]
ans2 = response.answers["the_widowmaker_lesson"]

print("\n" + "=" * 90)
print(f"[+] Edge em Mercados Preditivos (Kalshi EIA): {ans1.choice.upper()} ({ans1.confidence:.1%})")
for opt, prob in ans1.probabilities.items():
    print(f"    • {opt}: {prob:.1%}")

print(f"\n[+] Lição de Risco do 'Widowmaker': {ans2.choice.upper()} ({ans2.confidence:.1%})")
for opt, prob in ans2.probabilities.items():
    print(f"    • {opt}: {prob:.1%}")

audit_data["kalshi_edge"] = ans1.choice
audit_data["widowmaker_lesson"] = ans2.choice

with open("jev_natgas_dataset_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(audit_data, f, indent=2)

print("\n[*] Análise completa de Gás Natural salva com sucesso!")
