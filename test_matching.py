# -*- coding: utf-8 -*-
import urllib.request
import json
import re

HEADERS = {"User-Agent": "Mozilla/5.0"}

def test_matching():
    # 1. Kalshi Fed Markets
    url_k = "https://external-api.kalshi.com/trade-api/v2/markets?series_ticker=KXFEDCOMBO&limit=20"
    req_k = urllib.request.Request(url_k, headers=HEADERS)
    with urllib.request.urlopen(req_k, timeout=10) as r:
        k_mkts = json.loads(r.read().decode()).get("markets", [])

    # 2. Polymarket Fed Event
    url_p = "https://gamma-api.polymarket.com/events?slug=fed-decision-in-october-20260617190323537"
    req_p = urllib.request.Request(url_p, headers=HEADERS)
    with urllib.request.urlopen(req_p, timeout=10) as r:
        p_events = json.loads(r.read().decode())
        p_mkts = p_events[0].get("markets", []) if p_events else []

    print(f"Kalshi Fed markets: {len(k_mkts)} | Polymarket Fed markets: {len(p_mkts)}")

    for pm in p_mkts:
        pq = pm.get("question", "")
        pp = [float(p) for p in json.loads(pm.get("outcomePrices", "[]"))]
        p_yes = pp[0] if pp else 0.5
        p_no = pp[1] if len(pp) > 1 else 0.5
        
        # Procura correspondente na Kalshi
        for km in k_mkts:
            kt = km.get("title", "")
            # Checa se ambos tratam de 25 bps cut
            if "25" in pq and "25" in kt and ("cut" in pq.lower() or "decrease" in pq.lower()) and ("cut" in kt.lower() or "decrease" in kt.lower()):
                k_yes = float(km.get("yes_ask_dollars") or 0.04)
                k_no = float(km.get("no_ask_dollars") or 0.96)
                
                # Leg A: Buy YES Poly + Buy NO Kalshi
                cost_a = p_yes + k_no + 0.015 * k_no + 0.008
                # Leg B: Buy YES Kalshi + Buy NO Poly
                cost_b = k_yes + p_no + 0.015 * k_yes + 0.008

                print("\n🎯 PAR PAREADO COM SUCESSO:")
                print(f"  • Polymarket: {pq}")
                print(f"    YES: ${p_yes:.3f} | NO: ${p_no:.3f}")
                print(f"  • Kalshi: {kt}")
                print(f"    YES: ${k_yes:.3f} | NO: ${k_no:.3f}")
                print(f"  -> Leg A (Poly YES + Kalshi NO): Custo = ${cost_a:.3f} | Lucro = ${1.0 - cost_a:.3f}")
                print(f"  -> Leg B (Kalshi YES + Poly NO): Custo = ${cost_b:.3f} | Lucro = ${1.0 - cost_b:.3f}")
                print(f"  -> Divergência de Probabilidade: {abs(p_yes - k_yes)*100:.1f}%")

if __name__ == "__main__":
    test_matching()
