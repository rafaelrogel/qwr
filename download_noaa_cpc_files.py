import urllib.request
import os

base_url = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/"
dest_dir = os.path.join(os.getcwd(), "climate_dataset", "noaa_degree_days")
os.makedirs(dest_dir, exist_ok=True)

files = [
    "wctyhddy.txt",
    "wctycddy.txt",
    "wsahddy.txt",
    "wsacddy.txt",
    "mctyhddy.txt",
    "mctycddy.txt"
]

for f in files:
    url = base_url + f
    dest = os.path.join(dest_dir, f)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
            with open(dest, 'wb') as out_f:
                out_f.write(content)
            print(f"Downloaded {f}: {len(content)} bytes")
    except Exception as e:
        print(f"Failed {f}:", e)
