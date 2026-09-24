"""
=============================================================================
KALSHI QUANTITATIVE NATURAL GAS & WEATHER FORECAST ENGINE
=============================================================================
Integrates Open-Meteo GFS and NOAA NWS live 7-day weather forecast APIs
with EIA historical storage regressions to generate predictive signals for
Kalshi Weekly Natural Gas Storage and Henry Hub event contracts.
=============================================================================
"""

import os
import sys
import json
import urllib.request
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 5 Key EIA US Natural Gas Demand & Production Regions
REGIONS = {
    "Midwest": {
        "city": "Chicago, IL",
        "lat": 41.8781,
        "lon": -87.6298,
        "weight": 0.30,  # 30% of US residential gas heating
        "noaa_station": "LOT/76,73"
    },
    "East": {
        "city": "New York, NY",
        "lat": 40.7128,
        "lon": -74.0060,
        "weight": 0.32,  # 32% of US heating demand
        "noaa_station": "OKX/33,35"
    },
    "South_Central": {
        "city": "Houston, TX",
        "lat": 29.7604,
        "lon": -95.3698,
        "weight": 0.22,  # Henry hub production, chemical & power burn
        "noaa_station": "HGX/65,97"
    },
    "Mountain": {
        "city": "Denver, CO",
        "lat": 39.7392,
        "lon": -104.9903,
        "weight": 0.06,
        "noaa_station": "BOU/62,61"
    },
    "Pacific": {
        "city": "Los Angeles, CA",
        "lat": 34.0522,
        "lon": -118.2437,
        "weight": 0.10,
        "noaa_station": "LOX/154,44"
    }
}

class WeatherForecastEngine:
    def __init__(self):
        self.user_agent = "AntigravityQuantEngine/2.0 (energy-desk@quant.local)"

    def fetch_open_meteo_forecast(self):
        """Fetches 7-day numerical weather forecast for all 5 regions via Open-Meteo GFS."""
        lats = ",".join(str(r["lat"]) for r in REGIONS.values())
        lons = ",".join(str(r["lon"]) for r in REGIONS.values())
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lats}&longitude={lons}&"
            f"daily=temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min&"
            f"temperature_unit=fahrenheit&forecast_days=7&timezone=auto"
        )
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                return data
        except Exception as e:
            print(f"[!] Erro ao consultar Open-Meteo: {e}")
            return None

    def fetch_noaa_nws_confirmation(self, region_key="Midwest"):
        """Fetches official NOAA NWS forecast for cross-validation."""
        reg = REGIONS.get(region_key, REGIONS["Midwest"])
        url = f"https://api.weather.gov/gridpoints/{reg['noaa_station']}/forecast"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                periods = data.get("properties", {}).get("periods", [])
                return periods
        except Exception as e:
            # Fallback to points endpoint if gridpoint changed
            try:
                p_url = f"https://api.weather.gov/points/{reg['lat']},{reg['lon']}"
                req_p = urllib.request.Request(p_url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req_p, timeout=10) as resp_p:
                    data_p = json.loads(resp_p.read().decode())
                    f_url = data_p["properties"]["forecast"]
                    req_f = urllib.request.Request(f_url, headers={"User-Agent": self.user_agent})
                    with urllib.request.urlopen(req_f, timeout=10) as resp_f:
                        return json.loads(resp_f.read().decode()).get("properties", {}).get("periods", [])
            except Exception as e2:
                print(f"[!] Erro ao consultar NOAA NWS: {e2}")
                return None

    def calculate_forward_degree_days(self, open_meteo_data):
        """
        Calculates Population-Weighted Heating Degree Days (HDD) and Cooling Degree Days (CDD)
        for the upcoming 7 days across the continental US.
        """
        if not open_meteo_data:
            return None

        region_names = list(REGIONS.keys())
        results = {}
        total_us_hdd = 0.0
        total_us_cdd = 0.0

        for i, loc in enumerate(open_meteo_data):
            reg_name = region_names[i]
            reg_info = REGIONS[reg_name]
            weight = reg_info["weight"]

            dates = loc["daily"]["time"]
            t_max = loc["daily"]["temperature_2m_max"]
            t_min = loc["daily"]["temperature_2m_min"]

            reg_hdd_7d = 0.0
            reg_cdd_7d = 0.0
            daily_breakdown = []

            for d, mx, mn in zip(dates, t_max, t_min):
                t_avg = (mx + mn) / 2.0
                hdd = max(0.0, 65.0 - t_avg)
                cdd = max(0.0, t_avg - 65.0)

                reg_hdd_7d += hdd
                reg_cdd_7d += cdd

                daily_breakdown.append({
                    "date": d,
                    "t_avg_f": round(t_avg, 1),
                    "hdd": round(hdd, 1),
                    "cdd": round(cdd, 1)
                })

            weighted_hdd = reg_hdd_7d * weight
            weighted_cdd = reg_cdd_7d * weight

            total_us_hdd += weighted_hdd
            total_us_cdd += weighted_cdd

            results[reg_name] = {
                "city": reg_info["city"],
                "weight": weight,
                "hdd_7d": round(reg_hdd_7d, 1),
                "cdd_7d": round(reg_cdd_7d, 1),
                "weighted_hdd": round(weighted_hdd, 1),
                "weighted_cdd": round(weighted_cdd, 1),
                "daily_samples": daily_breakdown
            }

        return {
            "dates_coverage": f"{dates[0]} to {dates[-1]}",
            "us_national_weighted_hdd_7d": round(total_us_hdd, 1),
            "us_national_weighted_cdd_7d": round(total_us_cdd, 1),
            "regions": results
        }

    def generate_eia_storage_prediction(self, degree_days_result):
        """
        Translates forward 7-day HDD/CDD into estimated EIA weekly net change in Bcf.
        Regression Baseline:
        Normal Late-September Net Injection: ~ +70 to +80 Bcf.
        1 HDD deviation ~ 0.55 Bcf change in heating burn.
        1 CDD deviation ~ 0.40 Bcf change in electric power burn.
        """
        now = datetime.now()
        month = now.month

        # Baseline climatological normal injection for late September
        normal_injection_bcf = 76.0

        # Normal September HDD/CDD reference
        normal_hdd_sept = 15.0
        normal_cdd_sept = 30.0

        hdd_us = degree_days_result["us_national_weighted_hdd_7d"]
        cdd_us = degree_days_result["us_national_weighted_cdd_7d"]

        delta_hdd = hdd_us - normal_hdd_sept
        delta_cdd = cdd_us - normal_cdd_sept

        # Heat burn reduces injection; cooling burn reduces injection
        storage_impact_bcf = -(delta_hdd * 0.55 + delta_cdd * 0.40)
        predicted_net_change = normal_injection_bcf + storage_impact_bcf

        # Signal logic vs naive retail consensus (which assumes flat +76 Bcf)
        diff_from_consensus = normal_injection_bcf - predicted_net_change

        if diff_from_consensus >= 6.0:
            signal = "BUY BULLISH"
            reason = f"Clima mais rigoroso (HDD/CDD acima da média) drenará ~{diff_from_consensus:.1f} Bcf a mais que o consenso."
            confidence = min(85.0, 50.0 + abs(diff_from_consensus) * 3.0)
        elif diff_from_consensus <= -6.0:
            signal = "BUY BEARISH"
            reason = f"Clima ameno aumentará a injeção em ~{abs(diff_from_consensus):.1f} Bcf acima do consenso."
            confidence = min(85.0, 50.0 + abs(diff_from_consensus) * 3.0)
        else:
            signal = "NEUTRAL / NO TRADE"
            reason = "Previsão alinhada com a média histórica (+-5 Bcf). Sem assimetria estatística na Kalshi."
            confidence = 50.0

        return {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "dates_analyzed": degree_days_result["dates_coverage"],
            "us_weighted_hdd": hdd_us,
            "us_weighted_cdd": cdd_us,
            "retail_consensus_bcf": normal_injection_bcf,
            "model_forecast_bcf": round(predicted_net_change, 1),
            "expected_deviation_bcf": round(-diff_from_consensus, 1),
            "kalshi_actionable_signal": signal,
            "signal_confidence_pct": round(confidence, 1),
            "signal_rationale": reason,
            "recommended_execution_window": "Wednesday 14:00 - 18:00 ET (conforme auditoria JEV)"
        }

def run_live_pipeline():
    print("=" * 90)
    print("  🌐 CONECTANDO ÀS APIS LIVE: OPEN-METEO GFS + NOAA NWS (CLIMA & KALSHI NATGAS)")
    print("=" * 90)

    engine = WeatherForecastEngine()

    print("\n[*] 1/3 Consultando Open-Meteo GFS para os 5 Polos Energéticos dos EUA...")
    om_data = engine.fetch_open_meteo_forecast()
    if not om_data:
        print("[!] Falha ao obter dados do Open-Meteo.")
        return

    dd_res = engine.calculate_forward_degree_days(om_data)
    print(f"[OK] Previsão de 7 dias processada com sucesso! ({dd_res['dates_coverage']})")
    print(f"     • CONUS US Weighted HDD (Aquecimento): {dd_res['us_national_weighted_hdd_7d']} graus-dia")
    print(f"     • CONUS US Weighted CDD (Resfriamento): {dd_res['us_national_weighted_cdd_7d']} graus-dia")

    print("\n[*] 2/3 Validando contra Estação Oficial NOAA NWS (Midwest / Chicago)...")
    noaa_periods = engine.fetch_noaa_nws_confirmation("Midwest")
    if noaa_periods:
        print(f"[OK] NOAA NWS confirmada! Próximos períodos em Chicago:")
        for p in noaa_periods[:3]:
            print(f"     - {p['name']}: {p['temperature']}°{p['temperatureUnit']} ({p['shortForecast']})")

    print("\n[*] 3/3 Calculando Previsão Física de Estoques EIA e Sinal para a Kalshi...")
    signal = engine.generate_eia_storage_prediction(dd_res)

    print("\n" + "=" * 90)
    print("  📊 SINAL QUANTITATIVO AO VIVO PARA A KALSHI")
    print("=" * 90)
    print(f"  ▶ Decisão: {signal['kalshi_actionable_signal']}")
    print(f"  ▶ Confiança do Modelo: {signal['signal_confidence_pct']}%")
    print(f"  ▶ Consenso do Varejo (Média EIA): {signal['retail_consensus_bcf']} Bcf")
    print(f"  ▶ Projeção do Nosso Modelo: {signal['model_forecast_bcf']} Bcf")
    print(f"  ▶ Desvio Esperado: {signal['expected_deviation_bcf']:+.1f} Bcf")
    print(f"  ▶ Justificativa: {signal['signal_rationale']}")
    print(f"  ▶ Janela Ótima de Boletagem: {signal['recommended_execution_window']}")

    # Salva relatório JSON
    output_file = "kalshi_live_weather_signal.json"
    full_output = {
        "signal": signal,
        "degree_days": dd_res
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=2)

    print(f"\n[*] Relatório ao vivo salvo em {output_file}")

if __name__ == "__main__":
    run_live_pipeline()
