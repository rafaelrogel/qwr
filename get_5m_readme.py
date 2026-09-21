import urllib.request
import json
import base64

def fetch_file(path, save_as):
    url = f"https://api.github.com/repos/moondevonyt/Polymarket-Trading-Bot-Examples-By-Moon-Dev/contents/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
        content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        with open(save_as, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"{path} salvo como {save_as} ({len(content)} chars)")

fetch_file("5_minute_bots/README.md", "moondev_5m_readme.md")
