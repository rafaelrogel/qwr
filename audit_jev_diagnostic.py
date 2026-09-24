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

state = """
DEEP DIAGNOSTIC: JEV ASSESSMENT OF THE ANTIGRAVITY QUANT DESK
Context:
The previous JEV audit rated:
- SirMartingale Take-Profit: 98% DECISIVE_STRUCTURAL_EDGE
- Filter Discipline: 99% EXEMPLARY_INSTITUTIONAL_DISCIPLINE
- Multi-Desk Architecture Rating: 1.61 / 5.00
- Forward 100-cycle profitability probability: 39%

Current State:
1. Live Trading is currently active ONLY on Desk 1 (Polymarket BTC 5m) with $1.00 stakes (Wallet: $22.54 USDC, 137 trades, 70.8% WR).
2. Desk 2 (SOL 5m), Desk 3 (Kalshi 15m), and Desk 4 (NatGas EIA) are currently running in PAPER MODE (with live API connections).
3. The overnight session had only 4 trades executed out of ~120 5m cycles due to tight deadbands ($17.70) and price caps ($0.55).
"""

client = TypeSafeClient()

questions = {
    "primary_architectural_bottleneck": Choice(
        instructions="What is the primary reason why Jev rated the current multi-desk architecture at 1.61/5.00 despite strong execution mechanics?",
        criteria={
            "paper_mode_predominance": "Paper Mode Predominance: 3 out of 4 desks are still running in simulation/paper mode; institutional desks require production on-chain or exchange execution with real fill latency and slippage across all assets.",
            "small_sample_and_low_stake": "Small Sample & Low Stake: 4 trades over 10 hours and $1.00 position sizing makes statistical power low and sensitive to random drawdowns over the next 100 cycles.",
            "regime_shift_vulnerability": "Regime Shift Vulnerability: High 5m win rates (70%+) often experience mean-reversion during strong trending market regimes if volatility spikes."
        }
    ),
    "highest_priority_action_for_traders": Choice(
        instructions="What is the single most important actionable step the quant developers should take next to elevate the architecture score and long-term expectancy?",
        criteria={
            "gradual_live_rollout_sol_and_kalshi": "Gradual Live Rollout: Move Desk 2 (SOL 5m) and Desk 3 (Kalshi 15m) from Paper to minimal live capital ($10-$25) to validate live fills, orderbook latency, and multi-asset diversification.",
            "loosen_deadband_filters": "Loosen Deadband: Lower the deadband to capture more trades per hour and increase turnover.",
            "add_more_macro_assets": "Add More Macro Assets: Integrate traditional equities and commodities to broaden exposure."
        }
    ),
    "execution_engine_verdict": Score(
        instructions="Rate specifically the microsecond execution and protection engine of Desk 1 (Take-Profit early exit, Deadband, Safe 1271, Polygon gas management) on a scale from 1 to 5.",
        criteria=[
            "Unviable",
            "Basic Script",
            "Competent Retail Algo",
            "High-Grade Quantitative Execution",
            "Flawless Institutional Microstructure Engine"
        ]
    )
}

print("  🤖 CONSULTANDO DIAGNÓSTICO PROFUNDO DO JEV...")
response = client.system_one(state=state, questions=questions)

q1 = response.answers["primary_architectural_bottleneck"]
q2 = response.answers["highest_priority_action_for_traders"]
q3 = response.answers["execution_engine_verdict"]

print(f"\n[1] PRINCIPAL GARGALO APONTADO PELO JEV: {q1.choice.upper()} ({q1.confidence:.1%})")
for opt, prob in q1.probabilities.items():
    print(f"     • {opt}: {prob:.1%}")

print(f"\n[2] AÇÃO PRIORITÁRIA RECOMENDADA PELO JEV: {q2.choice.upper()} ({q2.confidence:.1%})")
for opt, prob in q2.probabilities.items():
    print(f"     • {opt}: {prob:.1%}")

print(f"\n[3] SCORE ESPECÍFICO DO MOTOR DE EXECUÇÃO DO DESK 1 (BTC LIVE): {q3.score:.2f} / 5.00 (Confiança: {q3.confidence:.1%})")

diag = {
    "bottleneck": q1.choice,
    "bottleneck_prob": q1.probabilities,
    "priority_action": q2.choice,
    "priority_action_prob": q2.probabilities,
    "desk1_engine_score": q3.score
}

with open("jev_diagnostic_details.json", "w", encoding="utf-8") as f:
    json.dump(diag, f, indent=2)
