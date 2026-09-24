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

from dotenv import load_dotenv; load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

print("\n" + "=" * 90)
print("  🤖 CONSULTANDO JEV (TYPESAFE AI) SOBRE MELHORIAS ADICIONAIS & RISCOS REMANESCENTES")
print("=" * 90)

state_dossier = """
PHASE 2 ARCHITECTURAL & RISK AUDIT: POST-P0 REMAINING ACTIONS & SECONDARY IMPROVEMENTS

Current System State:
1. Critical P0 fixes successfully implemented and committed (commit 4bcf1b0):
   - Genuine wallet parity check implemented (compares cumulative cycle PnL against actual on-chain USDC wallet balance delta).
   - Strike collapse bug eliminated (immediate abort on feed/oracle failure; no more 'or 0.0').
   - Kalshi 15m Take-Profit now includes official single-book sell order execution (action='sell').
   - Kalshi and Solana desks reverted to PAPER mode in .env until further live validation.
   - Solana restart deduplication active (traded_windows re-populated from journal).
   - Dashboard CORS locked down to local origin; balance bound to real journal balance.
   - Automated unit test suite created (test_critical_fixes.py) with 100% passing rate.

Proposed Secondary (P1/P2) Improvements:
1. GLOBAL FILE KILL-SWITCH ('HALT' / 'EMERGENCY_STOP'):
   - Add a check at the top of every cycle across all bots for a physical 'HALT' file in the directory. If present, immediately freezes all entry points and skips trading without crashing the process.

2. PERSISTENT DRAWDOWN BREAKER (DEPOSIT-ANCHORED):
   - Currently, session breakers reset on restart. Proposal: Anchor max loss not just to session_initial_balance, but strictly to initial_deposit ($21.00). If balance falls below $16.00 (>$5 total loss from deposit), the bot permanently locks out further entries across restarts.

3. DASHBOARD CONCURRENCY & ISOLATION:
   - Upgrade dashboard server from socketserver.TCPServer to socketserver.ThreadingTCPServer.
   - Decouple dashboard from background paper btc_5m_engine, ensuring it only displays telemetry from live market feeds and live trader state.

4. BACKTEST KALSHI 9Y CLEANUP:
   - Strip out the 150s future lookahead (c1.close) and unmodeled c1.high take-profit from backtest_kalshi_15m_9y.py to produce an honest PIT benchmark.
"""

client = TypeSafeClient()

questions = {
    "kill_switch_utility": Choice(
        instructions="Evaluate the utility and safety benefit of implementing a persistent file-based kill-switch ('HALT' file) and deposit-anchored circuit breaker.",
        criteria={
            "essential_safety_layer": "ESSENTIAL SAFETY LAYER: Highly recommended. Provides a deterministic, out-of-band panic button and prevents restart-loop breaker resets that could drain the bankroll.",
            "unnecessary_overhead": "UNNECESSARY: In-memory session checks and Ctrl+C / taskkill are already sufficient.",
            "neutral": "NEUTRAL: Minor convenience but does not alter trading edge."
        }
    ),
    "threading_server_recommendation": Choice(
        instructions="Evaluate upgrading the dashboard server to ThreadingTCPServer and isolating it from simulated paper engines.",
        criteria={
            "strongly_recommended": "STRONGLY RECOMMENDED: ThreadingTCPServer prevents request starvation during API polling, and decoupling from paper engines ensures truth-in-display.",
            "unnecessary": "UNNECESSARY: Single-threaded server is adequate for local user.",
            "neutral": "NEUTRAL: Negligible operational difference."
        }
    ),
    "kalshi_backtest_sanitization": Choice(
        instructions="Evaluate removing the lookahead interpolation from backtest_kalshi_15m_9y.py.",
        criteria={
            "mandatory_for_intellectual_honesty": "MANDATORY: Cleaning the backtest of lookahead bias is essential to understand whether the 15m strategy actually has an edge before risking real capital.",
            "low_priority_academic": "LOW PRIORITY: The backtest is already done; focus only on live code.",
            "unnecessary": "UNNECESSARY: Keep the original script as historical record."
        }
    ),
    "remaining_risk_score": Score(
        instructions="Rate the remaining operational risk of running Desk 1 (BTC 5m Live at $1 micro-stake) with current P0 fixes in place from 1 (negligible/controlled) to 5 (severe catastrophic risk).",
        criteria=[
            "Negligible/Fully Controlled ($1 stake, verified parity, armored stops)",
            "Low Controlled Risk (Hobby scale, strictly bounded loss)",
            "Moderate Risk (Execution drag may erode edge over time)",
            "High Risk (Significant chance of rapid drawdown)",
            "Severe Catastrophic Risk"
        ]
    ),
    "overall_strategic_recommendation": Noul(
        instructions="What is Jev's final overarching recommendation on next steps and operational posture for the user?"
    )
}

print("-> Consultando JEV API (TypeSafe AI)...")
t0 = time.time()
response = client.system_one(state=state_dossier, questions=questions)
t1 = time.time()
print(f"-> Resposta recebida do JEV em {t1 - t0:.2f}s!")

q1 = response.answers["kill_switch_utility"]
q2 = response.answers["threading_server_recommendation"]
q3 = response.answers["kalshi_backtest_sanitization"]
q4 = response.answers["remaining_risk_score"]
q5 = response.answers["overall_strategic_recommendation"]

output = {
    "timestamp": time.time(),
    "answers": {
        "kill_switch_utility": {
            "choice": q1.choice,
            "confidence": q1.confidence,
            "probabilities": q1.probabilities
        },
        "threading_server_recommendation": {
            "choice": q2.choice,
            "confidence": q2.confidence,
            "probabilities": q2.probabilities
        },
        "kalshi_backtest_sanitization": {
            "choice": q3.choice,
            "confidence": q3.confidence,
            "probabilities": q3.probabilities
        },
        "remaining_risk_score": {
            "score": q4.score,
            "confidence": q4.confidence
        },
        "overall_strategic_recommendation": {
            "noul": q5.noul
        }
    }
}

output_path = "jev_further_improvements_response.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 90)
print("  📊 PARECER DO JEV SOBRE MELHORIAS ADICIONAIS")
print("=" * 90)
print(f"1. Kill-Switch Global (HALT) & Circuit Breaker Persistente: {q1.choice.upper()} (Confiança: {q1.confidence:.1%})")
for opt, p in q1.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n2. Servidor Dashboard com Threading & Isolamento:          {q2.choice.upper()} (Confiança: {q2.confidence:.1%})")
for opt, p in q2.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n3. Sanitização do Backtest 9y Kalshi:                     {q3.choice.upper()} (Confiança: {q3.confidence:.1%})")
for opt, p in q3.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n4. Nível de Risco Residual no Desk 1 ($1 Stake):          {q4.score:.2f} / 5.0 (Confiança: {q4.confidence:.1%})")
print(f"\n5. Recomendação Estratégica do JEV (Noul Score):          {q5.noul:.1%}")
print("=" * 90)
