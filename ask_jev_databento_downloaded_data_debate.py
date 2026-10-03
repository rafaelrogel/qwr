"""
DEBATE INTELECTUAL & QUANTITATIVO: AGY SYSTEM × JEV AI (TYPESAFE SYSTEMONE)
==========================================================================
Tema: Auditoria Filosófica e Microestrutural dos Dados Oficiais Baixados da CME Globex (Databento)
Amostras: 14.957 Velas de Natural Gas (NYMEX NG) e 6.691 Velas de S&P 500 (CME ES)
Data/Hora: 2026-09-27 23:55 UTC
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

from dotenv import load_dotenv
load_dotenv()

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
====================================================================================================
DOSSIÊ QUANTITATIVO DE ALTA FREQUÊNCIA: DADOS REAIS EXTRAÍDOS DA DATABENTO (CME GLOBEX GLBX.MDP3)
Data/Hora: 2026-09-27 23:55 UTC
Acervo Auditado: 1.438 arquivos de dados reais da CME Globex em 1 segundo e TBBO (Trades + BBO em nanossegundos).
Símbolos Principais: NYMEX Henry Hub Natural Gas (NG.c.0) e CME E-mini S&P 500 (ES.c.0).

1. RESULTADOS EMPÍRICOS EM NATURAL GAS (NYMEX NG.c.0 - 14.957 VELAS REAIS DE 15M):
   - Deslocamento aos 450s (Metade da Vela / Sweet-Spot):
     * Mediana (p50): $0.0050 / MMBtu (15.29 bps)
     * Percentil 75:  $0.0100 / MMBtu (29.97 bps)
     * Percentil 85:  $0.0140 / MMBtu (41.36 bps)
     * Percentil 90:  $0.0180 / MMBtu (51.04 bps)
     * Percentil 95:  $0.0250 / MMBtu (67.69 bps)
   - Taxa de Acerto Empírica (Win Rate) ao entrar aos 450s na direção do drift se |Delta| >= Deadband:
     * Deadband >= 5.0 bps:  79.24% WR (N = 12.098 velas | 80.9% dos ciclos)
     * Deadband >= 7.5 bps:  81.97% WR (N = 10.553 velas | 70.6% dos ciclos)
     * Deadband >= 10.0 bps: 83.45% WR (N = 9.692 velas | 64.8% dos ciclos) [Nosso código atual]
     * Deadband >= 12.5 bps: 84.82% WR (N = 8.595 velas | 57.5% dos ciclos)
     * Deadband >= 15.0 bps: 86.26% WR (N = 7.567 velas | 50.6% dos ciclos)
     * Deadband >= 20.0 bps: 88.71% WR (N = 5.954 velas | 39.8% dos ciclos)
   - O Fenômeno do Chaveamento Diurno de Liquidez (Diurnal Regime Switch):
     * 12:00 às 15:00 UTC (Abertura do Pregão Físico de NYMEX): O deslocamento médio aos 450s salta para 30.0 a 32.8 bps (mediana 22.0 a 26.0 bps)! Fluxo institucional maciço, rompimentos limpos.
     * 07:00 às 10:00 UTC (Transição Ásia/Europa): Deslocamento médio cai para 14.1 a 17.0 bps (mediana 10.0 bps). Ruído mecânico de baixa amplitude.

2. RESULTADOS EMPÍRICOS EM E-MINI S&P 500 (CME ES.c.0 - 6.691 VELAS DE 15M):
   - Taxa de Acerto Empírica ao entrar aos 450s:
     * Deadband >= 1.5 pts: 83.86% WR (N = 4.053 velas)
     * Deadband >= 2.5 pts: 87.95% WR (N = 2.714 velas)
     * Deadband >= 3.5 pts: 90.63% WR (N = 1.793 velas)
     * Deadband >= 5.0 pts: 93.19% WR (N = 969 velas)
     * Deadband >= 7.5 pts: 94.98% WR (N = 418 velas)
     * Deadband >= 10.0 pts: 96.57% WR (N = 204 velas)

3. MICROESTRUTURA TBBO (TRADES COM BBO SIMULTÂNEO EM NANOSSEGUNDOS):
   - Cada trade vem carimbado com: bid_px_00, ask_px_00, bid_sz_00, ask_sz_00, bid_ct_00, ask_ct_00.
   - Revela absorção passiva: quando compradores agressivos agridem o Ask mas o preço não sobe (limites institucionais absorvendo), prevendo exaustão antes do ponto de decisão.

Teses para Debate:
Tese A: O Sweet-Spot de 450s não é um acaso empírico; ele representa o colapso da incerteza do leilão contínuo da CME (efeito 'Bridge' de Brownian Bridge).
Tese B: Um Deadband Fixo é sub-ótimo. O Desk 5 deve modular o deadband conforme a hora UTC (10 bps na madrugada, 20 bps na abertura de NY).
Tese C: O futuro de ES na CME Globex oferece uma vantagem de latência estrutural sobre o índice à vista (cash SPX) na Kalshi, permitindo front-run preditivo antes que o oráculo recalcule as 500 ações.
====================================================================================================
"""

questions = {
    "sweet_spot_physics_explanation": Choice(
        instructions="Why does entering at exactly 450s (50% of the 15-minute candle) consistently produce an 83.5% to 93.2% win rate across both Natural Gas and S&P 500? What is the mathematical and market microstructure explanation for this persistence?",
        criteria={
            "brownian_bridge_drift_dominance": "Brownian Bridge & Drift Dominance: By t=450s, the accumulated directional drift exceeds the diffusion variance (sigma * sqrt(t_remaining)). The probability of the sign reversing over the remaining 450s drops exponentially under a pinned brownian bridge process.",
            "institutional_execution_exhaustion": "Institutional Execution Exhaustion: Institutional TWAP and VWAP algorithms execute primarily in the first half of the 15m window; once counter-trend passive liquidity is cleared, the remaining half exhibits momentum drift without opposing order flow.",
            "spurious_selection_bias": "Spurious Selection Bias: The 83-93% win rate is an artifact of conditional conditioning (|Delta| >= Deadband) and does not reflect an unconditional edge."
        }
    ),
    "diurnal_deadband_modulation_verdict": Choice(
        instructions="Should Desk 5 (Kalshi NatGas 15m LIVE) implement Diurnal Deadband Modulation (expanding deadband to 20.0 bps between 12:00-15:00 UTC and tightening to 10.0 bps during off-peak 07:00-10:00 UTC), or maintain a scale-invariant fixed floor ($0.0040 / 10.0 bps)?",
        criteria={
            "implement_diurnal_modulation": "Implement Diurnal Modulation: Natural gas volatility expands by more than 100% during the NY physical session (12-15h UTC). Demanding higher delta during peak hours filters out false breakout whipsaws, while lower delta in Asian sessions captures quiet clean drifts.",
            "maintain_fixed_scale_invariant_floor": "Maintain Fixed Scale-Invariant Floor: Adding time-of-day parameter regimes increases parameter fragility and risk of overfitting. The scale-invariant floor ($0.0040 / 10.0 bps) already dynamically adapts to price levels.",
            "hybrid_volatility_zscore": "Hybrid Volatility Z-Score: Normalize delta by real-time rolling Parkinson/Garman-Klass volatility rather than static UTC clock buckets."
        }
    ),
    "tbbo_microstructure_gain_score": Score(
        instructions="Score from 1.0 to 5.0 the theoretical and practical information gain of upgrading our 15m desks with TBBO order flow imbalance (CVD and Bid-Ask aggression volume) compared to relying purely on 1-second price delta.",
        criteria=[
            "1.0 - Negligible: At 15m horizon, price delta already captures 99% of order flow information.",
            "2.0 - Marginal: Adds slight nuance but mostly noise for binary options.",
            "3.0 - Moderate: Detects absorption on 15-20% of edge cases where price moves without aggressive volume.",
            "4.0 - High: Eliminates traps where low-volume spoofing creates artificial delta without institutional backing.",
            "5.0 - Optimal Institutional Edge: Transforms the system into a true microsecond order-flow predictive engine capable of anticipating price jumps."
        ]
    ),
    "cme_es_lead_lag_front_run_prob": Noul(
        instructions="What is JEV's probabilistic estimate (0.0 to 1.0) that using CME Globex ES futures 1-second momentum creates an authentic structural latency front-run against Kalshi's cash SPX settlement (KXINXU) during regular trading hours?"
    ),
    "master_synthesis_verdict": Choice(
        instructions="What is JEV's master synthesis recommendation after reviewing the empirical evidence from the 1,438 Databento files for our production fleet?",
        criteria={
            "institutional_grade_certified": "Institutional Grade Certified: The empirical evidence from 14,957 NG candles and 6,691 ES candles confirms the mathematical validity of the AGY 450s Sweet-Spot Architecture. Lock in the calibrated parameters ($0.0040 floor on NatGas, 4.0 pts on SPX) and allow capital compounding.",
            "restrict_to_us_session_only": "Restrict to US Session Only: Shut down overnight trading on commodities and equities; trade only when NYMEX and NYSE physical liquidity is active.",
            "expand_to_gold_live_immediately": "Promote Desk 9 Gold to LIVE immediately based on COMEX data."
        }
    )
}

print("=" * 80)
print(" SUBMETENDO DADOS EMPÍRICOS DA DATABENTO PARA DEBATE QUANTITATIVO COM A IA JEV...")
print("=" * 80)

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer e Debate do JEV concluídos em {elapsed:.2f}s!\n")

q1 = response.answers["sweet_spot_physics_explanation"]
q2 = response.answers["diurnal_deadband_modulation_verdict"]
q3 = response.answers["tbbo_microstructure_gain_score"]
q4 = response.answers["cme_es_lead_lag_front_run_prob"]
q5 = response.answers["master_synthesis_verdict"]

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_sweet_spot_physics": {"choice": q1.choice, "confidence": q1.confidence, "probabilities": q1.probabilities},
    "q2_diurnal_modulation": {"choice": q2.choice, "confidence": q2.confidence, "probabilities": q2.probabilities},
    "q3_tbbo_gain_score": {"score": q3.score, "confidence": q3.confidence},
    "q4_cme_lead_lag_prob": {"noul": q4.noul},
    "q5_master_synthesis": {"choice": q5.choice, "confidence": q5.confidence, "probabilities": q5.probabilities}
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_databento_empirical_debate_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("=" * 85)
print(f"1. A Física do Sweet-Spot de 450s: {q1.choice.upper()} ({q1.confidence:.1%} de confiança)")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Modulação Diurna de Deadband: {q2.choice.upper()} ({q2.confidence:.1%} de confiança)")
for k, v in q2.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n3. Pontuação de Ganho com Microestrutura TBBO (1-5): {q3.score:.2f} / 5.00 ({q3.confidence:.1%} de confiança)")

print(f"\n4. Probabilidade de Front-Run de Latência do ES sobre SPX Kalshi: {q4.noul:.1%}")

print(f"\n5. Veredito Geral de Síntese Institucional: {q5.choice.upper()} ({q5.confidence:.1%} de confiança)")
for k, v in q5.probabilities.items():
    print(f"   - {k}: {v:.1%}")
print("=" * 85)
