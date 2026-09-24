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

base_dir = os.path.join(os.getcwd(), 'gold_prices_dataset')
annual_path = os.path.join(base_dir, 'annual.csv')

with open(annual_path, "r", encoding="utf-8") as f:
    annual_raw_csv = f.read()

with open("jev_gold_dataset_audit_response.json", "r", encoding="utf-8") as f:
    audit_data = json.load(f)

state = f"""
IN-DEPTH MACRO AND QUANTITATIVE DATASET SYNTHESIS: GLOBAL GOLD PRICES (1833 - 2026)
Source: GitHub (datasets/gold-prices) | World Bank Pink Sheet (1960-2026) & Timothy Green Records (1833-1959).
193 Years of Annual Prices and 2,325 Monthly observations.
Key Milestones:
- 1833: $18.93 / oz
- 1934 (Gold Reserve Act): $35.00 / oz
- 1971 (Nixon Shock): $40.80 / oz
- 1980 (Stagflation peak): $612.56 / oz
- 1999-2001 (Bottom): $270.99 / oz
- 2011 (GFC peak): $1,569.21 / oz
- 2024-2026 (Modern era): $2,387 to >$4,400 / oz

Jev SystemOne Prior Decisions:
- Nature: MONETARY_DEBASEMENT_HEDGE (97.0% probability)
- Role vs Bitcoin: COMPLEMENTARY_DUAL_HEDGE (67.0% probability)
- Valuation Score: 3.05 / 5.00 (Fair Value / Structural Shift)
"""

client = TypeSafeClient()

questions = {
    "key_structural_takeaways": Choice(
        instructions="What is the single most important mathematical and macroeconomic insight an algorithmic quant trader should extract from this 193-year dataset?",
        criteria={
            "fiat_devaluation_monotonic_drift": "Monotonic Fiat Devaluation: Gold does not appreciate; rather, fiat currencies systematically devalue against hard physical scarcity at ~8-10% CAGR in post-peg expansion eras.",
            "volatility_clustering_during_regime_shifts": "Volatility Clustering: 90% of returns occur in violent multi-year re-pricing regimes (1970s, 2000s, 2020s), followed by lengthy decade-long consolidation drawdowns.",
            "inflation_hedge_lag": "Inflation Hedge Lag: Gold is an unreliable short-term (1-3 yr) inflation hedge, but an unyielding multi-decade purchasing power anchor."
        }
    ),
    "actionable_trading_model": Choice(
        instructions="Which algorithmic trading model is most mathematically appropriate when backtesting on this gold dataset?",
        criteria={
            "multi_month_trend_following": "Multi-Month Trend Following / Breakout (Donchian / Moving Average Crossover): Captures the multi-year sovereign supercycles while avoiding 10-year chop.",
            "mean_reversion_to_production_cost": "Mean Reversion: Exploits price exhaustion relative to all-in sustaining mining costs (AISC).",
            "cross_asset_lead_lag_with_crypto": "Cross-Asset Momentum: Using Gold macro breakouts as a confirmation filter for high-beta digital asset (Bitcoin) long positions."
        }
    )
}

print("[*] Consultando JEV para conclusões estruturais e modelos de trade...")
response = client.system_one(state=state, questions=questions)

ans1 = response.answers["key_structural_takeaways"]
ans2 = response.answers["actionable_trading_model"]

print("\n" + "=" * 90)
print(f"[+] Maior Insight Macroeconômico: {ans1.choice.upper()} ({ans1.confidence:.1%})")
for opt, prob in ans1.probabilities.items():
    print(f"    • {opt}: {prob:.1%}")

print(f"\n[+] Modelo Algorítmico Mais Adequado: {ans2.choice.upper()} ({ans2.confidence:.1%})")
for opt, prob in ans2.probabilities.items():
    print(f"    • {opt}: {prob:.1%}")

# Update json
audit_data["key_takeaway"] = ans1.choice
audit_data["actionable_model"] = ans2.choice
audit_data["model_probabilities"] = ans2.probabilities

with open("jev_gold_dataset_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(audit_data, f, indent=2)

print("\n[*] Concluído e salvo com sucesso!")
