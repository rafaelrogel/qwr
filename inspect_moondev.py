import urllib.request
import json
import base64

def fetch_dir(path=""):
    url = f"https://api.github.com/repos/moondevonyt/Polymarket-Trading-Bot-Examples-By-Moon-Dev/contents/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

files = fetch_dir()
print("ARQUIVOS RAIZ:")
for f in files:
    print(f"[{f['type'].upper()}] {f['name']}")

if any(f['name'] == '5_minute_bots' for f in files):
    print("\nCONTEUDO DE 5_minute_bots:")
    bots_files = fetch_dir("5_minute_bots")
    for bf in bots_files:
        print(f"[{bf['type'].upper()}] {bf['name']} ({bf.get('size', 0)} bytes)")

# Ler README e salvar em arquivo texto utf-8
readme_url = "https://api.github.com/repos/moondevonyt/Polymarket-Trading-Bot-Examples-By-Moon-Dev/readme"
req_rm = urllib.request.Request(readme_url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req_rm) as r:
    rm_data = json.loads(r.read().decode())
    content = base64.b64decode(rm_data["content"]).decode("utf-8", errors="ignore")
    with open("moondev_readme.md", "w", encoding="utf-8") as out:
        out.write(content)
print("\nREADME salvo com sucesso em moondev_readme.md!")
