import urllib.request
import re
import os

url = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'href=["\']([^"\']+)["\']', html)
        print("CPC links found:")
        for m in matches:
            if any(k in m.lower() for k in ['txt', 'hdd', 'cdd', 'wk', 'weekly', 'conus', 'data']):
                print(" -", m)
except Exception as e:
    print("Error:", e)
