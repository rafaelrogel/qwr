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
print("  🤖 ENVIANDO O RELATÓRIO DOS 20 ANALISTAS E CÓDIGO FONTE AO JEV (TYPESAFE AI)")
print("=" * 90)

state_dossier = """
QUANTITATIVE & CODEBASE AUDIT: EVALUATION OF THE 20-SPECIALIST CODE REVIEW REPORT FOR QWR REPO (@77ddf58)

A panel of 20 quantitative and software engineering specialists audited the repository and delivered a comprehensive report with 10 cross-cutting findings and 20 individual verdicts.

VERIFIED FACTS CONFIRMED DIRECTLY IN THE CODEBASE:
1. LEDGER VS WALLET GAP ($26 phantom PnL & Tautological Parity Check):
   - live_trading_journal.json has 138 trades. Sum of cycle_pnl = +$26.88 USDC.
   - Polygon Safe wallet balance is currently $21.81 USDC (started at $21.00 deposit -> net wallet delta is only +$0.81 USDC).
   - In live_trader_5m.py:1479-1488:
     self.session_pnl = round(new_balance - self.session_initial_balance, 2)
     expected_journal_balance = round(self.session_initial_balance + self.session_pnl, 2)
     parity_gap = abs(new_balance - expected_journal_balance)
     -> Mathematical tautology: parity_gap is algebraically identically 0.00! It never checks the sum of trade cycle_pnl against wallet delta.

2. KALSHI 15M 'TAKE-PROFIT' AND SETTLEMENT DISCREPANCY:
   - In kalshi_trader_15m.py:406-430:
     When cur_bps >= 15.0:
       sold_early = True
       early_sell_price = TAKE_PROFIT_CENTS
       self.balance += cycle_pnl
     -> The bot NEVER calls kalshi_client.place_order() to sell the contract on Kalshi! It records a virtual profit in the local journal, but leaves the real position open on Kalshi until expiration.
     -> At settlement (line 437), it checks Binance spot (final_spot = get_binance_btc_spot()) instead of fetching Kalshi official settlement or account balance.

3. KALSHI 9-YEAR BACKTEST LOOKAHEAD ARTIFACT:
   - In backtest_kalshi_15m_9y.py:159-176:
     c1 = candles_by_ts.get(w_ts + 300) # 5m-10m candle
     spot_450s = (c1['open'] + c1['close']) / 2.0
     -> c1['close'] is the price at 600s! Using it at 450s introduces 150 seconds of future lookahead.
     -> c1['high'] is used for TP triggering across the entire candle. Zero exchange fees are modeled.
     -> Claims 94.5% WR and +$1,421 profit, which is largely an artifact of this lookahead and unmodeled friction.

4. FEED ERROR DEFAULT TO 0.0 (STRIKE COLLAPSE RISK):
   - In live_trader_5m.py:840:
     strike = get_candle_open(window_ts) or 0.0
     -> If RPC and candle feeds fail, strike becomes 0.0. At 135s: delta = spot - 0.0 (~$83,000), triggering an erroneous UP or DOWN trade rather than aborting.

5. LIVE EXECUTION DRAG VS BACKTEST ASSUMPTIONS:
   - Backtest assumed fills at $0.565 (breakeven 57.9%, EV +$0.101/trade).
   - In live execution on Polymarket, fills average ~$0.61 (moving breakeven to ~62.5% and compressing EV to ~+$0.02 - +$0.05/trade before gas and relayer costs).

6. OPERATIONAL & ENGINEERING HYGIENE:
   - No unit tests or assertions across the entire codebase (22k lines).
   - No background process watchdog or centralized rotating file logging.
   - Dashboard server has Access-Control-Allow-Origin: * without authentication.
   - requirements.txt does not pin py_clob_client_v2 or typesafe_sdk.

REPORT'S CORE RECOMMENDATIONS:
- P0: Halt live scaling immediately; fix wallet parity truth check; abort on feed failure; fix Kalshi sell order; account for real fills.
- Keep capital at hobby level ($1 - $2 micro-stakes) or paper until 30 days of reconciled live trading.
"""

client = TypeSafeClient()

questions = {
    "report_validity_verdict": Choice(
        instructions="Evaluate the overall validity and technical accuracy of the 20-specialist report based on the verified codebase facts.",
        criteria={
            "overwhelmingly_accurate_critical_truths": "OVERWHELMINGLY ACCURATE: The report identified genuine, high-severity bugs (tautological parity check, Kalshi missing sell order, 150s lookahead in 9y backtest, strike=0 fallback) that must be immediately addressed.",
            "partially_accurate_mostly_pedantic": "PARTIALLY ACCURATE: Some points are valid, but the tone is overly pessimistic and ignores working components.",
            "inaccurate_alarmist": "INACCURATE: The findings do not represent real risks to live operations."
        }
    ),
    "ledger_wallet_gap_verdict": Choice(
        instructions="Analyze finding #1: sum(cycle_pnl) = +$26.88 vs real wallet +$0.81, and the tautological parity check in live_trader_5m.py.",
        criteria={
            "critical_accounting_failure": "CRITICAL ACCOUNTING FAILURE: The parity check is an algebraic tautology (checks new_balance against itself). The $26 discrepancy proves that past journal PnL credited theoretical payouts that were never reconciled or redeemed on-chain.",
            "acceptable_discrepancy": "ACCEPTABLE: Minor timing differences between relayer balance and journal.",
            "unimportant": "UNIMPORTANT: Only the current wallet balance matters."
        }
    ),
    "kalshi_execution_verdict": Choice(
        instructions="Analyze finding #6: Kalshi trader records Take-Profit PnL in journal without sending a sell order to Kalshi API.",
        criteria={
            "critical_live_blocker": "CRITICAL LIVE BLOCKER: Desk 3 cannot be considered truly live if Take-Profit does not send a sell order and settlement relies on Binance spot. This creates unhedged, unmonitored market exposure.",
            "minor_inconvenience": "MINOR INCONVENIENCE: Can remain active while an order submission function is patched.",
            "working_as_intended": "WORKING AS INTENDED: Virtual TP tracking is sufficient."
        }
    ),
    "kalshi_9y_lookahead_verdict": Choice(
        instructions="Analyze finding #4: backtest_kalshi_15m_9y.py using c1['close'] (600s) to evaluate spot at 450s and c1['high'] for TP.",
        criteria={
            "confirmed_lookahead_contamination": "CONFIRMED LOOKAHEAD CONTAMINATION: The 94.5% WR and +$1,421 profit are mathematical artifacts of lookahead bias (knowing future price within the 15m candle). It should not be used to justify capital allocation.",
            "valid_approximation": "VALID APPROXIMATION: Midpoint interpolation is a standard quantitative backtest technique.",
            "insignificant_bias": "INSIGNIFICANT BIAS: The edge remains robust despite the lookahead."
        }
    ),
    "immediate_capital_action": Choice(
        instructions="What is Jev's recommended capital action right now for the user?",
        criteria={
            "halt_scale_fix_p0": "FREEZE EXPANSION & APPLY P0 FIXES: Do NOT scale capital. Keep Desk 1 at $1 micro-stake, revert Desk 3 (Kalshi) and Desk 2 (SOL) to Paper until P0 bugs (wallet truth, Kalshi sell order, strike fallback) are resolved and verified.",
            "maintain_current_live": "MAINTAIN CURRENT LIVE: Continue running Desks 1, 2, and 3 live with existing $1 stakes without changes.",
            "scale_capital_immediately": "SCALE CAPITAL: Increase stakes to $5-$10 per trade immediately."
        }
    ),
    "realistic_edge_assessment": Noul(
        instructions="Summarize Jev's assessment of the true edge of the BTC 5m strategy: What is the realistic net EV per trade under real-world slippage (0.61 fills) and fees, and what is its legitimate capital capacity?"
    ),
    "code_hygiene_score": Score(
        instructions="Rate the urgency of implementing P0 and P1 engineering fixes (true wallet parity, strike=0 abort, requirements.txt, and unit tests) from 1 (unimportant) to 5 (vital emergency).",
        criteria=[
            "Optional cleanup",
            "Low priority maintenance",
            "Recommended improvement",
            "Urgent priority",
            "Vital emergency prerequisite before any capital scale"
        ]
    )
}

print("-> Consultando JEV API (TypeSafe AI)...")
t0 = time.time()
response = client.system_one(state=state_dossier, questions=questions)
t1 = time.time()
print(f"-> Resposta recebida do JEV em {t1 - t0:.2f}s!")

q1 = response.answers["report_validity_verdict"]
q2 = response.answers["ledger_wallet_gap_verdict"]
q3 = response.answers["kalshi_execution_verdict"]
q4 = response.answers["kalshi_9y_lookahead_verdict"]
q5 = response.answers["immediate_capital_action"]
q6 = response.answers["realistic_edge_assessment"]
q7 = response.answers["code_hygiene_score"]

output = {
    "timestamp": time.time(),
    "answers": {
        "report_validity_verdict": {
            "choice": q1.choice,
            "confidence": q1.confidence,
            "probabilities": q1.probabilities
        },
        "ledger_wallet_gap_verdict": {
            "choice": q2.choice,
            "confidence": q2.confidence,
            "probabilities": q2.probabilities
        },
        "kalshi_execution_verdict": {
            "choice": q3.choice,
            "confidence": q3.confidence,
            "probabilities": q3.probabilities
        },
        "kalshi_9y_lookahead_verdict": {
            "choice": q4.choice,
            "confidence": q4.confidence,
            "probabilities": q4.probabilities
        },
        "immediate_capital_action": {
            "choice": q5.choice,
            "confidence": q5.confidence,
            "probabilities": q5.probabilities
        },
        "realistic_edge_assessment": {
            "noul": q6.noul
        },
        "code_hygiene_score": {
            "score": q7.score,
            "confidence": q7.confidence
        }
    }
}

output_path = "jev_20_analysts_audit_response.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 90)
print("  📊 RESULTADO DA AUDITORIA DO JEV (TYPESAFE AI)")
print("=" * 90)
print(f"1. Veredito sobre o Relatório dos 20 Analistas: {q1.choice.upper()} (Confiança: {q1.confidence:.1%})")
for opt, p in q1.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n2. Veredito sobre Gap Ledger vs Wallet ($26):   {q2.choice.upper()} (Confiança: {q2.confidence:.1%})")
for opt, p in q2.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n3. Veredito sobre Execução Kalshi TP Falso:    {q3.choice.upper()} (Confiança: {q3.confidence:.1%})")
for opt, p in q3.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n4. Veredito sobre Backtest 9y Kalshi:         {q4.choice.upper()} (Confiança: {q4.confidence:.1%})")
for opt, p in q4.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n5. Ação Recomendada de Capital:                {q5.choice.upper()} (Confiança: {q5.confidence:.1%})")
for opt, p in q5.probabilities.items():
    print(f"   • {opt}: {p:.1%}")

print(f"\n6. Urgência de Higiene de Engenharia (1 a 5): {q7.score:.2f} / 5.0 (Confiança: {q7.confidence:.1%})")
print(f"\n7. Avaliação Probabilística do Edge pelo JEV:\n   Noul Score: {q6.noul:.1%}")
print("=" * 90)

