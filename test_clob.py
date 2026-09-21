import urllib.request
import json

def test_clob_orderbook():
    gamma_url = "https://gamma-api.polymarket.com/markets?limit=1&active=true&closed=false&order=volume24hr&ascending=false"
    req = urllib.request.Request(gamma_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        market = data[0]
        token_ids = json.loads(market["clobTokenIds"])
        yes_token = token_ids[0]
        print(f"Mercado: {market['question']}")
        print(f"Token YES ID: {yes_token[:30]}...")

    clob_url = f"https://clob.polymarket.com/book?token_id={yes_token}"
    req2 = urllib.request.Request(clob_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        book = json.loads(resp2.read().decode())
        print("\n--- Livro de Ofertas (CLOB) do Token YES ---")
        print("Top 3 Bids (Compradores):")
        for b in book.get("bids", [])[:3]:
            print(f"  Preco: ${float(b['price']):.4f} | Quantidade: {float(b['size']):,.0f} cotas")
        print("Top 3 Asks (Vendedores):")
        for a in book.get("asks", [])[:3]:
            print(f"  Preco: ${float(a['price']):.4f} | Quantidade: {float(a['size']):,.0f} cotas")

if __name__ == "__main__":
    test_clob_orderbook()
