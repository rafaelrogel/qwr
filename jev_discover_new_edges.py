"""
=============================================================================
JEV 1.13.0 — MINERAÇÃO DE EDGES OCULTOS NO HISTÓRICO DE 9 ANOS DO BITCOIN
=============================================================================
Calcula matrizes estatísticas multidimensionais em 9 anos (318.570 janelas):
1. Efeito Hora do Dia (Sessão Asiática, Londres, Nova York, Fechamento)
2. Efeito Dia da Semana (Dias úteis vs Fins de semana sem CME Futures)
3. Faixas de Drift em Pontos-Base (Micro-drift vs Médio vs Explosivo)
4. Alinhamento com a Vela Anterior (Continuação vs Pullback)
5. Regime de Volatilidade (Compressão vs Expansão)
Envia o dataset multidimensional ao modelo Jev (SystemOne) para descoberta de edges.
=============================================================================
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

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
CACHE_FILE = os.path.join(BASE_DIR, "btc_5m_9y_cache.json")

print("\n" + "=" * 105)
print("  ⛏️ MINERANDO DADOS DE 9 ANOS PARA DESCOBERTA DE EDGES OCULTOS COM O JEV")
print("=" * 105)

print("[*] Carregando cache de 9 anos (955.699 velas de 5m)...")
with open(CACHE_FILE, "r", encoding="utf-8") as f:
    klines_5m = json.load(f)

candles = {k[0]: {"open": k[1], "high": k[2], "low": k[3], "close": k[4]} for k in klines_5m}
all_ts = sorted(candles.keys())
ts_15m = [ts for ts in all_ts if ts % 900 == 0]

print(f"[OK] {len(ts_15m):,} janelas de 15m indexadas. Processando matrizes estatísticas...")

# Matrizes multidimensionais
hourly_stats = {h: {"trades": 0, "wins": 0} for h in range(24)}
dow_stats = {d: {"trades": 0, "wins": 0} for d in ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]}
dow_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
bps_buckets = {
    "2.0_to_3.5_bps": {"trades": 0, "wins": 0},
    "3.5_to_5.0_bps": {"trades": 0, "wins": 0},
    "5.0_to_8.0_bps": {"trades": 0, "wins": 0},
    "8.0_to_15.0_bps": {"trades": 0, "wins": 0},
    "over_15.0_bps": {"trades": 0, "wins": 0}
}
prior_alignment = {
    "trend_continuation (prior_same_dir)": {"trades": 0, "wins": 0},
    "pullback_rebound (prior_opposite_dir)": {"trades": 0, "wins": 0}
}

for i in range(1, len(ts_15m)):
    ts = ts_15m[i]
    prev_ts = ts_15m[i-1]

    c0 = candles.get(ts)
    c1 = candles.get(ts + 300)
    c2 = candles.get(ts + 600)
    if not (c0 and c1 and c2): continue

    prev_c0 = candles.get(prev_ts)
    prev_c2 = candles.get(prev_ts + 600)
    prev_dir = "UP" if (prev_c0 and prev_c2 and prev_c2["close"] >= prev_c0["open"]) else "DOWN"

    dt = datetime.utcfromtimestamp(ts)
    hour = dt.hour
    dow = dow_names[dt.weekday()]

    strike = c0["open"]
    spot_450s = (c1["open"] + c1["close"]) / 2.0
    final = c2["close"]
    winner = "UP" if final >= strike else "DOWN"

    delta = spot_450s - strike
    abs_delta = abs(delta)
    bps = (abs_delta / strike) * 10000

    if bps < 2.0: continue

    side = "UP" if delta > 0 else "DOWN"
    is_win = (side == winner)

    # 1. Hora
    hourly_stats[hour]["trades"] += 1
    if is_win: hourly_stats[hour]["wins"] += 1

    # 2. Dia da semana
    dow_stats[dow]["trades"] += 1
    if is_win: dow_stats[dow]["wins"] += 1

    # 3. Faixa de BPS
    if bps < 3.5: b_name = "2.0_to_3.5_bps"
    elif bps < 5.0: b_name = "3.5_to_5.0_bps"
    elif bps < 8.0: b_name = "5.0_to_8.0_bps"
    elif bps < 15.0: b_name = "8.0_to_15.0_bps"
    else: b_name = "over_15.0_bps"
    bps_buckets[b_name]["trades"] += 1
    if is_win: bps_buckets[b_name]["wins"] += 1

    # 4. Alinhamento com vela anterior
    if side == prev_dir:
        prior_alignment["trend_continuation (prior_same_dir)"]["trades"] += 1
        if is_win: prior_alignment["trend_continuation (prior_same_dir)"]["wins"] += 1
    else:
        prior_alignment["pullback_rebound (prior_opposite_dir)"]["trades"] += 1
        if is_win: prior_alignment["pullback_rebound (prior_opposite_dir)"]["wins"] += 1

# Formata as tabelas percentuais
hourly_summary = {
    f"{h:02d}:00 UTC": f"{s['wins']}/{s['trades']} ({(s['wins']/max(s['trades'],1)*100):.1f}%)"
    for h, s in hourly_stats.items()
}
dow_summary = {
    d: f"{s['wins']}/{s['trades']} ({(s['wins']/max(s['trades'],1)*100):.1f}%)"
    for d, s in dow_stats.items()
}
bps_summary = {
    k: f"{s['wins']}/{s['trades']} ({(s['wins']/max(s['trades'],1)*100):.1f}%)"
    for k, s in bps_buckets.items()
}
prior_summary = {
    k: f"{s['wins']}/{s['trades']} ({(s['wins']/max(s['trades'],1)*100):.1f}%)"
    for k, s in prior_alignment.items()
}

dossier_edges = {
    "sample_scope": "9 Full Years (Aug 2017 - Sep 2026), 318,570 15m windows, BTC/USD",
    "edge_dimension_1_bps_magnitude": bps_summary,
    "edge_dimension_2_prior_candle_alignment": prior_summary,
    "edge_dimension_3_day_of_week_efficiency": dow_summary,
    "edge_dimension_4_hourly_utc_sessions": hourly_summary
}

state_str = json.dumps(dossier_edges, indent=2)
print(f"[OK] Matrizes calculadas. Dossiê para o Jev: {len(state_str):,} caracteres.")
print("[*] Enviando para o modelo 'jev-1.13.0' da TypeSafe AI para Caça de Edges Ocultos...\n")

t0 = time.time()
client = TypeSafeClient()

questions = {
    "most_lucrative_undiscovered_edge": Choice(
        instructions="Based on these 9-year empirical matrices, which dimension represents the strongest, most exploitable UNDISCOVERED edge to maximize profit?",
        criteria={
            "bps_sweet_spot_filtering": "BPS Drift Sweet-Spot - Restricting entries strictly to 3.5 to 8.0 bps eliminates false noise while capturing high-conviction moves",
            "prior_candle_trend_alignment": "Prior Candle Trend Alignment - Trading only in the direction of the previous candle yields higher follow-through persistence",
            "us_london_session_focus": "Session Timing - Focusing execution during peak liquidity hours (London/NY overlap 12:00 - 18:00 UTC) reduces adverse wicks",
            "weekend_vs_weekday_arbitrage": "Weekday vs Weekend Filter - Trading only on weekdays when CME Futures and institutional volume anchor momentum"
        }
    ),
    "best_bps_range_for_highest_ev": Choice(
        instructions="Looking at the BPS magnitude distribution (2.0 to >15 bps), which bracket delivers the highest risk-adjusted Expected Value (EV)?",
        criteria={
            "bps_3_5_to_5_0": "3.5 to 5.0 bps - ideal balance between cheap ticket cost (<=55c) and 80%+ win rate",
            "bps_5_0_to_8_0": "5.0 to 8.0 bps - strongest momentum conviction with manageable pricing",
            "bps_over_15_0": "Over 15.0 bps - highest raw win rate, but tickets are often overpriced"
        }
    ),
    "trend_continuation_vs_pullback": Choice(
        instructions="Does the engine gain an edge by requiring alignment with the previous 15m candle, or should it remain independent?",
        criteria={
            "require_trend_continuation": "Require trend continuation - entering when previous candle closed in the same direction adds statistical edge",
            "independent_candle_drift": "Keep independent - intra-candle 450s drift already carries sufficient momentum without filtering out good trades"
        }
    ),
    "session_hour_edge": Choice(
        instructions="Is there a statistically significant hour-of-day edge, or is Bitcoin's 24/7 market largely time-invariant?",
        criteria={
            "time_invariant": "Time-invariant - win rate remains remarkably stable (within 1-2pp) across all 24 hours of the day",
            "ny_session_superior": "NY Session (13:00 - 20:00 UTC) is superior due to higher institutional follow-through",
            "asian_session_fragile": "Asian Session (00:00 - 06:00 UTC) is more prone to mean-reversion and false breakouts"
        }
    ),
    "jev_top_optimization_recommendation": Choice(
        instructions="If the developer can implement ONE single new edge discovered from this 9-year dataset, what should it be?",
        criteria={
            "cap_drift_at_8_bps": "Cap drift entry at 8.0 bps (trade only between 2.1 and 8.0 bps) to completely eliminate paying for overpriced shares",
            "add_prior_candle_filter": "Add prior-candle trend confirmation filter",
            "filter_out_weekends": "Disable trading on weekends to avoid low-liquidity slippage",
            "maintain_current_rules": "Maintain current rules without adding complexity - the existing filter is already near-optimal"
        }
    ),
    "hidden_edge_impact_rating": Score(
        instructions="Rate the overall potential impact of these newly discovered edges on increasing the strategy's Sharpe ratio from 1 to 5.",
        criteria=["Insignificant / Noise", "Minor Improvement", "Noticeable Edge Boost", "Major Alpha Generation", "Game-Changing Transformation"]
    ),
    "jev_secret_alpha_confidence": Noul(
        instructions="Provide Jev's confidence level that capping the upper drift at 8.0 bps will increase net profit by avoiding the cauda cara (expensive tail)."
    )
}

response = client.system_one(state=state_str, questions=questions)
elapsed = time.time() - t0

print(f"[OK] Mineração do Jev concluída em {elapsed:.2f} segundos!\n")

print("=" * 105)
print("  💎 EDGES OCULTOS DESCOBERTOS PELO JEV (TYPESAFE AI — DADOS 9 ANOS)")
print("=" * 105)
print(f"  • Modelo Jev:                    {getattr(response, 'model', 'jev-1.13.0')}")
print(f"  • Request ID:                    {getattr(response, 'request_id', 'N/A')}")
if hasattr(response, 'usage'):
    print(f"  • Tokens de Entrada Analisados:  {response.usage.input_tokens:,} tokens")
    print(f"  • Tokens de Saída Gerados:       {response.usage.output_tokens:,} tokens")
print("-" * 105)

# 1. Maior Edge Oculto
e1 = response.answers["most_lucrative_undiscovered_edge"]
print(f"\n1. O MAIOR EDGE OCULTO NÃO DESCOBERTO NOS 9 ANOS:")
print(f"   ▶ Descoberta do Jev: {e1.choice.upper()}")
print(f"   ▶ Confiança: {e1.confidence:.1%}")
print("   ▶ Distribuição de Probabilidades:")
for opt, prob in e1.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == e1.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# 2. Melhor Faixa de BPS
e2 = response.answers["best_bps_range_for_highest_ev"]
print(f"\n2. FAIXA EXATA DE DRIFT (BPS) COM MAIOR VALOR ESPERADO (EV):")
print(f"   ▶ Faixa Selecionada: {e2.choice.upper()}")
print(f"   ▶ Confiança: {e2.confidence:.1%}")
print("   ▶ Distribuição de Probabilidades:")
for opt, prob in e2.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == e2.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# 3. Tendência vs Independência
e3 = response.answers["trend_continuation_vs_pullback"]
print(f"\n3. ALINHAMENTO COM A VELA ANTERIOR (TENDÊNCIA vs INDEPENDENTE):")
print(f"   ▶ Diagnóstico do Jev: {e3.choice.upper()}")
print(f"   ▶ Confiança: {e3.confidence:.1%}")
print("   ▶ Distribuição de Probabilidades:")
for opt, prob in e3.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == e3.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# 4. Efeito Hora do Dia
e4 = response.answers["session_hour_edge"]
print(f"\n4. EFEITO HORA DO DIA (SESSÃO NY vs LONDRES vs ÁSIA):")
print(f"   ▶ Veredito do Jev: {e4.choice.upper()}")
print(f"   ▶ Confiança: {e4.confidence:.1%}")
print("   ▶ Distribuição de Probabilidades:")
for opt, prob in e4.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == e4.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# 5. A Recomendação nº 1 do Jev
e5 = response.answers["jev_top_optimization_recommendation"]
print(f"\n5. A MELHORIA ÚNICA Nº 1 RECOMENDADA PELO JEV:")
print(f"   ▶ Ação Recomendada: {e5.choice.upper()}")
print(f"   ▶ Confiança: {e5.confidence:.1%}")
print("   ▶ Distribuição de Probabilidades:")
for opt, prob in e5.probabilities.items():
    m = " ◄◄◄ (ESCOLHA DO JEV)" if opt == e5.choice else ""
    print(f"     • {opt}: {prob:.1%}{m}")

# 6. Score de Impacto
e6 = response.answers["hidden_edge_impact_rating"]
print(f"\n6. IMPACTO ESTIMADO DESTE NOVO EDGE NO SHARPE:")
print(f"   ▶ Score: {e6.score:.2f} / 5.00 (Confiança: {e6.confidence:.1%})")

# 7. Confiança Noul
e7 = response.answers["jev_secret_alpha_confidence"]
print(f"\n7. CONFIANÇA PROBABILÍSTICA NO TETO DE 8.0 BPS:")
print(f"   ▶ Probabilidade Calculada pelo Jev: {e7.noul:.1%}")

print("\n" + "=" * 105 + "\n")

# Salva resultado em JSON
with open(os.path.join(BASE_DIR, "jev_discovered_edges.json"), "w", encoding="utf-8") as f:
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
        },
        "matrices": dossier_edges
    }, f, indent=2, ensure_ascii=False)
