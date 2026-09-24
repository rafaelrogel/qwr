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

base_dir = os.path.join(os.getcwd(), 'climate_dataset')
temp_path = os.path.join(base_dir, 'global_temp_monthly.csv')
co2_path = os.path.join(base_dir, 'co2_monthly.csv')

print("=" * 90)
print("  📊 PROCESSANDO DATASETS DE CLIMA & TEMPERATURA (1850 - 2026) PARA O JEV")
print("=" * 90)

df_temp = pd.read_csv(temp_path)
df_co2 = pd.read_csv(co2_path)

# 1. Filtra dados do GISTEMP e GCAG
gcag = df_temp[df_temp['Source'] == 'GCAG'].copy()
gcag['Date'] = pd.to_datetime(gcag['Year'])
gcag = gcag.sort_values('Date').reset_index(drop=True)

# 2. Resumo da anomalia de temperatura
min_temp_year = gcag['Date'].min().strftime('%Y-%m')
max_temp_year = gcag['Date'].max().strftime('%Y-%m')
mean_temp_anomaly = gcag['Mean'].mean()
max_temp_anomaly = gcag['Mean'].max()
min_temp_anomaly = gcag['Mean'].min()

# 3. Tendência por década (Warming rate per decade)
gcag['year_num'] = gcag['Date'].dt.year + gcag['Date'].dt.month / 12.0
poly_recent = np.polyfit(gcag[gcag['Date'] >= '1970-01-01']['year_num'], gcag[gcag['Date'] >= '1970-01-01']['Mean'], 1)
warming_rate_per_decade = poly_recent[0] * 10.0  # °C por década

# 4. CO2 stats
df_co2['Date'] = pd.to_datetime(df_co2['Date'])
min_co2 = df_co2['Average'].min()
max_co2 = df_co2['Average'].max()
co2_start_date = df_co2['Date'].min().strftime('%Y-%m')
co2_end_date = df_co2['Date'].max().strftime('%Y-%m')

# Análise de anos mais quentes
gcag['year_only'] = gcag['Date'].dt.year
annual_avg = gcag.groupby('year_only')['Mean'].mean().reset_index()
top5_warmest_years = annual_avg.sort_values(by='Mean', ascending=False).head(5)
top5_warmest = [
    {"year": int(r['year_only']), "mean_anomaly_celsius": round(r['Mean'], 3)}
    for _, r in top5_warmest_years.iterrows()
]

summary_stats = {
    "temperature_series": {
        "source": "NOAA Global Historical Climatology Network (GCAG) & NASA GISTEMP",
        "coverage": f"{min_temp_year} to {max_temp_year} ({len(gcag)} monthly records)",
        "mean_anomaly": round(mean_temp_anomaly, 3),
        "min_anomaly": round(min_temp_anomaly, 3),
        "max_anomaly": round(max_temp_anomaly, 3),
        "warming_rate_since_1970_c_per_decade": round(warming_rate_per_decade, 3),
        "top_warmest_years_in_history": top5_warmest
    },
    "co2_atmospheric_series": {
        "source": "NOAA Mauna Loa Observatory (ESRL)",
        "coverage": f"{co2_start_date} to {co2_end_date} ({len(df_co2)} months)",
        "min_ppm": round(min_co2, 2),
        "max_ppm": round(max_co2, 2),
        "growth_ppm": round(max_co2 - min_co2, 2)
    }
}

print(f"[*] Estatísticas de Clima computadas:")
print(f"    Aquecimento global desde 1970: +{warming_rate_per_decade:.3f}°C por década")
print(f"    Anomalia máxima registrada: +{max_temp_anomaly:.2f}°C")
print(f"    CO2 Mauna Loa: de {min_co2:.1f} ppm (1958) para {max_co2:.1f} ppm (2026)")

# Prepara dossiê estruturado para o JEV
dossier = f"""
OFFICIAL DATASET AUDIT & IN-DEPTH QUANTITATIVE ANALYSIS REQUEST: GLOBAL CLIMATE & TEMPERATURE TIME SERIES
Source: DataHub (collections/climate-data) | NASA GISTEMP, NOAA GCAG & NOAA Mauna Loa CO2 Observatory.
Coverage: 176 continuous years (Jan 1850 to Jun 2026), 3,871 monthly records.

1. FULL EMPIRICAL DISTRIBUTION & METRICS:
{json.dumps(summary_stats, indent=2)}

2. KEY PHYSICAL & MATHEMATICAL PHENOMENA:
- Relentless Monotonic Secular Drift: Post-1970 global temperature anomaly exhibits an upward drift of +{warming_rate_per_decade:.3f}°C per decade, driven by exponential atmospheric CO2 accumulation (315 ppm to >426 ppm).
- Superimposed Cyclical Oscillations: El Niño-Southern Oscillation (ENSO) produces periodic spikes (+0.2°C to +0.4°C above baseline trend during El Niño phases) and cooling troughs during La Niña phases.
- Direct Coupling to Prediction Markets & Energy:
  * Kalshi lists binary markets: 'Will [Year] be the warmest year on record?', 'NASA Global Temperature anomaly > X.X°C', 'Degree-Days Milestones'.
  * Weather extremes (Heating Degree Days in winter, Cooling Degree Days in summer) directly govern the $3.88/MMBtu Natural Gas inventory drainage and electric grid peak power pricing.
"""

print("[*] Submetendo ao modelo Jev (SystemOne da TypeSafe AI)...")

client = TypeSafeClient()

questions = {
    "mathematical_nature_of_climate_time_series": Choice(
        instructions="From an econometric and quantitative time-series perspective, how should an algorithmic model classify global temperature anomaly data?",
        criteria={
            "deterministic_drift_with_enso_cycles": "Deterministic Linear/Exponential Drift + Cyclical ENSO: Highly predictable long-term positive drift (+0.19°C/decade) modulated by 3-7 year El Niño/La Niña oscillating wave harmonics.",
            "stationary_mean_reversion": "Stationary Mean Reversion: Fluctuations around a fixed historical mean with zero structural trend.",
            "pure_stochastic_random_walk": "Pure Stochastic Random Walk: Next month's temperature anomaly is mathematically unpredictable white noise."
        }
    ),
    "actionable_kalshi_climate_edge": Choice(
        instructions="What is the single most mathematically exploitable edge on Kalshi climate prediction markets (e.g. 'Warmest Year on Record' or 'Global Temp Anomaly > X.X°C')?",
        criteria={
            "enso_phase_arbitrage_on_annual_records": "ENSO Phase Arbitrage: Buying 'Warmest Year on Record' early when NOAA models forecast an emerging El Niño event, as retail traders systematically underprice the probability of new annual highs.",
            "naive_contrarian_betting": "Contrarian Betting: Betting on colder-than-normal global records to exploit long-shot odds.",
            "unexploitable_perfect_pricing": "Unexploitable: Climate scientists and hedge funds price temperature prediction markets with 100% efficiency."
        }
    ),
    "predictability_score_climate_events": Score(
        instructions="Rate the statistical predictability of macro annual global climate milestone contracts (e.g. Annual Temperature Anomaly above trend) compared to short-term financial assets on a scale of 1 to 5 (where 1 means low predictability like stock prices, and 5 means exceptionally high physical predictability governed by thermodynamics).",
        criteria=[
            "Low Predictability (Like daily stock returns)",
            "Moderate Predictability",
            "High Predictability",
            "Very High Predictability (Physics-constrained momentum)",
            "Deterministic Physical Inevitability"
        ]
    ),
    "jev_advice_on_climate_prediction_markets": Noul(
        instructions="State Jev's probabilistic assessment of whether automated algorithms exploiting climate thermodynamics and seasonal degree-days hold a persistent structural edge over human bettors on prediction platforms."
    )
}

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0
print(f"[OK] Resposta recebida do Jev em {elapsed:.1f}s!\n")

print("=" * 90)
print("  🤖 RESULTADOS DA AUDITORIA DO JEV SOBRE OS DADOS DE CLIMA (1850 - 2026)")
print("=" * 90)

q1 = response.answers["mathematical_nature_of_climate_time_series"]
print(f"\n[1] NATUREZA MATEMÁTICA DAS SÉRIES DE CLIMA:")
print(f"  ▶ Veredito do Jev: {q1.choice.upper()}")
print(f"  ▶ Confiança: {q1.confidence:.1%}")
for opt, prob in q1.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q1.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q2 = response.answers["actionable_kalshi_climate_edge"]
print(f"\n[2] MAIOR EDGE EM MERCADOS PREDITIVOS DE CLIMA (KALSHI):")
print(f"  ▶ Veredito do Jev: {q2.choice.upper()}")
print(f"  ▶ Confiança: {q2.confidence:.1%}")
for opt, prob in q2.probabilities.items():
    marker = " ◄◄◄ (ESCOLHA DO JEV)" if opt == q2.choice else ""
    print(f"     • {opt}: {prob:.1%}{marker}")

q3 = response.answers["predictability_score_climate_events"]
print(f"\n[3] SCORE DE PREVISIBILIDADE FÍSICA VS MERCADO FINANCEIRO:")
print(f"  ▶ Score do Jev: {q3.score:.2f} / 5.00")
print(f"  ▶ Confiança: {q3.confidence:.1%}")

q4 = response.answers["jev_advice_on_climate_prediction_markets"]
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
    "climate_statistics": summary_stats
}

with open("jev_climate_dataset_audit_response.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("\n[*] Auditoria completa de Clima salva em jev_climate_dataset_audit_response.json")
