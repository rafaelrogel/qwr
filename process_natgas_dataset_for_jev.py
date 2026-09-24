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

base_dir = os.path.join(os.getcwd(), 'natural_gas_dataset')
daily_path = os.path.join(base_dir, 'daily.csv')
monthly_path = os.path.join(base_dir, 'monthly.csv')

print("=" * 90)
print("  📊 PROCESSANDO DATASET COMPLETO DE GÁS NATURAL (1997 - 2026) PARA O JEV")
print("=" * 90)

df_daily = pd.read_csv(daily_path)
df_daily['Date'] = pd.to_datetime(df_daily['Date'])
df_daily = df_daily.sort_values('Date').reset_index(drop=True)
df_daily['Price'] = pd.to_numeric(df_daily['Price'], errors='coerce')
df_daily = df_daily.dropna(subset=['Price'])

df_monthly = pd.read_csv(monthly_path)
df_monthly['Price'] = pd.to_numeric(df_monthly['Price'], errors='coerce')
df_monthly = df_monthly.dropna(subset=['Price'])

n_days = len(df_daily)
min_date = df_daily['Date'].min().strftime('%Y-%m-%d')
max_date = df_daily['Date'].max().strftime('%Y-%m-%d')

p = df_daily['Price']

mean_p = p.mean()
median_p = p.median()
std_p = p.std()
min_p = p.min()
max_p = p.max()
skew_p = p.skew()
kurt_p = p.kurtosis()

# Percentis
p10 = p.quantile(0.10)
p25 = p.quantile(0.25)
p50 = p.quantile(0.50)
p75 = p.quantile(0.75)
p90 = p.quantile(0.90)
p95 = p.quantile(0.95)
p99 = p.quantile(0.99)

# Análise de Sazonalidade por Mês do Ano
df_daily['month'] = df_daily['Date'].dt.month
monthly_seasonality = df_daily.groupby('month')['Price'].agg(['mean', 'std']).reset_index()
month_names = {
    1: 'Jan (Winter)', 2: 'Feb (Winter)', 3: 'Mar (End Winter)', 4: 'Apr (Shoulder)',
    5: 'May (Shoulder)', 6: 'Jun (Summer Cooling)', 7: 'Jul (Peak Summer)', 8: 'Aug (Peak Summer)',
    9: 'Sep (Shoulder)', 10: 'Oct (Pre-Winter Storage)', 11: 'Nov (Early Winter)', 12: 'Dec (Winter Heating)'
}
monthly_seasonality['month_name'] = monthly_seasonality['month'].map(month_names)

# Top 10 Picos Históricos
top10_spikes = df_daily.sort_values(by='Price', ascending=False).head(10)[['Date', 'Price']]
top10_list = [
    {"date": r['Date'].strftime('%Y-%m-%d'), "price_usd_per_mmbtu": round(r['Price'], 2)}
    for _, r in top10_spikes.iterrows()
]

# Regimes Históricos
# 1. Pre-Shale / Deregulation Era (1997 - 2008)
# 2. Shale Revolution Gluta (2009 - 2020)
# 3. Post-COVID / LNG Export & Energy Crisis (2021 - 2026)
regimes = {
    "Pre_Shale_Boom (1997-2008)": df_daily[(df_daily['Date'] >= '1997-01-01') & (df_daily['Date'] <= '2008-12-31')]['Price'],
    "Shale_Glut_Abundance (2009-2020)": df_daily[(df_daily['Date'] >= '2009-01-01') & (df_daily['Date'] <= '2020-12-31')]['Price'],
    "LNG_Export_Globalized_Era (2021-2026)": df_daily[df_daily['Date'] >= '2021-01-01']['Price']
}

regime_stats = {}
for name, s in regimes.items():
    regime_stats[name] = {
        "mean_price": round(s.mean(), 2),
        "median_price": round(s.median(), 2),
        "min_price": round(s.min(), 2),
        "max_price": round(s.max(), 2),
        "volatility_std": round(s.std(), 2)
    }

stats_summary = {
    "sample_period": f"{min_date} to {max_date} ({n_days:,} daily spot prices)",
    "mean_price_usd_mmbtu": round(mean_p, 2),
    "median_price": round(median_p, 2),
    "std_dev": round(std_p, 2),
    "min_price": round(min_p, 2),
    "max_price": round(max_p, 2),
    "skewness": round(skew_p, 2),
    "kurtosis": round(kurt_p, 2),
    "percentiles": {
        "10th": round(p10, 2),
        "25th": round(p25, 2),
        "50th_median": round(p50, 2),
        "75th": round(p75, 2),
        "90th": round(p90, 2),
        "95th": round(p95, 2),
        "99th": round(p99, 2)
    },
    "historical_regimes": regime_stats,
    "top_10_all_time_spikes": top10_list,
    "monthly_seasonality": {
        r['month_name']: {"mean": round(r['mean'], 2), "std": round(r['std'], 2)}
        for _, r in monthly_seasonality.iterrows()
    }
}

print(f"[*] Estatísticas computadas:")
print(f"    Média: ${mean_p:.2f} | Mediana: ${median_p:.2f} | Mín: ${min_p:.2f} | Máx: ${max_p:.2f}")
print(f"    Curtose extrema: {kurt_p:.2f} (Efeito 'Widowmaker' / Cauda pesada)")

# Prepara dossiê quantitativo estruturado para o JEV
dossier = f"""
OFFICIAL DATASET AUDIT & IN-DEPTH QUANTITATIVE ANALYSIS REQUEST: HENRY HUB NATURAL GAS SPOT PRICES
Source: DataHub (core/natural-gas) | U.S. Energy Information Administration (EIA).
Coverage: 30 continuous years (Jan 1997 to Sep 2026), 5,689 daily market sessions.

1. FULL EMPIRICAL DISTRIBUTION & METRICS:
{json.dumps(stats_summary, indent=2)}

2. KEY PHYSICAL & MARKET PHENOMENA IN THE DATASET:
- Extreme Kurtosis & Asymmetric Spikes (Kurtosis = {kurt_p:.2f}, Skew = {skew_p:.2f}): Known on Wall Street as "The Widowmaker". Prices can surge 300% in days during polar vortex events or hurricane disruptions, then collapse when storage refills.
- Three Structural Regimes:
  * Pre-Shale (1997-2008): Scarcity pricing, average $5.49/MMBtu, peak $15.38 (Katrina).
  * Shale Glut (2009-2020): Hydraulic fracturing & horizontal drilling flooded US supply, compressing prices to average $3.03/MMBtu (floor $1.33 in 2020).
  * Globalized LNG & War Era (2021-2026): US export terminals linked Henry Hub to European TTF and Asian JKM, restoring volatility with peaks up to $9.85 in 2022.
- Rigorous Seasonality: Highest prices consistently occur in December/January/February (winter heating peak) and July/August (summer cooling power burn), while April/October shoulder months exhibit cyclical troughs.
- Modern Power Demand Driver: Natural gas is now the marginal fuel source powering electricity grids for AI data centers (hyperscalers) and Bitcoin proof-of-work mining facilities.
"""

print("[*] Submetendo ao modelo Jev (SystemOne da TypeSafe AI)...")

client = TypeSafeClient()

questions = {
    "mathematical_nature_of_natural_gas": Choice(
        instructions="From an econometric and quantitative perspective, what is the fundamental mathematical nature of Natural Gas across this 30-year dataset?",
        criteria={
            "mean_reverting_seasonally_bounded": "Mean-Reverting Seasonally Bounded Commodity: Dominated by physics, weather, and underground storage capacity; relentlessly reverts to marginal extraction cost ($2.00-$3.50), punctuated by extreme episodic supply shocks.",
            "unconstrained_inflation_asset": "Unconstrained Inflation Asset: Follows long-term sovereign debt and fiat devaluation similar to gold.",
            "untradable_tail_chaos": "Pure Tail Chaos / Non-stationary: The 'Widowmaker' kurtosis makes directional algorithmic trading mathematically unviable without physical storage delivery capability."
        }
    ),
    "actionable_quant_edge_natgas": Choice(
        instructions="What is the single most mathematically robust algorithmic trading edge when backtesting on Natural Gas data?",
        criteria={
            "calendar_seasonality_and_storage_spreads": "Calendar Seasonality & Storage Inventory Arbitrage: Trading the seasonal winter-summer spread (March vs April 'Widowmaker' spread) conditioned on EIA underground storage deficit/surplus.",
            "simple_trend_following": "Simple Trend Following: Buying upside breakouts regardless of season.",
            "shorting_volatility_unhedged": "Shorting Spikes Unhedged: Betting that every winter spike will immediately mean-revert."
        }
    ),
    "ai_datacenter_and_crypto_power_score": Score(
        instructions="Rate the strategic importance of Natural Gas as the base-load energy backbone for the expansion of AI Datacenters and Bitcoin Mining infrastructure on a scale from 1 to 5 (where 1 means irrelevant/fully displaced by renewables, and 5 means indispensable mission-critical base-load fuel).",
        criteria=[
            "Irrelevant / Displaced by Renewables",
            "Minor Marginal Component",
            "Moderate Regional Importance",
            "Highly Critical Base-load Fuel",
            "Indispensable Mission-Critical Infrastructure Anchor"
        ]
    ),
    "jev_advice_to_algorithmic_traders": Noul(
        instructions="State Jev's probabilistic assessment of whether a retail quant trader should trade pure directional Henry Hub outright futures vs calendar spreads / equity proxies."
    )
}

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta recebida do Jev em {elapsed:.1f}s!\n")

print("=" * 90)
print("  🤖 RESULTADOS DA AUDITORIA DO JEV SOBRE O GÁS NATURAL (1997 - 2026)")
print("=" * 90)

q1 = response.answers["mathematical_nature_of_natural_gas"]
print(f"\n[1] NATUREZA MATEMÁTICA DO GÁS NATURAL:")
print(f"  ▶ Veredito do Jev: {q1.choice.upper()}")
print(f"  ▶ Confiança: {q1.confidence:.1%}")
for opt, prob in q1.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q2 = response.answers["actionable_quant_edge_natgas"]
print(f"\n[2] MAIOR EDGE QUANTITATIVO NO GÁS NATURAL:")
print(f"  ▶ Veredito do Jev: {q2.choice.upper()}")
print(f"  ▶ Confiança: {q2.confidence:.1%}")
for opt, prob in q2.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q2.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q3 = response.answers["ai_datacenter_and_crypto_power_score"]
print(f"\n[3] IMPORTÂNCIA DO GÁS NATURAL PARA IA E CRIPTO (DATA CENTERS & ENERGIA):")
print(f"  ▶ Score do Jev: {q3.score:.2f} / 5.00")
print(f"  ▶ Confiança: {q3.confidence:.1%}")

q4 = response.answers["jev_advice_to_algorithmic_traders"]
print(f"\n[4] CONSELHO PROBABILÍSTICO DO JEV:")
print(f"  ▶ Noul do Jev: {q4.noul:.1%}")

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
    "natural_gas_statistics": stats_summary
}

with open("jev_natgas_dataset_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n[*] Auditoria completa salva em jev_natgas_dataset_audit_response.json")
