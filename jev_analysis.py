"""
Análise Jev/TypeSafe AI dos resultados do backtest 5 anos
Usa o SDK oficial typesafe-sdk para comunicação correta com a API
"""
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, "backtest_5y_results_v2.json")

# Configurar API key
JEV_API_KEY = "apikey_2221ec444158dd114f7c9c1455f7a43d54d3_8650ae9c262528646e523b5b9185b404723800fc38025af60761917b012bed7c"
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

print("\n" + "=" * 90)
print("  [JEV/TYPESAFE AI] ANÁLISE PROBABILÍSTICA DO ENGINE BTC5M (SDK OFICIAL)")
print("=" * 90)

# Carregar resultados
print("[*] Carregando resultados do backtest...")
with open(RESULTS_FILE, "r", encoding="utf-8") as f:
    r = json.load(f)

# Preparar estado
state = f"""
BACKTEST RESULTS - BTC 5-Minute Up-or-Down Binary Options Engine (Polymarket)
Period: 5 years (September 2021 - September 2026)
Initial Capital: ${r['initial_balance']:.2f} USDC
Final Capital: ${r['final_balance']:,.2f} USDC
Total P&L: {r['total_pnl']:+,.2f} USDC
ROI on Volume: {r['roi']:+.2f}%
Return on Initial Capital: {r['total_pnl']/r['initial_balance']*100:+,.1f}%
Total Trades: {r['participated']:,}
Win Rate: {r['win_rate']:.1f}%
Max Drawdown: ${r['max_drawdown']:.2f} USDC
Peak Balance: ${r['peak_balance']:,.2f} USDC
Min Balance: ${r['min_balance']:,.2f} USDC
Sharpe Ratio (Daily): {r['sharpe_ratio_daily']:.4f}
Profitable Days: {r['profitable_days']}/{r['trading_days']} ({r['profitable_days']/max(r['trading_days'],1)*100:.1f}%)
Max Win Streak: {r['max_win_streak_days']} consecutive days
Max Loss Streak: {r['max_loss_streak_days']} consecutive days
Primary Entry Win Rate: {r['primary_wr']:.1f}%
Take-Profit (SirMartingale) Triggers: {r['sirmartingale_tp']:,}
Hedge (Bonereaper) Triggers: {r['bonereaper_hedge']}
Stake Progression: $1.00 base, +$0.50 per $10 profit, capped at $5.00
Yearly P&L: {json.dumps(r['yearly_pnl'])}
Profitable Quarters: 20 out of 21 (95.2%)
Best Month: {r['best_month']['month']} ({r['best_month']['pnl']:+,.2f})
Worst Month: {r['worst_month']['month']} ({r['worst_month']['pnl']:+,.2f})
Recent Trend: Performance declining from ~$11K/year (2023) to ~$920/year (2025)
"""

print(f"[*] Estado preparado ({len(state)} chars)")
print("[*] Enviando para Jev/TypeSafe AI...\n")

try:
    client = TypeSafeClient()

    response = client.system_one(
        state=state,
        questions={
            "strategy_viability": Choice(
                instructions="Based on these 5-year backtest results, evaluate the overall viability of this trading strategy for real money deployment with a starting capital of $21 USDC.",
                criteria={
                    "highly_viable": "Highly viable - strong consistent returns with manageable risk across 5 years",
                    "viable_with_caveats": "Viable with caveats - profitable overall but declining performance trend is concerning",
                    "marginal": "Marginal - past results strong but recent slowdown raises questions",
                    "not_viable": "Not viable - backtest results are unreliable for live trading"
                }
            ),
            "risk_level": Score(
                instructions="Rate the overall risk level of this strategy from 1 (very low) to 5 (very high), considering the max drawdown of $287, the 75.9% win rate, the Sharpe ratio of 0.65, and the declining yearly returns.",
                criteria=["Very Low Risk", "Low Risk", "Moderate Risk", "High Risk", "Very High Risk"]
            ),
            "overfitting_concern": Noul(
                instructions="Is there a significant concern that this strategy is overfit to historical data? Consider that it was tested over 5 years with 29,087 trades, 525,547 total cycles, and showed 75.9% win rate. However, it uses simulated CLOB prices rather than real market prices."
            ),
            "declining_performance": Noul(
                instructions="Is the declining annual performance trend (from +$11,884 in 2023 to +$919 in 2025) a serious red flag that suggests the strategy edge is disappearing?"
            ),
            "stake_scaling_safe": Noul(
                instructions="Is the progressive stake scaling (starting at $1.00, adding $0.50 per $10 profit, capped at $5.00 max) a safe and appropriate money management approach for this strategy?"
            ),
            "recommendation": Choice(
                instructions="Given these comprehensive 5-year results, what is your primary recommendation for this trader who currently has $16.93 USDC balance?",
                criteria={
                    "scale_up": "Scale up - deposit more capital, the strategy has a proven 5-year edge",
                    "maintain": "Maintain current approach - keep trading with current parameters",
                    "optimize": "Optimize - adjust parameters to address the declining performance",
                    "reduce_risk": "Reduce risk - lower stake sizes due to declining returns",
                    "paper_trade": "Paper trade - validate in real-time before committing more capital",
                    "stop": "Stop trading - the edge may have disappeared"
                }
            ),
            "projected_return_12m": Choice(
                instructions="Based on the 5-year trajectory (strong 2022-2023, declining 2024-2025, recovering 2026), what is the most likely 12-month return for this strategy starting from $16.93 USDC?",
                criteria={
                    "above_1000": "Above $1,000 profit - if volatility returns to 2022-2023 levels",
                    "500_to_1000": "$500-$1000 profit - moderate performance continuation",
                    "100_to_500": "$100-$500 profit - conservative based on recent 2025 pace",
                    "breakeven": "Near breakeven - the edge is thinning",
                    "loss": "Net loss - the strategy is no longer effective"
                }
            )
        }
    )

    print("=" * 90)
    print("  [JEV] RESULTADOS DA ANÁLISE")
    print("=" * 90)

    # Strategy Viability
    print("\n  1. VIABILIDADE DA ESTRATÉGIA:")
    sv = response.answers["strategy_viability"]
    print(f"     Escolha: {sv.choice}")
    print(f"     Confiança: {sv.confidence:.1%}")
    print(f"     Probabilidades:")
    for opt, prob in sv.probabilities.items():
        marker = " <<<" if opt == sv.choice else ""
        print(f"       - {opt}: {prob:.1%}{marker}")

    # Risk Level
    print("\n  2. NÍVEL DE RISCO:")
    rl = response.answers["risk_level"]
    print(f"     Score: {rl.score:.2f}/5")
    print(f"     Confiança: {rl.confidence:.1%}")
    print(f"     Probabilidades por nível:")
    for i, prob in enumerate(rl.probabilities):
        levels = ["Very Low", "Low", "Moderate", "High", "Very High"]
        label = levels[i] if i < len(levels) else f"Level {i+1}"
        print(f"       - {label}: {prob:.1%}")

    # Overfitting
    print("\n  3. RISCO DE OVERFITTING:")
    of = response.answers["overfitting_concern"]
    print(f"     Probabilidade de overfitting: {of.noul:.1%}")

    # Declining Performance
    print("\n  4. DECLÍNIO DE PERFORMANCE:")
    dp = response.answers["declining_performance"]
    print(f"     É um red flag sério: {dp.noul:.1%}")

    # Stake Scaling
    print("\n  5. ESCALONAMENTO DE STAKE:")
    ss = response.answers["stake_scaling_safe"]
    print(f"     É seguro e apropriado: {ss.noul:.1%}")

    # Recommendation
    print("\n  6. RECOMENDAÇÃO PRINCIPAL:")
    rec = response.answers["recommendation"]
    print(f"     Escolha: {rec.choice}")
    print(f"     Confiança: {rec.confidence:.1%}")
    print(f"     Probabilidades:")
    for opt, prob in rec.probabilities.items():
        marker = " <<<" if opt == rec.choice else ""
        print(f"       - {opt}: {prob:.1%}{marker}")

    # Projected Return
    print("\n  7. RETORNO PROJETADO (12 MESES):")
    pr = response.answers["projected_return_12m"]
    print(f"     Escolha: {pr.choice}")
    print(f"     Confiança: {pr.confidence:.1%}")
    print(f"     Probabilidades:")
    for opt, prob in pr.probabilities.items():
        marker = " <<<" if opt == pr.choice else ""
        print(f"       - {opt}: {prob:.1%}{marker}")

    print("\n" + "=" * 90)
    print("  [JEV] ANÁLISE CONCLUÍDA COM SUCESSO")
    print("=" * 90 + "\n")

    # Salvar resposta completa
    jev_output = {
        "strategy_viability": {"choice": sv.choice, "confidence": sv.confidence, "probabilities": sv.probabilities},
        "risk_level": {"score": rl.score, "confidence": rl.confidence, "probabilities": list(rl.probabilities)},
        "overfitting_concern": {"probability": of.noul},
        "declining_performance": {"probability": dp.noul},
        "stake_scaling_safe": {"probability": ss.noul},
        "recommendation": {"choice": rec.choice, "confidence": rec.confidence, "probabilities": rec.probabilities},
        "projected_return_12m": {"choice": pr.choice, "confidence": pr.confidence, "probabilities": pr.probabilities},
    }

    with open(os.path.join(BASE_DIR, "jev_analysis_results.json"), "w", encoding="utf-8") as f:
        json.dump(jev_output, f, indent=2, ensure_ascii=False)
    print("[OK] Resultados Jev salvos em 'jev_analysis_results.json'.\n")

except Exception as e:
    print(f"\n[ERRO] Falha na análise Jev: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
