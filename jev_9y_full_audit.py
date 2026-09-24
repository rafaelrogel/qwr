"""
=============================================================================
JEV 1.13.0 — AUDITORIA INSTITUCIONAL DOS 9 ANOS COMPLETOS (2017-2026)
=============================================================================
Envia o dataset estruturado de 9 anos (318.570 janelas, 3.484 trades reais,
breakdown anual completo de 2017 a 2026, métricas de drawdown e Sharpe)
diretamente para o modelo 'jev-1.13.0' da TypeSafe AI.
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

from dotenv import load_dotenv; load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_9Y = os.path.join(BASE_DIR, "backtest_kalshi_15m_9y_results.json")

print("\n" + "=" * 105)
print("  📡 ENVIANDO DADOS COMPLETOS DE 9 ANOS PARA O MODELO JEV (TYPESAFE AI)")
print("=" * 105)

# Carrega o arquivo com todos os dados brutos de 9 anos
with open(RESULTS_9Y, "r", encoding="utf-8") as f:
    d = json.load(f)

# Monta o dossiê detalhado com as tabelas ano a ano
state = {
    "dataset_metadata": {
        "source": "Binance BTCUSDT 5-Minute Klines (Aug 2017 - Sep 2026)",
        "total_15m_windows_analyzed": d["total_15m_windows"],
        "total_candles_processed": 955699,
        "sample_duration_years": 9.1,
        "underlying_asset": "Bitcoin (BTC/USD)",
        "contract_type": "Binary Option Up/Down 15-Minute Expiry"
    },
    "strategy_parameters": {
        "decision_point_seconds": 450,
        "decision_point_percentage_of_candle": 50.0,
        "dynamic_deadband_basis_points": 3.5,
        "dynamic_deadband_formula": "max(25.0, strike * 0.00035)",
        "hard_price_ceiling_cents": 60,
        "hard_price_floor_cents": 35,
        "money_management": "Fixed $1.00 USD stake per signal, initial bankroll $35.00 USD"
    },
    "full_9_year_performance_metrics": {
        "total_signals_generated": 146276,
        "filtered_trades_taken_under_60c": d["participated"],
        "pure_hold_win_rate_no_take_profit": "72.59% (2,529 Wins / 955 Losses)",
        "take_profit_assisted_win_rate": f"{d['win_rate']}% ({d['total_wins']} Wins / {d['losses']} Losses)",
        "initial_capital_usd": d["initial_capital"],
        "final_capital_usd": d["final_balance"],
        "total_net_pnl_usd": d["total_pnl"],
        "total_capital_wagered_usd": d["total_stake"],
        "total_payout_recovered_usd": d["total_payout"],
        "roi_on_volume_percentage": d["roi_on_volume"],
        "max_drawdown_usd": d["max_drawdown"],
        "daily_sharpe_ratio": d["sharpe_daily"],
        "profitable_trading_days": d["profitable_days"],
        "loss_trading_days": d["loss_days"]
    },
    "annual_breakdown_all_9_years": d["yearly_pnl"]
}

state_str = json.dumps(state, indent=2)
print(f"[*] Dossiê estruturado preparado: {len(state_str):,} caracteres.")
print(f"[*] Chamando API oficial do Jev (https://api.typesafe.ai/v1/systemone)...")

t0 = time.time()
client = TypeSafeClient()

questions = {
    "is_9y_sample_statistically_significant": Choice(
        instructions="Evaluate whether this 9-year dataset of 318,570 windows and 3,484 executed trades is statistically significant enough to rule out luck, curve-fitting, or random walk chance.",
        criteria={
            "overwhelmingly_significant": "Overwhelmingly significant - 9 full years across bear, bull, and flat regimes with p < 0.0001 rules out random chance",
            "moderately_significant": "Moderately significant - 3,484 trades is large, but regime shifts still warrant live verification",
            "insufficient": "Insufficient - backtest assumptions may still hide execution friction"
        }
    ),
    "pure_hold_vs_tp_verdict": Choice(
        instructions="Compare the 72.59% pure-hold win rate against the 94.5% Take-Profit win rate. Which metric should the trader consider the honest baseline?",
        criteria={
            "72_percent_pure_hold": "72.59% pure-hold is the honest, conservative ground-truth to build risk models on",
            "tp_realistic_intermediate": "The truth is between 80-85%, as real limit order TP catches favorable intra-candle wicks",
            "94_percent_tp": "94.5% is fully achievable if limit sell orders are placed at 86 cents at the time of entry"
        }
    ),
    "edge_durability_across_market_cycles": Score(
        instructions="Rate how durable this 3.5 bps momentum edge is across diverse market cycles (2017 boom, 2018 crash, 2021 bull, 2022 crypto winter, 2024-2026 ETF era) on a scale of 1 to 5.",
        criteria=["Extremely Fragile", "Vulnerable to Regime Shifts", "Moderately Robust", "Highly Robust", "Exceptional Cross-Regime Durability"]
    ),
    "risk_of_depleting_35_dollars": Choice(
        instructions="With a starting capital of $35.00 USD and flat $1.00 bets, what is Jev's calculated probability of total bankroll depletion ($0.00 balance)?",
        criteria={
            "under_1_percent": "Virtually zero (less than 1% probability of ruin) given the 72.6% win rate and $3.00 max drawdown",
            "between_1_and_5_percent": "Low risk (1% to 5% probability of ruin) under an extreme black-swan loss streak",
            "above_10_percent": "Significant risk (greater than 10% probability of ruin)"
        }
    ),
    "growth_expectancy_next_12_months": Choice(
        instructions="Given the 9-year historical annual pace ($300 - $700 net profit per year with $1 stake), what is Jev's most probable 12-month net capital projection from a $35 starting balance?",
        criteria={
            "between_300_and_800": "$300 to $800 USD net profit - steady continuation of the 9-year statistical average",
            "between_100_and_300": "$100 to $300 USD net profit - conservative if intra-candle volatility remains low",
            "near_breakeven_or_loss": "Near breakeven or loss due to market maker adaptation"
        }
    ),
    "deposit_10_claim_25_bonus_action": Choice(
        instructions="Should the user proceed with depositing $10.00 to claim the $25.00 bonus ($35.00 total) on Kalshi based on this 9-year audit?",
        criteria={
            "strongly_recommend_deposit": "Strongly recommended - the +250% instant bonus combined with a proven 72.6% win rate creates a rare positive EV asymmetric bet",
            "proceed_with_caution": "Proceed with caution - ensure regulatory terms in user's country allow withdrawals",
            "do_not_deposit": "Do not deposit - stick exclusively to existing platforms"
        }
    ),
    "jev_model_confidence_score": Noul(
        instructions="Provide Jev's overall probabilistic confidence (0.0 to 1.0) that the strategy will generate positive net profit over the next 3,000 live trades."
    )
}

response = client.system_one(state=state, questions=questions)
elapsed = time.time() - t0

print(f"[OK] Resposta processada pelo Jev em {elapsed:.2f} segundos!\n")

print("=" * 105)
print("  📋 AUDITORIA INSTITUCIONAL EMITIDA PELO MODELO JEV (TYPESAFE AI)")
print("=" * 105)
print(f"  • Modelo da TypeSafe Utilizado:   {getattr(response, 'model', 'jev-1.13.0')}")
print(f"  • Request ID Oficial:            {getattr(response, 'request_id', 'N/A')}")
if hasattr(response, 'usage'):
    print(f"  • Tokens de Entrada Processados: {response.usage.input_tokens:,} tokens")
    print(f"  • Tokens de Saída Gerados:       {response.usage.output_tokens:,} tokens")
print("-" * 105)

# Questão 1
q1 = response.answers["is_9y_sample_statistically_significant"]
print(f"\n1. SIGNIFICÂNCIA ESTATÍSTICA DOS 9 ANOS (318.570 JANELAS):")
print(f"   ▶ Veredito do Jev: {q1.choice.upper()}")
print(f"   ▶ Confiança: {q1.confidence:.1%}")
print("   ▶ Probabilidades calculadas pelo Jev:")
for opt, prob in q1.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# Questão 2
q2 = response.answers["pure_hold_vs_tp_verdict"]
print(f"\n2. TAXA REAL DE ACERTO (72.6% PURE-HOLD vs 94.5% COM TP):")
print(f"   ▶ Veredito do Jev: {q2.choice.upper()}")
print(f"   ▶ Confiança: {q2.confidence:.1%}")
print("   ▶ Probabilidades calculadas pelo Jev:")
for opt, prob in q2.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q2.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# Questão 3
q3 = response.answers["edge_durability_across_market_cycles"]
print(f"\n3. DURABILIDADE ATRAVÉS DOS CICLOS DO BITCOIN (2017 A 2026):")
print(f"   ▶ Score de Robustez do Jev: {q3.score:.2f} / 5.00")
print(f"   ▶ Confiança: {q3.confidence:.1%}")

# Questão 4
q4 = response.answers["risk_of_depleting_35_dollars"]
print(f"\n4. RISCO DE QUEBRAR A BANCA DE $35 DÓLARES (RUÍNA TOTAL):")
print(f"   ▶ Veredito do Jev: {q4.choice.upper()}")
print(f"   ▶ Confiança: {q4.confidence:.1%}")
print("   ▶ Probabilidades calculadas pelo Jev:")
for opt, prob in q4.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q4.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# Questão 5
q5 = response.answers["growth_expectancy_next_12_months"]
print(f"\n5. PROJEÇÃO DE LUCRO LÍQUIDO NOS PRÓXIMOS 12 MESES:")
print(f"   ▶ Projeção do Jev: {q5.choice.upper()}")
print(f"   ▶ Confiança: {q5.confidence:.1%}")
print("   ▶ Probabilidades calculadas pelo Jev:")
for opt, prob in q5.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q5.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# Questão 6
q6 = response.answers["deposit_10_claim_25_bonus_action"]
print(f"\n6. RECOMENDAÇÃO: DEPOSITAR $10 E PEGAR O BÔNUS DE $25?")
print(f"   ▶ Recomendação do Jev: {q6.choice.upper()}")
print(f"   ▶ Confiança: {q6.confidence:.1%}")
print("   ▶ Probabilidades calculadas pelo Jev:")
for opt, prob in q6.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q6.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# Questão 7
q7 = response.answers["jev_model_confidence_score"]
print(f"\n7. CONFIANÇA PROBABILÍSTICA GERAL DO JEV DE LUCRO FUTURO:")
print(f"   ▶ Probabilidade Calculada pelo Jev: {q7.noul:.1%}")

print("\n" + "=" * 105 + "\n")

# Salva arquivo com resposta bruta
with open(os.path.join(BASE_DIR, "jev_9y_full_audit_response.json"), "w", encoding="utf-8") as f:
    json.dump({
        "model": getattr(response, "model", "jev-1.13.0"),
        "request_id": getattr(response, "request_id", None),
        "usage": {
            "input_tokens": response.usage.input_tokens if hasattr(response, "usage") else None,
            "output_tokens": response.usage.output_tokens if hasattr(response, "usage") else None,
        },
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
    }, f, indent=2, ensure_ascii=False)
