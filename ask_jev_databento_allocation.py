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
DOSSIÊ QUANTITATIVO: ALOCAÇÃO ÓTIMA DE $125 USD EM CRÉDITOS HISTÓRICOS NO DATABENTO PARA O AGY SYSTEM
Data/Hora: 2026-09-27 22:35 UTC
Orçamento: $125.00 USD em créditos na Databento (sem taxa mensal para dados históricos, cobrado por byte/GB descompactado em DBN).
Contexto do Sistema: O AGY Trading System opera 11 desks algorítmicas ativas:
  - 4 Desks LIVE (Dinheiro Real): Desk 1 (Polymarket BTC 5m), Desk 2 (Polymarket SOL 5m), Desk 3 (Kalshi BTC 15m), Desk 5 (Kalshi NatGas 15m KXNATGAS15M).
  - 7 Desks PAPER / SCANNER: Desk 4 (Kalshi NatGas EIA Semanal), Desk 6 (Yield Harvester Poly), Desk 7 (Cross-Market Macro Arb Poly/Kalshi), Desk 8 (Polymarket ETH 5m), Desk 9 (Kalshi Gold 15m KXGOLD15M), Desk 10 (Binance USD-M Futures Microstructure), Desk 11 (Kalshi SPX 15m KXINXU).

Dados já existentes no acervo local (Custo zero):
  1. Dukascopy Bank SA: 917.891 velas M1/M15/H1 (BTC, ETH, Gold, Nasdaq, Oil, NatGas, Forex de 2000 a 2026).
  2. HistData.com: 1.087 arquivos anuais M1 (~400 milhões de barras de 66 ativos).
  3. Binance USD-M Futures: 50GB de dados tick-by-tick (CVD, aggTrades, BookTicker OBI de BTC/ETH/SOL).

Gargalos Atuais do Sistema:
  - Desk 5 (NatGas 15m - LIVE): O oráculo Kalshi liquida por Pyth (Commodities.Index.NATGAS/USD), cujo subjacente institucional é o futuro de Henry Hub na NYMEX (NG no CME Globex). Atualmente o bot consulta cotações via Yahoo/Pyth. Não temos o tick-by-tick real da NYMEX (order flow, book imbalance, saltos no leilão).
  - Desk 11 (SPX 15m - PAPER): Kalshi liquida por cash SPX, mas o E-mini S&P 500 (ES no CME Globex) lidera o SPX físico em 500ms a 5 segundos. Operar 15m sem a microestrutura de ES é operar com atraso de oráculo.
  - Desk 9 (Gold 15m - PAPER): O oráculo Pyth liquida por COMEX Gold (GC no Globex).
  - Esquema de Dados Databento:
    * MBO (L3 full order book): Extremamente pesado (10-30 GB/mês por símbolo). $125 esgotaria em poucas semanas de ES.
    * MBP-10 (L2 10 níveis): Médio.
    * MBP-1 (L1 BBO updates + trades): Microestrutura completa de topo de livro.
    * TBBO (Trades com BBO simultâneo): Compacto e ultra-eficiente. Cada trade carimbado com o melhor Bid/Ask e tamanhos.
    * OHLCV-1s (Barras de 1 segundo): Custo irrisório (centavos por ano). Permite multi-ano de lead-lag e calibragem de Kalman/deadband.

Candidatos de Alocação dos $125:
  Candidato 1: Pacote NYMEX Henry Hub Natural Gas (NG) no GLBX.MDP3 (TBBO + OHLCV-1s de 1-2 anos). Fortalece diretamente a Desk 5 (que opera DINHEIRO REAL com 93.8% WR).
  Candidato 2: Pacote CME E-mini S&P 500 (ES) no GLBX.MDP3 (TBBO dos últimos 3-6 meses + OHLCV-1s de 2 anos). Resolve o lead-lag preditivo de 15m para Desk 11.
  Candidato 3: Pacote Multi-Asset OHLCV-1s (NG, GC, ES, MBT - 3 anos completos) + Amostras TBBO em dias de alta volatilidade/EIA/FOMC.
  Candidato 4: Pacote OPRA / CBOE Options para GEX (Gamma Exposure) do SPX / QQQ para modular o regime de volatilidade de todas as desks.
====================================================================================================
"""

questions = {
    "optimal_asset_target": Choice(
        instructions="Considering that Desk 5 (Kalshi NatGas 15m) is already trading REAL MONEY, Desk 11 (SPX 15m) is in paper mode needing lead-lag data, and Desk 1/2/3 already have 50GB of Binance tick data, which target asset should receive the highest allocation of the $125 Databento credit?",
        criteria={
            "nymex_natgas_priority": "NYMEX Henry Hub Natural Gas (NG): Desk 5 is live with real money. Natural gas has unique physical inventory gap dynamics, extreme jump-diffusion, and low retail noise. Calibrating tick-level order flow on NG protects real capital and optimizes entry sizing.",
            "cme_emini_spx_priority": "CME E-mini S&P 500 (ES): The cash SPX has zero price discovery; ES futures lead SPX by hundreds of milliseconds to seconds. Without ES tick data, Desk 11 cannot compete against institutional arbitrageurs.",
            "multi_asset_portfolio_approach": "Multi-Asset Split: Do not put 100% into a single asset. Split the $125 across NG (NatGas), GC (Gold), and ES (SPX) using compact schemas (TBBO / OHLCV-1s) to enrich multiple desks simultaneously.",
            "opra_options_gex_priority": "OPRA / Options Gamma Exposure: Market-maker gamma flips dictate whether breakouts succeed or fail across the entire market."
        }
    ),
    "optimal_schema_selection": Choice(
        instructions="Databento charges per uncompressed byte. MBO (L3) is massive and expensive, while OHLCV-1s is ultra-cheap and TBBO captures tick trades with prevailing BBO. Which schema combination maximizes the Information-to-Cost Ratio (ICR) for our $125?",
        criteria={
            "tbbo_plus_ohlcv_1s_hybrid": "TBBO + OHLCV-1s Hybrid: OHLCV-1s provides multi-year macro lead-lag and volatility distribution for pennies, while TBBO captures microstructure aggression, trade toxicity, and effective spread without the wasteful bloat of full MBO.",
            "pure_mbp_10_recent_window": "Pure MBP-10 (L2): Focus on the top 10 levels of book depth for the last 60 days, sacrificing historical duration for depth profile.",
            "pure_mbo_event_sniper": "Pure MBO on Event Days: Download only specific FOMC, CPI, and EIA report days in full L3 Market-by-Order.",
            "pure_ohlcv_1s_decade": "Pure OHLCV-1s Maximization: Download 5+ years of 1-second bars across all CME commodities and equities."
        }
    ),
    "information_gain_score_natgas": Score(
        instructions="Rate from 1.0 to 5.0 the expected Information Gain and Sharpe impact of feeding Desk 5 (Kalshi NatGas 15m) with authentic NYMEX Henry Hub CME Globex TBBO/1s data vs relying on Yahoo/Pyth delayed feeds.",
        criteria=[
            "1.0 - Negligible gain: Pyth already tracks Henry Hub sufficiently for a 15m binary option.",
            "2.0 - Marginal: Slight improvement in entry price, but not worth the effort.",
            "3.0 - Moderate: Clarifies exact bid-ask bounce and fills gaps during EIA inventory releases.",
            "4.0 - High: Eliminates stale quote risk, detects institutional absorption pre-breakout, and refines the 10.0 bps deadband.",
            "5.0 - Transformative Institutional Edge: Transforms Desk 5 into an ultra-low-latency institutional taker that anticipates Kalshi oracle adjustments."
        ]
    ),
    "spx_lead_lag_edge_probability": Noul(
        instructions="What is Jev's probabilistic estimate (0.0 to 1.0) that utilizing CME E-mini ES 1-second price action provides statistically significant predictive lead over Kalshi's KXINXU cash SPX settlements at the 15-minute horizon?"
    ),
    "recommended_action_plan": Choice(
        instructions="What is JEV's definitive prescriptive roadmap for downloading and integrating the $125 of Databento data into the AGY repository?",
        criteria={
            "execute_targeted_ng_es_extraction": "Execute Targeted NG & ES Extraction: Allocate ~$60 to NYMEX NG (1 year of OHLCV-1s + key months of TBBO) and ~$65 to CME ES (1 year of OHLCV-1s + high-volatility TBBO periods), creating dedicated parquet tick caches in scratch.",
            "all_in_natgas_live_desk": "All-in on NatGas: Commit 100% of the $125 to NYMEX Natural Gas (NG) to maximize depth and duration for the only non-crypto desk trading real capital.",
            "all_in_spx_high_beta": "All-in on ES/SPX: Commit 100% to CME ES, building a premier high-frequency index engine.",
            "reserve_credits_for_live_streaming": "Reserve Credits for Live Streaming: Do not spend on historical data; save credits to feed live Databento WebSockets into the trading loops."
        }
    )
}

print("=" * 80)
print(" ENVIANDO DOSSIÊ DATABENTO ($125 CRÉDITOS) PARA AUDITORIA FORMAL DA IA JEV...")
print("=" * 80)

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

q1 = response.answers["optimal_asset_target"]
q2 = response.answers["optimal_schema_selection"]
q3 = response.answers["information_gain_score_natgas"]
q4 = response.answers["spx_lead_lag_edge_probability"]
q5 = response.answers["recommended_action_plan"]

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_optimal_asset": {"choice": q1.choice, "confidence": q1.confidence, "probabilities": q1.probabilities},
    "q2_optimal_schema": {"choice": q2.choice, "confidence": q2.confidence, "probabilities": q2.probabilities},
    "q3_natgas_gain_score": {"score": q3.score, "confidence": q3.confidence},
    "q4_spx_lead_lag_prob": {"noul": q4.noul},
    "q5_recommended_plan": {"choice": q5.choice, "confidence": q5.confidence, "probabilities": q5.probabilities}
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_databento_allocation_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("=" * 85)
print(f"1. Ativo Alvo Prioritário: {q1.choice.upper()} ({q1.confidence:.1%} de confiança)")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Esquema Ótimo de Dados: {q2.choice.upper()} ({q2.confidence:.1%} de confiança)")
for k, v in q2.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n3. Pontuação de Ganho de Informação para NatGas (1-5): {q3.score:.2f} / 5.00 ({q3.confidence:.1%} de confiança)")

print(f"\n4. Probabilidade de Lead-Lag Preditivo do ES sobre SPX 15m: {q4.noul:.1%}")

print(f"\n5. Plano de Ação Recomendado: {q5.choice.upper()} ({q5.confidence:.1%} de confiança)")
for k, v in q5.probabilities.items():
    print(f"   - {k}: {v:.1%}")
print("=" * 85)
