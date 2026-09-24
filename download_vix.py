import urllib.request
import json
import os

base_dir = os.path.join(os.getcwd(), 'vix_dataset')
os.makedirs(base_dir, exist_ok=True)

# DataHub finance-vix github repository
url = 'https://api.github.com/repos/datasets/finance-vix/contents/data'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        for item in data:
            name = item['name']
            download_url = item['download_url']
            dest = os.path.join(base_dir, name)
            urllib.request.urlretrieve(download_url, dest)
            print(f"Saved {name} ({os.path.getsize(dest)} bytes)")
except Exception as e:
    print('GitHub API error:', e)
    # Direct URLs
    urls = [
        ('vix-daily.csv', 'https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv'),
        ('vix-monthly.csv', 'https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-monthly.csv'),
        ('README.md', 'https://raw.githubusercontent.com/datasets/finance-vix/main/README.md')
    ]
    for name, u in urls:
        dest = os.path.join(base_dir, name)
        try:
            urllib.request.urlretrieve(u, dest)
            print(f"Saved fallback {name} ({os.path.getsize(dest)} bytes)")
        except Exception as e2:
            print(f"Failed {name}:", e2)
