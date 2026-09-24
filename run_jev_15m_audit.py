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
print("  🤖 CONSULTANDO IA JEV (TYPESAFE AI) SOBRE O TIMEFRAME DE 15 MINUTOS (KALSHI BTC 15M)")
print("=" * 90)

with open("nq_btc_15m_results.json", "r", encoding="utf-8") as f:
    res_15m = json.load(f)

state = f"""
EMPIRICAL RESEARCH AUDIT: INTEGRATING NASDAQ-100 (NQ/QQQ) INTO THE 15-MINUTE BTC TRADING ENGINE (KALSHI BTC 15M)

Target Architecture:
- Kalshi Regulated 15-Minute BTC Binary Contracts.
- Entry Trigger: Drift >= 3.5 bps at 450s (7.5m / midpoint of 15m window).
- Question: Does adding an NQ/QQQ 15m veto filter create a statistically valid edge, or should the trader 'forget it' (esqueço)?

EMPIRICAL 5-YEAR BACKTEST DATA ON 15-MINUTE BARS (112,019 Matched Bars from Aug 2019 to Aug 2024):
1. Contemporaneous Correlation on 15m:
   - Global (24/5): r = {res_15m['corr_global_15m']}
   - US Market Hours (13:30 - 20:00 UTC): r = {res_15m['corr_us_15m']}
2. Lead-Lag Correlation (NQ 15m candle t -> BTC 15m candle t+1):
   - Global: r = {res_15m['lead_lag_global_15m']}
   - US Hours: r = {res_15m['lead_lag_us_15m']}
3. Concordance on 15m candles:
   - NQ >= 10 bps: 49.9%
   - NQ >= 20 bps: 50.0%
   - NQ >= 30 bps: 50.2%
   - US Hours NQ >= 20 bps: 49.7%
4. Empirical Veto Impact on 97,093 signals:
   - Baseline Win Rate: {res_15m['baseline_wr_15m']}%
   - Filtered Win Rate: {res_15m['filtered_wr_15m']}% (Delta: +0.11%, well within standard error)
   - Vetoed trades: 41,441 trades (cuts volume by 42.7% for +0.11% WR)
"""

client = TypeSafeClient()

questions = {
    "verdict_15m_timeframe": Choice(
        instructions="Based on 112,019 15-minute bars showing r=0.0027 and 50% coin-flip concordance, should the trader implement QQQ/NQ filter on the 15-minute Kalshi bot, or FORGET IT ('esqueço')?",
        criteria={
            "forget_it_noise": "FORGET IT: 15-minute TradFi equity vs BTC is still pure microstructure noise (r=0.0027); cutting 42% of trades for +0.11% delta is spurious overfitting.",
            "implement_on_15m": "IMPLEMENT: Implement QQQ filter on the 15-minute bot.",
            "test_longer_timeframes": "PIVOT TO LONGER HORIZONS: Macro correlation only becomes actionable on 1-hour, 4-hour, or daily timeframes, not 15m."
        }
    ),
    "minimum_timeframe_for_tradfi_correlation": Choice(
        instructions="At what minimum timeframe does the macroeconomic correlation between Nasdaq-100 (QQQ) and Bitcoin become statistically actionable for algorithmic trading?",
        criteria={
            "one_hour_or_higher": "1-Hour to 4-Hour timeframe or higher (Daily macro trends)",
            "fifteen_minutes": "15-minute timeframe",
            "five_minutes": "5-minute timeframe"
        }
    ),
    "jev_advice_to_trader": Noul(
        instructions="Provide Jev's direct operational advice to the trader regarding whether to pursue TradFi feeds for short-duration binary options (5m/15m)."
    )
}

print("[*] Submetendo ao JEV...")
t0 = time.time()
response = client.system_one(state=state, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta do Jev recebida em {elapsed:.1f}s!\n")

q1 = response.answers["verdict_15m_timeframe"]
print(f"\n[1] VEREDITO PARA O 15 MINUTOS: {q1.choice.upper()} ({q1.confidence:.1%})")
for opt, prob in q1.probabilities.items():
    print(f"     • {opt}: {prob:.1%}")

q2 = response.answers["minimum_timeframe_for_tradfi_correlation"]
print(f"\n[2] TIMEFRAME MÍNIMO PARA CORRELAÇÃO TRADFI TER VALOR: {q2.choice.upper()} ({q2.confidence:.1%})")
for opt, prob in q2.probabilities.items():
    print(f"     • {opt}: {prob:.1%}")

q3 = response.answers["jev_advice_to_trader"]
print(f"\n[3] CONSELHO DO JEV:\n  {q3.noul}")

# Salvar em json
out = {
    "verdict_15m": q1.choice,
    "confidence_15m": q1.confidence,
    "probabilities_15m": q1.probabilities,
    "min_timeframe": q2.choice,
    "advice": q3.noul,
    "empirical_15m": res_15m
}
with open("jev_15m_qqq_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("\n[*] Auditoria de 15m salva em jev_15m_qqq_audit_response.json")
