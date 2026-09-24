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

print("\n" + "=" * 90)
print("  🤖 CONSULTANDO IA JEV (TYPESAFE AI) SOBRE ADICIONAR FILTRO QQQ/NQ NO BOT BTC 5M")
print("=" * 90)

# Load empirical findings
with open("nq_btc_correlation_summary.json", "r", encoding="utf-8") as f:
    corr_data = json.load(f)

with open("nq_btc_backtest_results.json", "r", encoding="utf-8") as f:
    backtest_data = json.load(f)

state = f"""
EMPIRICAL RESEARCH AUDIT: INTEGRATING NASDAQ-100 (NQ FUTURES / QQQ ETF) AS A VETO FILTER FOR BTC 5-MINUTE SNIPER

Target Architecture:
- Polymarket 5-Minute BTC Binary Prediction Markets (Settled via Chainlink / Pyth vs Binance spot).
- Entry Trigger: Midpoint drift >= 2.1 bps at 135s of the 300s window.
- Proposed Feature: If BTC signals UP (drift >= 2.1 bps), but QQQ / NQ is negative or diverging, veto the BTC entry (and vice versa for DOWN).

EMPIRICAL 5-YEAR BACKTEST DATA (329,033 Matched Concurrent 5-Minute Bars from Aug 2019 to Aug 2024):
1. Contemporaneous Correlation (Same 5m candle):
   - Global (24/5): r = {corr_data['contemporaneous_correlation_global']}
   - US Market Session (13:30 - 20:00 UTC, 78,203 bars): r = {corr_data['contemporaneous_correlation_us_hours']}
2. Lead-Lag Correlation (NQ candle t predicting BTC candle t+1):
   - Global: r = {corr_data['lead_lag_correlation_nq_to_btc_next_global']}
   - US Market Session: r = {corr_data['lead_lag_correlation_nq_to_btc_next_us_hours']}
3. Directional Concordance under Expressive NQ Moves (US Hours):
   - NQ move >= 5 bps (N=31,244): BTC same direction = {corr_data['concordance_by_nq_magnitude_us_hours']['>=5_bps']}%
   - NQ move >= 10 bps (N=15,160): BTC same direction = {corr_data['concordance_by_nq_magnitude_us_hours']['>=10_bps']}%
   - NQ move >= 20 bps (N=4,838): BTC same direction = {corr_data['concordance_by_nq_magnitude_us_hours']['>=20_bps']}%
   - NQ move >= 50 bps (N=458): BTC same direction = {corr_data['concordance_by_nq_magnitude_us_hours']['>=50_bps']}%
4. Empirical Veto Filter Results on 281,469 BTC 5m Signals:
   - Baseline Win Rate: {backtest_data['2.1_bps']['baseline_wr']}%
   - Filtered Win Rate (requiring NQ alignment): {backtest_data['2.1_bps']['filtered_wr']}% (Net Delta: {backtest_data['2.1_bps']['wr_delta_global']}%)
   - Trades eliminated: {backtest_data['2.1_bps']['vetoed_conflicts']:,} trades
   - Win Rate of the eliminated "conflict" trades: {backtest_data['2.1_bps']['conflict_wr']}% (Virtually identical to baseline)
   - US Hours Specific: Baseline {backtest_data['2.1_bps']['us_baseline_wr']}% vs Filtered {backtest_data['2.1_bps']['us_filtered_wr']}% (Delta: {backtest_data['2.1_bps']['us_wr_delta']}%)

Contrasting Context:
- SOL vs BTC correlation on 5m is > 0.85 (Crypto-to-crypto sharing identical Binance order books & market makers).
- NQ/QQQ vs BTC correlation on 5m is ~0.0048 (TradFi equity vs Crypto microstructure are decoupled at high frequencies).
"""

client = TypeSafeClient()

questions = {
    "qqq_5m_veto_decision": Choice(
        instructions="Based strictly on the 5-year empirical evidence (r=0.0048, 50% coin-flip concordance on 5m bars), should the live Polymarket BTC 5m bot implement a QQQ/NQ 5m veto filter?",
        criteria={
            "reject_5m_qqq_veto": "REJECT: Do not add QQQ/NQ 5m filter. At 5-minute horizons, TradFi noise does not predict BTC microstructure; vetoing would act as a random trade reducer without adding edge.",
            "approve_5m_qqq_veto_all_hours": "APPROVE: Implement QQQ/NQ veto across all trading hours.",
            "approve_5m_qqq_veto_us_hours_only": "APPROVE PARTIAL: Implement QQQ/NQ veto strictly during US regular trading hours (13:30 - 20:00 UTC).",
            "pivot_to_daily_macro_trend": "PIVOT: Use QQQ/NQ only as a daily macro regime indicator (>1% daily trend), not as a 5-minute intraday candle veto."
        }
    ),
    "tradfi_crypto_5m_decoupling_score": Score(
        instructions="Rate the level of decoupling between Bitcoin 5m price action and Nasdaq-100 5m price action on a scale from 1 (tightly coupled) to 5 (completely decoupled high-frequency microstructure).",
        criteria=[
            "Tightly Coupled (TradFi leads 5m BTC)",
            "Moderately Coupled",
            "Weak Coupling",
            "Largely Decoupled",
            "Completely Decoupled (5m noise is idiosyncratic to crypto)"
        ]
    ),
    "overfitting_and_latency_risk": Choice(
        instructions="What is the primary risk of adding an external TradFi API feed (QQQ/NQ) into the 135-second critical execution loop of the BTC sniper?",
        criteria={
            "latency_friction_and_spurious_veto": "Latency friction, external API point of failure, and spurious vetoes reducing trade frequency without improving win rate",
            "acceptable_risk": "Acceptable risk with negligible downsides",
            "underfitting_risk": "Underfitting risk by not including enough external macro assets"
        }
    ),
    "jev_verdict_noul": Noul(
        instructions="State Jev's probabilistic assessment that native crypto orderflow (Binance Taker Flow + CLOB L2) is mathematically superior to external TradFi stock feeds for 5-minute binary expiry trading."
    )
}

print("[*] Conectando ao modelo Jev (SystemOne) e submetendo dossiê quantitativo...")
t0 = time.time()
response = client.system_one(state=state, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta oficial do Jev recebida em {elapsed:.1f}s!\n")

print("=" * 90)
print("  📊 RESULTADOS OFICIAIS DO JEV (TYPESAFE AI)")
print("=" * 90)

q1 = response.answers["qqq_5m_veto_decision"]
print(f"\n[1] DECISÃO DO JEV SOBRE O FILTRO QQQ/NQ 5M:")
print(f"  ▶ Veredito do Jev: {q1.choice.upper()}")
print(f"  ▶ Confiança: {q1.confidence:.1%}")
print("  ▶ Distribuição de Probabilidades:")
for opt, prob in q1.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q2 = response.answers["tradfi_crypto_5m_decoupling_score"]
print(f"\n[2] NÍVEL DE DESACOPLAMENTO TRADFI VS CRIPTO (5 MINUTOS):")
print(f"  ▶ Score do Jev: {q2.score:.2f} / 5.00")
print(f"  ▶ Confiança: {q2.confidence:.1%}")

q3 = response.answers["overfitting_and_latency_risk"]
print(f"\n[3] RISCO DE LATÊNCIA E OVERFITTING:")
print(f"  ▶ Diagnóstico do Jev: {q3.choice.upper()}")
print(f"  ▶ Confiança: {q3.confidence:.1%}")
for opt, prob in q3.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q3.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q4 = response.answers["jev_verdict_noul"]
print(f"\n[4] CONFIANÇA DO JEV NO FLUXO NATIVO DE CRIPTO VS TRADFI:")
print(f"  ▶ Probabilidade Noul do Jev: {q4.noul:.1%}")

# Salvar relatório final
output = {
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
    },
    "empirical_evidence": {
        "bars_tested": 329033,
        "contemporaneous_correlation_5m": corr_data['contemporaneous_correlation_global'],
        "us_hours_correlation_5m": corr_data['contemporaneous_correlation_us_hours'],
        "lead_lag_correlation": corr_data['lead_lag_correlation_nq_to_btc_next_global'],
        "directional_concordance_us_hours": corr_data['concordance_by_nq_magnitude_us_hours']
    }
}

with open("jev_qqq_btc_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n" + "=" * 90)
print("  [*] AUDITORIA COMPLETA SALVA EM jev_qqq_btc_audit_response.json")
print("=" * 90)
