# -*- coding: utf-8 -*-
import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0"}

print("=== 1. KALSHI MACRO / CRYPTO MARKETS ===")
url_k = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
req_k = urllib.request.Request(url_k, headers=headers)
try:
    with urllib.request.urlopen(req_k, timeout=10) as r:
        d = json.loads(r.read().decode())
        markets = d.get("markets", [])
        keywords = ["FED", "RATE", "CPI", "INFLATION", "PRES", "ELECTION", "VOTE", "BTC", "ETH", "SOL"]
        matched = []
        for m in markets:
            t = m.get("ticker", "").upper()
            title = m.get("title", "").upper()
            if any(k in t or k in title for k in keywords):
                matched.append(m)
        print(f"Encontrados {len(matched)} mercados Kalshi:")
        for m in matched[:8]:
            ticker = m.get("ticker")
            title = m.get("title")
            yes_ask = m.get("yes_ask_dollars", "N/A")
            no_ask = m.get("no_ask_dollars", "N/A")
            print(f"  • [{ticker}] {title} -> YES ask: ${yes_ask} | NO ask: ${no_ask}")
except Exception as e:
    print(f"Erro Kalshi: {e}")

print("\n=== 2. POLYMARKET MACRO / CRYPTO EVENTS ===")
url_p = "https://gamma-api.polymarket.com/events?limit=40&active=true&closed=false&order=volume24hr&ascending=false"
req_p = urllib.request.Request(url_p, headers=headers)
try:
    with urllib.request.urlopen(req_p, timeout=10) as r:
        events = json.loads(r.read().decode())
        print(f"Encontrados {len(events)} eventos Polymarket com alto volume:")
        for ev in events[:8]:
            title = ev.get("title", "")
            slug = ev.get("slug", "")
            mkts = ev.get("markets", [])
            print(f"  • {title} (slug: {slug}) - {len(mkts)} submercado(s)")
            for m in mkts[:2]:
                q = m.get("question")
                outcomes = m.get("outcomes")
                prices = m.get("outcomePrices")
                print(f"      -> {q} | Out: {outcomes} | Prices: {prices}")
except Exception as e:
    print(f"Erro Polymarket: {e}")
