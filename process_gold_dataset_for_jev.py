import os
import sys
import json
import time
import pandas as pd
import numpy as np

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

base_dir = os.path.join(os.getcwd(), 'gold_prices_dataset')
annual_path = os.path.join(base_dir, 'annual.csv')
monthly_path = os.path.join(base_dir, 'monthly.csv')

print("=" * 90)
print("  📊 PROCESSANDO DATASET COMPLETO DE OURO (1833 - 2026) PARA O JEV")
print("=" * 90)

df_annual = pd.read_csv(annual_path)
df_monthly = pd.read_csv(monthly_path)

print(f"[*] Registros anuais carregados: {len(df_annual)} anos ({df_annual['Date'].min()} a {df_annual['Date'].max()})")
print(f"[*] Registros mensais carregados: {len(df_monthly)} meses ({df_monthly['Date'].min()} a {df_monthly['Date'].max()})")

# Estatísticas por regimes históricos
# 1. Classical Gold Standard (1833 - 1933)
# 2. Bretton Woods Era (1934 - 1971)
# 3. Post-Nixon Fiat Era (1971 - Present)
df_annual['Return'] = df_annual['Price'].pct_change()

regimes = {
    "Classical_Gold_Standard (1833-1933)": df_annual[(df_annual['Date'] >= 1833) & (df_annual['Date'] <= 1933)],
    "Bretton_Woods_Fixed (1934-1971)": df_annual[(df_annual['Date'] >= 1934) & (df_annual['Date'] <= 1971)],
    "Fiat_Free_Float (1971-2025)": df_annual[(df_annual['Date'] >= 1971) & (df_annual['Date'] <= 2025)],
    "Modern_Era_21st_Century (2000-2025)": df_annual[(df_annual['Date'] >= 2000) & (df_annual['Date'] <= 2025)],
    "Recent_Expansion (2020-2026)": df_monthly[df_monthly['Date'] >= '2020-01']
}

regime_stats = {}
for name, data in regimes.items():
    if 'Date' in data.columns and isinstance(data['Date'].iloc[0], (int, np.integer)):
        start_p = data['Price'].iloc[0]
        end_p = data['Price'].iloc[-1]
        n_years = len(data)
        cagr = (end_p / start_p) ** (1 / max(n_years - 1, 1)) - 1
        vol = data['Return'].std()
        regime_stats[name] = {
            "start_year": int(data['Date'].iloc[0]),
            "end_year": int(data['Date'].iloc[-1]),
            "start_price_usd": float(start_p),
            "end_price_usd": float(end_p),
            "total_return_pct": round(((end_p - start_p) / start_p) * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "annual_volatility_pct": round(vol * 100, 2) if not pd.isna(vol) else 0.0
        }
    else:
        # Monthly slice
        start_p = data['Price'].iloc[0]
        end_p = data['Price'].iloc[-1]
        regime_stats[name] = {
            "start_date": str(data['Date'].iloc[0]),
            "end_date": str(data['Date'].iloc[-1]),
            "start_price_usd": float(start_p),
            "end_price_usd": float(end_p),
            "total_gain_pct": round(((end_p - start_p) / start_p) * 100, 2)
        }

# Prepara o arquivo anual completo em formato CSV textual para enviar na íntegra
with open(annual_path, "r", encoding="utf-8") as f:
    annual_raw_csv = f.read()

# Prepara dossiê quantitativo estruturado
dossier = f"""
OFFICIAL DATASET AUDIT & IN-DEPTH QUANTITATIVE ANALYSIS REQUEST: GLOBAL GOLD PRICES (1833 - 2026)
Source: GitHub (datasets/gold-prices) | World Bank Commodity Markets ("Pink Sheet") & Timothy Green Historical Records.
Time Coverage: 193 continuous years (Annual 1833-2025) and 2,325 monthly observations (Jan 1833 to Aug 2026).

1. REGIME BREAKDOWN & EMPIRICAL METRICS:
{json.dumps(regime_stats, indent=2)}

2. KEY MONETARY & EMPIRICAL PHENOMENA IN THE DATASET:
- Period 1833-1933 (Fixed Standard): Price pegged at $18.93 to $20.67/oz for 100 years. Annualized volatility was virtually 0.0%.
- 1934 FDR Revaluation: Executive Order 6102 and Gold Reserve Act pegged price to $35.00/oz (+69.3% overnight revaluation).
- 1971 Nixon Shock: Termination of Bretton Woods gold convertibility. Gold transitioned from monetary peg to a free-floating global macro asset.
- 1971-1980 Stagflation Boom: Price erupted from $35.00 to an annual average of $612.56/oz (+1,650% gain, CAGR > 37%).
- 1980-2000 Disinflation & Dot-Com Bear Market: 20-year structural drawdown from $612 down to $279/oz (-54.4% nominal drawdown).
- 2001-2011 Commodity Supercycle & Great Financial Crisis: Gold surged from $270 to $1,569/oz (CAGR 19.2%).
- 2020-2026 Sovereign Debt & Central Bank Reserve Accumulation: Price expanded from $1,500/oz to over $4,400-$5,000/oz (+194% gain).

3. COMPLETE ANNUAL HISTORICAL DATASET VERBATIM (1833 to 2025):
```csv
{annual_raw_csv.strip()}
```

4. RECENT MONTHLY TRAJECTORY SAMPLES (2024-2026 World Bank Pink Sheet):
{df_monthly.tail(24).to_string(index=False)}
"""

print(f"[*] Dossiê analítico preparado ({len(dossier):,} caracteres).")
print("[*] Submetendo ao modelo Jev (SystemOne da TypeSafe AI)...")

client = TypeSafeClient()

questions = {
    "macro_regime_nature_of_gold": Choice(
        instructions="Based on this 193-year dataset (1833-2026), how does Jev classify the long-term mathematical behavior of gold in the post-1971 fiat era?",
        criteria={
            "monetary_debasement_hedge": "Pure Monetary Debasement & Sovereign Debt Expansion Hedge: Gold behaves as an inverse shadow index of global fiat supply and sovereign debt growth.",
            "cyclical_commodity_speculation": "Cyclical Commodity Speculation: Gold acts like an industrial or speculative commodity subject to 10-20 year boom-bust supply-demand cycles.",
            "stagnant_dead_capital": "Stagnant Capital: Long drawdowns (e.g. 1980-2000) negate its efficacy as a wealth builder compared to equity equities."
        }
    ),
    "gold_vs_bitcoin_store_of_value": Choice(
        instructions="Comparing this 193-year physical gold track record with digital assets (Bitcoin), what is Jev's quantitative view on their role as macro hedges?",
        criteria={
            "complementary_dual_hedge": "Complementary Dual-Hedge: Physical gold serves as sovereign central bank reserve collateral, while Bitcoin captures high-beta digital liquidity expansion.",
            "bitcoin_superior_absorption": "Bitcoin Superior Absorption: Bitcoin's strict 21M supply cap and digital mobility will progressively demonetize gold over a multi-decade horizon.",
            "gold_unrivaled_durability": "Gold Unrivaled Durability: 193+ years of sovereign continuity and physical tangibility cannot be replicated by crypto code."
        }
    ),
    "current_valuation_regime_score": Score(
        instructions="Rate the current 2024-2026 gold pricing regime ($4,000-$5,000/oz) on a scale from 1 to 5, where 1 means extremely overbought bubble and 5 means fundamentally justified structural re-pricing due to global de-dollarization and debt expansion.",
        criteria=[
            "Severe Speculative Bubble",
            "Moderately Overextended",
            "Fair Value Range",
            "Fundamentally Justified Structural Shift",
            "Historic Multi-Decade Sovereign Supercycle"
        ]
    ),
    "jev_deep_insights_gold": Noul(
        instructions="State Jev's quantitative probabilistic assessment of whether gold remains an essential portfolio allocation for preserving real purchasing power over the next decade."
    )
}

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta recebida do Jev em {elapsed:.1f}s!\n")

print("=" * 90)
print("  🤖 RESULTADOS DA AUDITORIA DO JEV SOBRE O DATASET DE OURO (1833 - 2026)")
print("=" * 90)

q1 = response.answers["macro_regime_nature_of_gold"]
print(f"\n[1] NATUREZA MATEMÁTICA DO OURO (PÓS-1971):")
print(f"  ▶ Veredito do Jev: {q1.choice.upper()}")
print(f"  ▶ Confiança: {q1.confidence:.1%}")
for opt, prob in q1.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q2 = response.answers["gold_vs_bitcoin_store_of_value"]
print(f"\n[2] OURO FÍSICO VS BITCOIN (RESERVA DE VALOR):")
print(f"  ▶ Veredito do Jev: {q2.choice.upper()}")
print(f"  ▶ Confiança: {q2.confidence:.1%}")
for opt, prob in q2.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q2.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q3 = response.answers["current_valuation_regime_score"]
print(f"\n[3] AVALIAÇÃO DA PRECIFICAÇÃO ATUAL ($4.000 - $5.000 / oz):")
print(f"  ▶ Score do Jev: {q3.score:.2f} / 5.00")
print(f"  ▶ Confiança: {q3.confidence:.1%}")

q4 = response.answers["jev_deep_insights_gold"]
print(f"\n[4] PROBABILIDADE DO JEV (PRESERVAÇÃO DE PODER DE COMPRA):")
print(f"  ▶ Confiança Noul do Jev: {q4.noul:.1%}")

# Salva arquivo JSON
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
    "regime_statistics": regime_stats
}

with open("jev_gold_dataset_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n[*] Auditoria completa salva em jev_gold_dataset_audit_response.json")
