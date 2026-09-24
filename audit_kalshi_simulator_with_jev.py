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

print("\n" + "=" * 90)
print("  🤖 CONSULTANDO IA JEV (TYPESAFE AI) SOBRE O SIMULADOR KALSHI NATURAL GAS & EIA")
print("=" * 90)

with open("kalshi_natgas_simulator_summary.json", "r", encoding="utf-8") as f:
    sim_data = json.load(f)

dossier = f"""
OFFICIAL ARCHITECTURE & RESULTS AUDIT: KALSHI QUANTITATIVE NATURAL GAS STORAGE & WEATHER SIMULATOR
Target Market: Kalshi Regulated Binary Options (Weekly EIA Storage Consensus Deviation).
Simulation Period: 13.8 continuous years (Jan 2013 to Sep 2026), 715 weekly Thursdays.
Dataset Inputs:
1. EIA Weekly Underground Natural Gas Storage Report (871 weeks, 2010-2026).
2. Henry Hub Spot Prices (30 years, 1997-2026).
3. Thermal Persistence Model: Exploiting 2-week meteorological momentum and population-weighted heating degree days (HDD) inertia against naive 5-year retail consensus.

SIMULATION RESULTS:
- Total Trades: {sim_data['total_trades']} weeks traded
- Wins / Losses: {sim_data['wins']} Wins / {sim_data['losses']} Losses
- Win Rate: {sim_data['win_rate_pct']}%
- Initial Capital: ${sim_data['initial_bankroll']:.2f} USD | Flat Stake: $25.00
- Net Profit: +${sim_data['net_profit_usd']:.2f} USD (+{sim_data['total_roi_pct']}%)
- Profit Factor: {sim_data['profit_factor']}
- Maximum Drawdown: {sim_data['max_drawdown_pct']}%
- Annualized Sharpe Ratio: {sim_data['annualized_sharpe_ratio']}
Execution Friction Modeled: 2 cents bid-ask spread per contract, hard $0.60 price cap, binary $1.00 settlement.
"""

client = TypeSafeClient()

questions = {
    "authenticity_of_eia_thermal_edge": Choice(
        instructions="Analyze whether this 68.4% win rate on EIA weekly storage deviation reflects a durable physical/meteorological market inefficiency or statistical overfitting.",
        criteria={
            "durable_thermodynamic_edge": "Durable Physical Edge: Retail prediction market participants rely on naive 5-year averages, whereas weather model inertia (NOAA HDD/CDD persistence) carries genuine predictive autocorrelation across 1-2 week horizons.",
            "spurious_overfitting": "Overfitting: The edge will disappear in live forward trading.",
            "unexecutable_due_to_liquidity": "Liquidity Constrained: The edge exists theoretically but Kalshi book depth on weekly EIA contracts is too thin to deploy capital."
        }
    ),
    "kalshi_execution_recommendation": Choice(
        instructions="What is the optimal timing window for entering this trade on Kalshi prior to the Thursday 10:30 AM ET official release?",
        criteria={
            "wednesday_afternoon_sweet_spot": "Wednesday Afternoon Sweet Spot (18-24h prior): Enter after NOAA 12z model cycle confirms weather forecasts, but before retail liquidity spikes on Thursday morning.",
            "thursday_morning_seconds_before": "Thursday Morning (Seconds prior): Wait until 10:29 AM to capture last-second order flow.",
            "monday_morning_early_bird": "Monday Morning: Enter early in the week to capture maximum price discount."
        }
    ),
    "strategy_robustness_score": Score(
        instructions="Rate the institutional robustness of this natural gas storage simulator strategy on a scale from 1 to 5.",
        criteria=[
            "Flawed / Unviable",
            "Weak / Fragile",
            "Moderate Academic Prototype",
            "Robust Quantitative Strategy",
            "Top-Tier Institutional Energy Desk Grade"
        ]
    ),
    "jev_confidence_level": Noul(
        instructions="State Jev's overall probabilistic confidence that this thermal inertia model on Kalshi will remain profitable over the upcoming 2026-2027 winter heating season."
    )
}

print("[*] Submetendo ao modelo Jev (SystemOne da TypeSafe AI)...")
t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta recebida do Jev em {elapsed:.1f}s!\n")

print("=" * 90)
print("  📊 RESULTADOS DA AUDITORIA DO JEV SOBRE O SIMULADOR KALSHI")
print("=" * 90)

q1 = response.answers["authenticity_of_eia_thermal_edge"]
print(f"\n[1] NATUREZA DO EDGE (INÉRCIA TÉRMICA DA EIA):")
print(f"  ▶ Veredito do Jev: {q1.choice.upper()}")
print(f"  ▶ Confiança: {q1.confidence:.1%}")
for opt, prob in q1.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q2 = response.answers["kalshi_execution_recommendation"]
print(f"\n[2] JANELA ÓTIMA DE EXECUÇÃO NA KALSHI:")
print(f"  ▶ Veredito do Jev: {q2.choice.upper()}")
print(f"  ▶ Confiança: {q2.confidence:.1%}")
for opt, prob in q2.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q2.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q3 = response.answers["strategy_robustness_score"]
print(f"\n[3] SCORE DE ROBUSTEZ INSTITUCIONAL:")
print(f"  ▶ Score do Jev: {q3.score:.2f} / 5.00")
print(f"  ▶ Confiança: {q3.confidence:.1%}")

q4 = response.answers["jev_advice_to_algorithmic_traders"] = response.answers["jev_confidence_level"]
print(f"\n[4] CONFIANÇA PROBABILÍSTICA DO JEV (PRÓXIMO INVERNO):")
print(f"  ▶ Noul do Jev: {q4.noul:.1%}")

# Salva arquivo JSON
output = {
    "timestamp": time.time(),
    "answers": {
        k: {
            "choice": getattr(v, "choice", None),
            "score": getattr(v, "score", None),
            "confidence": getattr(v, "confidence", None),
            "probabilities": getattr(v, "probabilities", None),
            "noul": getattr(v, "noul", None)
        }
        for k, v in response.answers.items()
    },
    "simulation_summary": sim_data
}

with open("jev_kalshi_simulator_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n[*] Auditoria completa salva em jev_kalshi_simulator_audit_response.json")
