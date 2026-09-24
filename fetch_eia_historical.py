import urllib.request
import re

url = "https://ir.eia.gov/ngs/ngs.html"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'href=["\']([^"\']+)["\']', html)
        for m in matches:
            if any(k in m.lower() for k in ['csv', 'xls', 'history', 'hist', 'data']):
                print("EIA link:", m)
except Exception as e:
    print("Error:", e)
