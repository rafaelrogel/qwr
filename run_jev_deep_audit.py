"""
=============================================================================
JEV / TYPESAFE AI — AUDITORIA PROFUNDA E AUTÔNOMA DO ENGINE BTC5M
=============================================================================
Este script consulta DIRETAMENTE o modelo Jev (SystemOne) da TypeSafe AI,
passando os dados completos de telemetria, backtests de 5 e 9 anos, e a nova
arquitetura limpa (Sem Streak Snapper, Deadband 2.1 bps, Teto $0.60).
Todas as respostas, probabilidades e vereditos são gerados pelo próprio JEV.
=============================================================================
"""

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

# Chave API do Jev fornecida pelo usuário
from dotenv import load_dotenv; load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

print("\n" + "=" * 100)
print("  🤖 INICIANDO AUDITORIA PROFUNDA E AUTÔNOMA DA IA JEV (TYPESAFE AI)")
print("=" * 100)

# Carrega os dados reais mais recentes
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
comp_file = os.path.join(BASE_DIR, "backtest_5y_comparativo.json")
journal_file = os.path.join(BASE_DIR, "live_trading_journal.json")

comp_data = {}
if os.path.exists(comp_file):
    with open(comp_file, "r", encoding="utf-8") as f:
        comp_data = json.load(f)

journal_data = {}
if os.path.exists(journal_file):
    with open(journal_file, "r", encoding="utf-8") as f:
        journal_data = json.load(f)

# Constrói o dossiê quantitativo para o Jev analisar
sem_streak = comp_data.get("SEM_STREAK", {})
state = f"""
COMPREHENSIVE QUANTITATIVE AUDIT DOSSIER — POLYMARKET BTC 5-MINUTE SNIPER ENGINE
Platform: Polymarket CLOB V2 on Polygon & Binance Futures Real-Time Microstructure
Current Live Balance: $18.52 USDC (started at $21.00 USDC, 128 cycles completed, 91 wins / 37 losses = 71.1% Win Rate)

5-YEAR EMPIRICAL SIMULATION RESULTS (2,627,819 1-minute klines = 525,547 5m cycles):
- Strategy Version: Sniper Purista (Streak Snapper Deactivated, Deadband Scale-Invariant 2.1 bps, Max Price $0.60)
- Total Real Trades Participated: 28,676 trades
- Overall Win Rate: 76.5% (21,936 Wins / 6,740 Losses)
- Total Net P&L: +$25,295.31 USDC
- ROI on Volume: +18.72%
- Maximum Drawdown: $261.17 USDC
- Daily Sharpe Ratio: 0.6699
- Take-Profit (SirMartingale @ 86c): Triggered 3,293 times, directly preventing 139 losing flips
- Stop-Loss (Emergency exit): Triggered when delta flips against position, limiting losses to ~-$0.10 instead of -$1.00
- Annual Breakdown:
  * 2021: -$2.83
  * 2022: +$7,871.32
  * 2023: +$12,260.39
  * 2024: +$2,668.49
  * 2025: +$1,033.98
  * 2026: +$1,463.96
- 9-Year Long-Term Benchmark: 955,350 candles tested from 2017 to 2026 show pure hold directional win rate of 72.6% (+$756 net profit with flat $1 stake).

Current Production Architecture (live_trader_5m.py):
1. Entry @ 135s of 5m candle (45% mark).
2. Dynamic Scale-Invariant Deadband: 2.1 bps of strike price (e.g. $18.06 at $86,000 BTC, floor $15.00).
3. Hard Price Ceiling: Never buy outcome shares above $0.60 (ensures minimum 1.67x payout, breakeven <= 60%).
4. Binance Lead Drift Confirmation: Requires spot drift alignment to prevent counter-trend execution.
5. CLOB L2 Orderbook Liquidity & Spread: Vetoes execution if spread > $0.06 or ask-wall imbalance detected.
6. Execution Mode: Live trading on Polygon mainnet via ClobClient V2.
"""

print(f"[*] Dossiê preparado ({len(state)} caracteres).")
print("[*] Conectando ao modelo Jev (SystemOne)... Enviando perguntas analíticas...\n")

t0 = time.time()
client = TypeSafeClient()

questions = {
    "structural_edge": Choice(
        instructions="Analyze whether this trading system possesses a genuine, durable structural statistical edge over the Polymarket orderbook, or if past profits are merely variance and luck.",
        criteria={
            "genuine_durable_edge": "Genuine durable edge - the combination of 135s directional momentum, Binance latency arbitrage, and 60c price ceiling creates a persistent positive EV",
            "marginal_decaying_edge": "Marginal edge - edge exists but is rapidly eroding as market makers become more efficient",
            "spurious_overfitting": "Spurious/Overfitting - the strategy has no real edge and is overfit to historical volatility"
        }
    ),
    "risk_of_ruin_current_bankroll": Choice(
        instructions="Given the current live balance of $18.52 USDC and a fixed stake size of $1.00 per trade, what is the probability of the account going broke (hitting $0.00) vs growing to $50.00+ USDC?",
        criteria={
            "growth_highly_probable": "Growth to $50+ is highly probable (>85% probability) due to 76.5% win rate and stop-loss protection",
            "moderate_ruin_risk": "Moderate ruin risk (20-40% chance of drawdown below $10) if an adverse cluster of losses occurs early",
            "high_ruin_risk": "High ruin risk (>50% chance of depletion) - $18.52 is too small for a $1.00 stake"
        }
    ),
    "why_did_returns_slow_in_2024_2025": Choice(
        instructions="What is the primary fundamental reason why the strategy's annual P&L slowed from ~$12,000 in 2023 to ~$1,000-$2,600 in 2024-2025?",
        criteria={
            "volatility_compression": "Volatility compression & higher BTC dollar price - lower relative intra-candle volatility reduced the frequency of clean 2.1 bps breakouts",
            "market_maker_efficiency": "Polymarket market makers became faster and tightened spreads, reducing the window of mispriced shares",
            "strategy_breakdown": "The underlying mathematical signal degraded and stopped working"
        }
    ),
    "optimal_bankroll_management": Choice(
        instructions="What is the mathematically optimal stake sizing policy for this trader with $18.52 USDC balance?",
        criteria={
            "keep_flat_1_dollar": "Keep flat $1.00 stake until the account reaches at least $40.00 USDC, then scale to $1.50",
            "reduce_to_50_cents": "Reduce stake size to $0.50 USDC immediately to minimize drawdown risk on a small bankroll",
            "aggressive_scaling": "Increase stake to $1.50 or $2.00 immediately to accelerate compound growth"
        }
    ),
    "timeline_to_50_usdc": Choice(
        instructions="Based on the strategy's average trade frequency (12-16 trades/day) and average EV per trade (~+$0.25), what is the most realistic timeframe for the balance to grow from $18.52 to $50.00 USDC?",
        criteria={
            "one_to_two_weeks": "1 to 2 weeks (7 to 14 days) under normal market conditions",
            "two_to_four_weeks": "2 to 4 weeks (15 to 30 days) if volatility is moderate to low",
            "over_a_month": "Over 1 month or unlikely to reach $50 without additional deposits"
        }
    ),
    "final_verdict_instruction": Choice(
        instructions="What is Jev's authoritative, direct operational verdict for this trader right now?",
        criteria={
            "continue_live_trading": "Continue live trading with full confidence - the engine is mathematically validated, clean, and positive EV",
            "pause_and_paper_trade": "Pause live trading and paper trade for 14 days to re-verify live slippage",
            "halt_operations": "Halt operations permanently"
        }
    ),
    "edge_durability_score": Score(
        instructions="Rate the mathematical durability and robustness of this 5m momentum + price cap engine on a scale of 1 to 5.",
        criteria=["Fragile / Likely Fluke", "Weak", "Moderate Durability", "Robust", "Institutional Grade Robustness"]
    ),
    "jev_confidence_level": Noul(
        instructions="State Jev's overall probabilistic confidence that this trading system will remain net profitable over the next 12 months."
    )
}

response = client.system_one(state=state, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta recebida do Jev em {elapsed:.1f}s!\n")

print("=" * 100)
print("  📊 RESULTADOS OFICIAIS GERADOS PELO JEV (TYPESAFE AI)")
print("=" * 100)

# 1. Edge Estrutural
print("\n[1] NATUREZA DO EDGE MATEMÁTICO:")
se = response.answers["structural_edge"]
print(f"  ▶ Veredito do Jev: {se.choice.upper()}")
print(f"  ▶ Confiança: {se.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in se.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == se.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

# 2. Risco de Ruína com $18.52
print("\n[2] RISCO DE RUÍNA COM A BANCA ATUAL ($18.52 USDC):")
rr = response.answers["risk_of_ruin_current_bankroll"]
print(f"  ▶ Veredito do Jev: {rr.choice.upper()}")
print(f"  ▶ Confiança: {rr.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in rr.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == rr.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

# 3. Motivo da Desaceleração em 2024/2025
print("\n[3] POR QUE O LUCRO ANUAL DIMINUIU EM 2024-2025?")
yr = response.answers["why_did_returns_slow_in_2024_2025"]
print(f"  ▶ Diagnóstico do Jev: {yr.choice.upper()}")
print(f"  ▶ Confiança: {yr.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in yr.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == yr.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

# 4. Gestão de Banca Ótima
print("\n[4] GESTÃO DE BANCA RECOMENDADA PELO JEV:")
bm = response.answers["optimal_bankroll_management"]
print(f"  ▶ Política Recomendada: {bm.choice.upper()}")
print(f"  ▶ Confiança: {bm.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in bm.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == bm.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

# 5. Prazo até os $50 USDC
print("\n[5] TEMPO ESTIMADO ATÉ CHEGAR AOS $50 USDC:")
tl = response.answers["timeline_to_50_usdc"]
print(f"  ▶ Projeção do Jev: {tl.choice.upper()}")
print(f"  ▶ Confiança: {tl.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in tl.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == tl.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

# 6. Veredito Operacional Final
print("\n[6] VEREDITO OPERACIONAL DEFINITIVO DO JEV:")
fv = response.answers["final_verdict_instruction"]
print(f"  ▶ DECISÃO DO JEV: {fv.choice.upper()}")
print(f"  ▶ Confiança: {fv.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in fv.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == fv.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

# 7. Robustez
print("\n[7] NOTA DE ROBUSTEZ MATEMÁTICA DO SISTEMA:")
ed = response.answers["edge_durability_score"]
print(f"  ▶ Score de Robustez: {ed.score:.2f} / 5.00")
print(f"  ▶ Confiança: {ed.confidence:.1%}")

# 8. Confiança Geral para os Próximos 12 Meses
print("\n[8] PROBABILIDADE DO JEV DE LUCRO NOS PRÓXIMOS 12 MESES:")
jc = response.answers["jev_confidence_level"]
print(f"  ▶ Confiança Jev (Probabilidade Noul): {jc.noul:.1%}")

print("\n" + "=" * 100)
print("  [OK] AUDITORIA JEV CONCLUÍDA COM SUCESSO E SALVA!")
print("=" * 100 + "\n")

# Salva arquivo JSON com todos os dados brutos
output_data = {
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
    }
}
with open(os.path.join(BASE_DIR, "jev_deep_audit_results.json"), "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)
