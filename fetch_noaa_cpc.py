import urllib.request
import re

url = "https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/historical_data/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'href=["\']([^"\']+)["\']', html)
        print("NOAA links found:")
        for m in matches:
            if not m.startswith('?') and not m.startswith('/'):
                print(" -", m)
except Exception as e:
    print("Error:", e)
