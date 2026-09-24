"""
Scanner de Teste para o 98¢ Trade: Varredura de mercados quase certos em Polymarket e Kalshi
"""
import urllib.request
import json
from datetime import datetime, timezone, timedelta

def scan_polymarket(min_price=0.965, max_price=0.992, max_days=7):
    print("--- Varrendo Polymarket Gamma API ---")
    url = "https://gamma-api.polymarket.com/markets?limit=100&active=true&closed=false&order=volume24hr&ascending=false"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    candidates = []
    now = datetime.now(timezone.utc)
    max_expiry = now + timedelta(days=max_days)

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            for m in data:
                end_iso = m.get("endDateIso") or m.get("endDate")
                if not end_iso:
                    continue
                try:
                    if end_iso.endswith("Z"):
                        end_dt = datetime.fromisoformat(end_iso[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        end_dt = datetime.fromisoformat(end_iso)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                
                # Filtro de tempo: até max_days no futuro
                if end_dt > max_expiry or end_dt < now:
                    continue
                
                # Analisa outcomePrices
                prices_str = m.get("outcomePrices")
                outcomes = m.get("outcomes")
                if not prices_str or not outcomes:
                    continue
                try:
                    if isinstance(prices_str, str):
                        prices = json.loads(prices_str)
                    else:
                        prices = prices_str
                    prices = [float(p) for p in prices]
                except Exception:
                    continue
                
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                
                token_ids = m.get("clobTokenIds")
                if isinstance(token_ids, str):
                    try:
                        token_ids = json.loads(token_ids)
                    except Exception:
                        token_ids = []

                for idx, p in enumerate(prices):
                    if min_price <= p <= max_price:
                        outcome_name = outcomes[idx] if idx < len(outcomes) else str(idx)
                        tok_id = token_ids[idx] if token_ids and idx < len(token_ids) else None
                        candidates.append({
                            "platform": "Polymarket",
                            "id": m.get("id"),
                            "slug": m.get("slug"),
                            "question": m.get("question"),
                            "description": m.get("description", ""),
                            "resolution_source": m.get("resolutionSource", "UMA"),
                            "outcome": outcome_name,
                            "price": p,
                            "volume": float(m.get("volumeNum") or m.get("volume24hr") or 0),
                            "spread": float(m.get("spread") or 0.01),
                            "end_date": end_iso,
                            "days_remaining": round((end_dt - now).total_seconds() / 86400, 1),
                            "clob_token_id": tok_id
                        })
    except Exception as e:
        print(f"Erro ao varrer Polymarket: {e}")
    return candidates

def scan_kalshi(min_price=0.965, max_price=0.992, max_days=7):
    print("--- Varrendo Kalshi Public API ---")
    url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    candidates = []
    now = datetime.now(timezone.utc)
    max_expiry = now + timedelta(days=max_days)

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            markets = data.get("markets", [])
            for m in markets:
                close_time = m.get("close_time") or m.get("expiration_time")
                if not close_time:
                    continue
                try:
                    if close_time.endswith("Z"):
                        end_dt = datetime.fromisoformat(close_time[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        end_dt = datetime.fromisoformat(close_time)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                
                if end_dt > max_expiry or end_dt < now:
                    continue

                # Preços YES e NO
                yes_ask = m.get("yes_ask_dollars")
                no_ask = m.get("no_ask_dollars")
                
                checks = []
                if yes_ask is not None:
                    try:
                        checks.append(("YES", float(yes_ask)))
                    except Exception:
                        pass
                if no_ask is not None:
                    try:
                        checks.append(("NO", float(no_ask)))
                    except Exception:
                        pass

                for outcome, p in checks:
                    if min_price <= p <= max_price:
                        candidates.append({
                            "platform": "Kalshi",
                            "ticker": m.get("ticker"),
                            "title": m.get("title"),
                            "rules_primary": m.get("rules_primary", ""),
                            "rules_secondary": m.get("rules_secondary", ""),
                            "outcome": outcome,
                            "price": p,
                            "volume": float(m.get("volume_24h_fp") or m.get("volume_fp") or 0),
                            "end_date": close_time,
                            "days_remaining": round((end_dt - now).total_seconds() / 86400, 1)
                        })
    except Exception as e:
        print(f"Erro ao varrer Kalshi: {e}")
    return candidates

if __name__ == "__main__":
    poly = scan_polymarket()
    kalshi = scan_kalshi()
    all_c = poly + kalshi
    print(f"\n[OK] Encontrados {len(all_c)} candidatos potenciais (Polymarket: {len(poly)} | Kalshi: {len(kalshi)}):")
    for i, c in enumerate(all_c[:10], 1):
        name = c.get("question") or c.get("title")
        print(f"{i}. [{c['platform']}] {name}")
        print(f"   Outcome: {c['outcome']} @ ${c['price']:.3f} | Vencimento em: {c['days_remaining']} dias")
        rules = c.get("description") or c.get("rules_primary") or ""
        print(f"   Regras: {rules[:120]}...\n")
