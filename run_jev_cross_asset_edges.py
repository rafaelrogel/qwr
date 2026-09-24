"""
=============================================================================
JEV 1.13.0 — AUDITORIA E DESCOBERTA DE EDGES MULTI-DATASETS
=============================================================================
Envia as matrizes empíricas consolidadas de todos os outros datasets:
1. Ouro Spot (XAU/USD 5m - 500.000 velas)
2. Índices Acionários (ES S&P 500 & NQ Nasdaq 100 Futuros - 680.000 barras)
3. Forex EUR/USD (189.000 barras)
4. Microestrutura Polymarket Multi-Ativo (BTC, ETH, SOL, XRP nos parquets da PolyResearch)
5. 13F Hedge Funds Institucionais

Ao motor de probabilidade calibrada da TypeSafe AI (jev-1.13.0).
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
MATRIX_FILE = os.path.join(BASE_DIR, "all_datasets_matrix_summary.json")

print("\n" + "=" * 105)
print("  🌐 JEV AI — BUSCA DE EDGES OCULTOS EM TODOS OS OUTROS DATASETS (CROSS-ASSET)")
print("=" * 105)

with open(MATRIX_FILE, "r", encoding="utf-8") as f:
    matrices = json.load(f)

context_str = json.dumps(matrices, indent=2)
print(f"[*] Dossiê consolidado com {len(context_str):,} caracteres.")
print(f"[*] Datasets incluídos: Gold 5m (XAU), S&P 500 (ES), Nasdaq (NQ), EURUSD, Polymarket (BTC/ETH/SOL/XRP), 13F Funds.")
print("[*] Enviando requisição para o motor Jev (jev-1.13.0)...\n")

client = TypeSafeClient()

questions = {
    "most_exploitable_cross_asset_edge": Choice(
        instructions="Analyzing across all provided datasets (Gold 5m, ES/NQ Equity Futures, EURUSD Forex, and Polymarket Multi-Asset Orderbooks), which represents the single most exploitable, high-Sharpe edge?",
        criteria={
            "equity_futures_clean_drift": "Equity Futures Drift (ES/NQ) - 94.6% to 97.3% continuation at >=2.0 bps with lower tail-risk than crypto",
            "gold_spot_drift_arbitrage": "Gold Spot Drift (XAU/USD) - 88.0% to 91.7% win rate at >=3.5 bps with 53.3% candle-to-candle mean reversion",
            "polymarket_sol_xrp_inefficiency": "Polymarket Altcoin Inefficiency (SOL/XRP) - wider spreads ($0.014) and 33% higher microprice disparity than BTC create retail mispricings",
            "multi_market_binary_basket": "Cross-Asset Multi-Binary Basket - Trading BTC, ETH, SOL and Gold simultaneously to smooth equity curve"
        }
    ),
    "best_altcoin_expansion_target": Choice(
        instructions="Comparing the Polymarket microstructure data across BTC, ETH, SOL, and XRP: Which asset offers the best combination of liquidity and exploitable retail flow?",
        criteria={
            "sol_solana_markets": "Solana (SOL) - High microprice disparity ($0.0040) with sufficient depth (36k shares) to fill orders without massive slippage",
            "eth_ethereum_markets": "Ethereum (ETH) - Tightest spread ($0.0102) and deep book (42k shares), most similar to BTC stability",
            "xrp_ripple_markets": "XRP - Highest spread and widest book gaps, but shallower depth (20k-30k shares) creates fill risk",
            "remain_btc_exclusive": "Remain BTC Exclusive - BTC has 2x higher depth (73k shares) preventing liquidity traps"
        }
    ),
    "gold_and_equities_dichotomy": Choice(
        instructions="In Gold and Equities, consecutive candle returns show 51.5% to 53.3% mean reversion, yet intra-candle midpoint drift shows 88% to 97% continuation. What is the optimal quant strategy for this structure?",
        criteria={
            "fade_prior_candle_ride_intra_drift": "Fade prior candle, ride intra-candle drift: Enter on midpoint momentum especially when counter to previous bar close",
            "pure_intra_candle_momentum": "Pure intra-candle momentum: Ignore prior candle entirely and execute purely on drift magnitude",
            "mean_reversion_scalp_only": "Mean reversion scalping: Fade every large candle close at the boundary"
        }
    ),
    "cross_asset_diversification_benefit": Score(
        instructions="Rate the diversification and Sharpe boost of expanding this binary prediction engine to Solana and Gold.",
        criteria=[
            "No benefit / Distraction",
            "Minor benefit",
            "Noticeable diversification boost",
            "Major Sharpe expansion",
            "Transformational multi-asset alpha"
        ]
    ),
    "top_strategic_recommendation": Choice(
        instructions="What is the single most actionable next step Rafael should implement based on these diverse datasets?",
        criteria={
            "add_solana_to_polymarket_bot": "Add Solana (SOL 5m/15m) to Polymarket bot - exploit higher microprice disparity and retail imbalance",
            "scale_btc_parameters_first": "Focus strictly on scaling BTC Polymarket/Kalshi engines using the 9-year discovered edges first",
            "develop_gold_binary_engine": "Develop a Gold 5m binary predictor using the 91.7% drift persistence edge",
            "build_sp500_nasdaq_engine": "Build S&P 500 / Nasdaq futures 5m momentum engine (97% continuation)"
        }
    ),
    "jev_confidence_cross_asset": Noul(
        instructions="Assess confidence in the structural stability of these cross-asset momentum edges across macro regimes."
    )
}

t0 = time.time()
response = client.system_one(
    state=f"CROSS-ASSET EMPIRICAL FINANCIAL DATASETS (Gold 5m, S&P 500 ES, Nasdaq NQ, EURUSD, Polymarket Multi-Asset Orderbooks BTC/ETH/SOL/XRP):\n{context_str}",
    questions=questions
)
duration = time.time() - t0

print(f"[OK] Resposta recebida do Jev em {duration:.2f}s!")
print(f"Request ID: {response.request_id}")
print(f"Tokens: Input={response.usage.input_tokens} | Output={response.usage.output_tokens}\n")

# Extrair respostas
answers = {}
for q_name, ans in response.answers.items():
    ans_dict = {
        "choice": getattr(ans, "choice", None),
        "score": getattr(ans, "score", None),
        "confidence": getattr(ans, "confidence", None),
        "probabilities": getattr(ans, "probabilities", None),
        "noul": getattr(ans, "noul", None)
    }
    answers[q_name] = ans_dict

out_data = {
    "model": "jev-1.13.0",
    "request_id": response.request_id,
    "usage": {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens
    },
    "answers": answers,
    "datasets_analyzed": {
        "gold_5m": "500,000 candles (2003-2026), 91.7% win rate at >=5 bps drift",
        "es_sp500_5y": "353,206 bars, 97.3% win rate at >=5 bps drift",
        "nq_nasdaq_5y": "329,458 bars, 97.3% win rate at >=5 bps drift",
        "eurusd_1m": "189,680 bars",
        "polymarket_crypto": "BTC, ETH, SOL, XRP 5m/15m tick orderbook samples"
    }
}

out_path = os.path.join(BASE_DIR, "jev_cross_asset_edges_response.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out_data, f, indent=2)

print(json.dumps(answers, indent=2))
print(f"\n[OK] Resposta completa gravada em: {out_path}")
