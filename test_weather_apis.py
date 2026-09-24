import urllib.request
import json

print("1. Testing Open-Meteo GFS Forecast API...")
url_om = (
    "https://api.open-meteo.com/v1/forecast?"
    "latitude=41.8781,40.7128,29.7604,39.7392,34.0522&"
    "longitude=-87.6298,-74.0060,-95.3698,-104.9903,-118.2437&"
    "daily=temperature_2m_max,temperature_2m_min&"
    "temperature_unit=fahrenheit&forecast_days=7&timezone=auto"
)
req_om = urllib.request.Request(url_om, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req_om, timeout=10) as resp:
        data_om = json.loads(resp.read().decode())
        print(f"[OK] Open-Meteo returned 7-day forecast for 5 regions:")
        regions = ['Midwest (Chicago)', 'East (New York)', 'South Central (Houston)', 'Mountain (Denver)', 'Pacific (Los Angeles)']
        for i, loc in enumerate(data_om):
            t_max = loc['daily']['temperature_2m_max']
            t_min = loc['daily']['temperature_2m_min']
            avg_temp = [(mx + mn)/2 for mx, mn in zip(t_max, t_min)]
            print(f"  • {regions[i]}: Avg Temp = {sum(avg_temp)/len(avg_temp):.1f}°F")
except Exception as e:
    print("[ERROR] Open-Meteo:", e)

print("\n2. Testing NOAA NWS Official API...")
url_noaa = "https://api.weather.gov/points/41.8781,-87.6298"
req_noaa = urllib.request.Request(url_noaa, headers={'User-Agent': 'AntigravityQuant/1.0 (contact@quantdesk.local)'})
try:
    with urllib.request.urlopen(req_noaa, timeout=10) as resp:
        data_noaa = json.loads(resp.read().decode())
        forecast_url = data_noaa['properties']['forecast']
        print(f"[OK] NOAA Station connected! Forecast endpoint: {forecast_url}")
        req_fc = urllib.request.Request(forecast_url, headers={'User-Agent': 'AntigravityQuant/1.0 (contact@quantdesk.local)'})
        with urllib.request.urlopen(req_fc, timeout=10) as resp_fc:
            fc_data = json.loads(resp_fc.read().decode())
            periods = fc_data['properties']['periods']
            print(f"[OK] NOAA 7-Day Forecast Periods received ({len(periods)} periods):")
            for p in periods[:4]:
                print(f"  • {p['name']}: {p['temperature']}°{p['temperatureUnit']} | {p['shortForecast']}")
except Exception as e:
    print("[ERROR] NOAA NWS:", e)
