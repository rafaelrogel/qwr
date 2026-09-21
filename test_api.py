import urllib.request
import json

def test_connection():
    url = "https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume24hr&ascending=false"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"Sucesso! {len(data)} mercados de alto volume encontrados:")
            for m in data:
                question = m.get("question", "N/A")
                vol = float(m.get("volume24hr", 0) or 0)
                outcomes = m.get("outcomes", "[]")
                outcome_prices = m.get("outcomePrices", "[]")
                print(f"\n[Mercado] {question}")
                print(f"  Volume 24h: ${vol:,.2f}")
                print(f"  Resultados: {outcomes}")
                print(f"  Precos:     {outcome_prices}")
    except Exception as e:
        print(f"Erro ao conectar: {e}")

if __name__ == "__main__":
    test_connection()
