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

with open("jev_vix_dataset_audit_response.json", "r", encoding="utf-8") as f:
    audit_data = json.load(f)

state = f"""
PREDICTION MARKET & QUANT ALGORITHMIC IMPLICATIONS OF THE 36-YEAR VIX DATASET (1990-2026)
Source: DataHub (core/finance-vix) | CBOE.
Key Empirical Parameters:
- Historical Mean: 19.43 | Median: 17.57 | Floor: 9.14 | Ceiling: 82.69
- Mean-Reversion Half-Life: 30.0 trading days.
- Calm Regimes (VIX < 15): 34.6% of history.
- Normal Regimes (15 <= VIX < 20): 43.8% of history.
- Elevated (20 <= VIX < 30): 15.6% of history.
- Panic (30 <= VIX < 40): 3.7% of history.
- Systemic Crash (VIX >= 40): 2.2% of history.

Context: Trader operates automated short-horizon binary prediction market bots (Polymarket BTC 5m sniper, Kalshi BTC 15m, Solana 5m paper).
"""

client = TypeSafeClient()

questions = {
    "vix_impact_on_binary_markets": Choice(
        instructions="How does an elevated TradFi volatility regime (VIX > 25) typically impact binary prediction markets (Polymarket / Kalshi) for crypto?",
        criteria={
            "spread_widening_and_mispricings": "Increased Spreads & Opportunity: Market makers widen quotes, resulting in wider spreads (>6c) but creating massive short-lived mispricings for directional snipers.",
            "untradeable_whipsaws": "Destructive Whipsaws: High volatility increases intra-candle reversal frequency, breaking momentum continuation assumptions.",
            "negligible_impact": "Negligible Impact: High-frequency crypto order books operate independently of equity VIX."
        }
    ),
    "golden_rule_for_trader_during_vix_spike": Choice(
        instructions="What is the single golden rule an algorithmic quantitative trader should follow when VIX exceeds 35 (Top 5% crisis regime)?",
        criteria={
            "tighten_spread_vetoes_and_reduce_size": "Defensive Calibration: Enforce strict CLOB spread filters (veto if spread > 6c) and reduce stake size by 50% to withstand liquidity vacuums.",
            "turn_off_all_bots": "Complete Shutdown: Cease all algorithmic execution until VIX mean-reverts below 25.",
            "increase_stake_size": "Aggressive Exploitation: Double stake size to exploit panicked retail market participants."
        }
    )
}

print("[*] Consultando JEV sobre o impacto do VIX nos mercados preditivos...")
response = client.system_one(state=state, questions=questions)

ans1 = response.answers["vix_impact_on_binary_markets"]
ans2 = response.answers["golden_rule_for_trader_during_vix_spike"]

print("\n" + "=" * 90)
print(f"[+] Impacto do VIX em Mercados Preditivos: {ans1.choice.upper()} ({ans1.confidence:.1%})")
for opt, prob in ans1.probabilities.items():
    print(f"    • {opt}: {prob:.1%}")

print(f"\n[+] Regra de Ouro em Picos de Pânico (VIX > 35): {ans2.choice.upper()} ({ans2.confidence:.1%})")
for opt, prob in ans2.probabilities.items():
    print(f"    • {opt}: {prob:.1%}")

audit_data["prediction_markets_impact"] = ans1.choice
audit_data["golden_rule"] = ans2.choice
audit_data["golden_rule_probabilities"] = ans2.probabilities

with open("jev_vix_dataset_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(audit_data, f, indent=2)

print("\n[*] Análise salva com sucesso!")
