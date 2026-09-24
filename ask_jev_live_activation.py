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
FEASIBILITY & RISK AUDIT: ACTIVATING DESK 2 (POLYMARKET SOL 5M) AND DESK 3 (KALSHI BTC 15M) TO REAL MONEY (LIVE MODE)

Context & Current Balances:
1. Current Live Status:
   - Desk 1 (Polymarket BTC 5m): LIVE on Polygon. Real wallet balance: $22.54 USDC (up from $21.00 initial deposit). Lifetime: 97W / 40L (70.8% Win Rate, 137 on-chain trades).
   - Desk 2 (Polymarket SOL 5m): Currently in PAPER mode consuming real CLOB L2 data. Paper balance: $29.65 USD (3W / 0L, 100% WR). Over the last 10 hours, 100% of ~110 cycles were cleanly filtered by Deadband (5 bps / $0.06), Jev Trend Continuation, and $0.55 Price Cap.
   - Desk 3 (Kalshi BTC 15m): Currently in PAPER mode with real authenticated RSA-PSS API. Real account balance on Kalshi: $10.36 USD. Paper balance: $35.91 USD (2W / 0L, 100% WR). Evaluated at 450s midpoint.

2. Technical Readiness Analysis:
   - Desk 2 (Polymarket SOL): The bot sol_trader_5m.py currently has hyper-realistic paper taker-fill logic on the real CLOB orderbook. To go live, it needs the ClobClient V2 signing integration (derived from live_trader_5m.py) to place real on-chain orders using the shared $22.54 USDC bankroll ($1.00 fixed stake).
   - Desk 3 (Kalshi BTC 15m): The bot kalshi_trader_15m.py already has KalshiClient RSA-PSS authentication and place_order() implemented for 1 contract (~$0.45 - $0.55 stake). Real account balance is $10.36 USD (~20 trades of 1 contract).

3. Proposal from User:
   "Can we now activate Desk 2 (SOL 5m) and Desk 3 (Kalshi 15m) in real mode?"
"""

client = TypeSafeClient()

questions = {
    "live_activation_verdict": Choice(
        instructions="Should the traders activate Desk 2 (Polymarket SOL 5m) and Desk 3 (Kalshi BTC 15m) to real money (LIVE mode) now?",
        criteria={
            "approved_staged_rollout": "APPROVED WITH STAGED ROLLOUT: Yes, approve activation with strict staged deployment (first Kalshi 15m with 1 contract ~$0.50, then SOL 5m with $1.00 stake), keeping maximum micro-stakes to preserve bankroll.",
            "approved_simultaneous_activation": "APPROVED SIMULTANEOUS: Activate both Desk 2 and Desk 3 immediately in live mode at $1.00 / 1 contract.",
            "premature_keep_paper": "PREMATURE: Keep both in paper mode for another 24-48 hours until more paper trades trigger.",
            "reject_kalshi_only_sol": "PARTIAL APPROVAL: Activate only Polymarket SOL 5m and keep Kalshi in paper mode."
        }
    ),
    "kalshi_real_readiness": Choice(
        instructions="Evaluate Kalshi 15m readiness with an authenticated $10.36 USD balance and 1-contract sizing (~$0.50 risk per trade).",
        criteria={
            "ready_for_micro_live": "Ready for Micro-Live: With 1-contract sizing ($0.45-$0.55 risk), $10.36 represents ~20 units of risk capital. With Jev 5.0 bps deadband and 450s decision filter, risk of ruin is minimal.",
            "insufficient_capital": "Insufficient Capital: $10.36 is too small to trade live on Kalshi; deposit more capital first.",
            "untested_execution": "Untested Execution: Test paper mode longer."
        }
    ),
    "polymarket_sol_shared_wallet_risk": Choice(
        instructions="Evaluate the risk of Desk 1 (BTC 5m) and Desk 2 (SOL 5m) sharing the same Polymarket Funder wallet ($22.54 USDC balance) at $1.00 flat stakes.",
        criteria={
            "manageable_with_strict_sizing": "Manageable Risk: Maximum concurrent exposure is $2.00 (under 9% of the $22.54 balance). Non-correlated 5m volatility between BTC and SOL provides natural diversification.",
            "high_concurrency_risk": "High Concurrency Risk: Two bots sharing a single wallet could cause nonce collisions or race conditions on Polygon.",
            "insufficient_cushion": "Insufficient Cushion: Need at least $50 USDC before running two bots on the same wallet."
        }
    ),
    "overall_live_go_confidence": Noul(
        instructions="State Jev's overall probabilistic confidence that activating micro-stake live trading ($0.50-$1.00) on Desk 2 and Desk 3 will result in positive expected value (+EV) and capital preservation over the next 50 trades."
    ),
    "implementation_prerequisite_score": Score(
        instructions="Rate the necessity of code verification (verifying live ClobClient for SOL and Kalshi sell execution) before flipping the live switch from 1 (unnecessary) to 5 (vital prerequisite).",
        criteria=[
            "Unnecessary",
            "Low Priority",
            "Recommended",
            "Crucial Prerequisite",
            "Mandatory Strict Gatekeeper"
        ]
    )
}

print("\n" + "=" * 90)
print("  🤖 CONSULTANDO IA JEV SOBRE A ATIVAÇÃO DO MODO REAL NOS DESKS 2 E 3...")
print("=" * 90)

t0 = time.time()
response = client.system_one(state=state, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Resposta do Jev recebida em {elapsed:.1f}s!\n")

q1 = response.answers["live_activation_verdict"]
q2 = response.answers["kalshi_real_readiness"]
q3 = response.answers["polymarket_sol_shared_wallet_risk"]
q4 = response.answers["overall_live_go_confidence"]
q5 = response.answers["implementation_prerequisite_score"]

print("=" * 90)
print("  📊 PARECER DO JEV SOBRE ATIVAÇÃO DO MODO REAL (DESK 2 & 3)")
print("=" * 90)

print(f"\n[1] VEREDITO DE ATIVAÇÃO LIVE: {q1.choice.upper()} (Confiança: {q1.confidence:.1%})")
for opt, prob in q1.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

print(f"\n[2] PRONTIDÃO DA KALSHI (DESK 3): {q2.choice.upper()} (Confiança: {q2.confidence:.1%})")
for opt, prob in q2.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q2.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

print(f"\n[3] RISCO DE CARTEIRA COMPARTILHADA BTC + SOL (DESK 1 & 2): {q3.choice.upper()} (Confiança: {q3.confidence:.1%})")
for opt, prob in q3.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q3.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

print(f"\n[4] CONFIANÇA PROBABILÍSTICA DO JEV (+EV NOS PRÓXIMOS 50 TRADES): {q4.noul:.1%}")

print(f"\n[5] GRAU DE NECESSIDADE DE VALIDAÇÃO DE CÓDIGO ANTES DO SWITCH: {q5.score:.2f} / 5.00 (Confiança: {q5.confidence:.1%})")

output = {
    "timestamp": time.time(),
    "answers": {
        "live_activation_verdict": {
            "choice": q1.choice,
            "confidence": q1.confidence,
            "probabilities": q1.probabilities
        },
        "kalshi_real_readiness": {
            "choice": q2.choice,
            "confidence": q2.confidence,
            "probabilities": q2.probabilities
        },
        "polymarket_sol_shared_wallet_risk": {
            "choice": q3.choice,
            "confidence": q3.confidence,
            "probabilities": q3.probabilities
        },
        "overall_live_go_confidence": {
            "noul": q4.noul
        },
        "implementation_prerequisite_score": {
            "score": q5.score,
            "confidence": q5.confidence
        }
    }
}

with open("jev_live_activation_decision.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n[*] Parecer completo salvo em jev_live_activation_decision.json")
