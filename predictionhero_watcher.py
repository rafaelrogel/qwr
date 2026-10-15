# -*- coding: utf-8 -*-
"""
=============================================================================
PREDICTIONHERO MULTI-VENUE WATCHER & JEV CONSENSUS ENGINE
=============================================================================
Alavanca os dados agregados do PredictionHero (Polymarket, Kalshi, Limitless,
Predict.Fun e Opinion) para:
1. Calcular o Consenso de Probabilidade Multi-Venue em tempo real.
2. Detectar anomalias de "Baleia Local" e Spoofing quando uma plataforma descola.
3. Fornecer dados ao Cão de Guarda Jev SystemOne (<1ms em cache de memória).
4. Alertar oportunidades de Arbitragem Pura (Cross-Arb) para o Desk 7.
=============================================================================
"""

import os
import sys
import time
import json
import re
import threading
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "predictionhero_live_state.json")

# Sessão e Token da conta PredictionHero do usuário
CLERK_SESSION_ID = os.getenv("PREDICTIONHERO_CLERK_SESSION_ID", "sess_3Ke8VvRp11WIazArvQ7mNzVXltU")
CLERK_CLIENT_COOKIE = os.getenv(
    "PREDICTIONHERO_CLIENT_COOKIE",
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImNsaWVudF8zS2U4VE0zUFdMbWJYU0hPRXVrSm1mUEdTVFIiLCJyb3RhdGluZ190b2tlbiI6ImlsOTBrdXVyeGFuOXh1ZWR4azB1MW51NWQ1MTJlMWNjYXA3YXd5aWcifQ.TJ1X84KXa1llLIsvPqEGJ5ciSxSgw4f1xiYidYYkVbCN-BTWm71f4P9WecyHCRgmL-3txGyIn2uWqiUIOAzfB3HlGP4Lc1FfRtRqxJuVK_mBzuLWsACTsnwVKcgT-J1bYlCkMKoF3A4pOZam3pTvYvHX_xhYPDkxprJ5ZUdKICh65DBvAsn-ts2xo3WS3yCjm8aLRdjiKR5yJVc8DGojTnpI4mXi38cC6_G1g9FM44eGTUsRpqtVjVJOh3zKHnc4tSpY0TGlgzqFPToofRt-AANWLs0iDV-Q3wTFl-HJjlWQ6c7hYIz8djrF3MkyLP6hP-EdIaF_SNnOEfAI4TqS7g"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8"
}

_CACHE_LOCK = threading.Lock()
_CONSENSUS_CACHE: Dict[str, Dict[str, Any]] = {}
_ARBITRAGE_ALERTS: List[Dict[str, Any]] = []
_LAST_UPDATE_TS: float = 0.0


class PredictionHeroWatcher:
    """
    Watcher assíncrono em background que monitora o PredictionHero,
    atualiza o consenso multi-venue e detecta divergências de preço.
    """

    def __init__(self, update_interval: int = 60):
        self.update_interval = update_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._jwt_token: Optional[str] = None
        self._jwt_expiry: float = 0.0

    def get_fresh_jwt(self) -> Optional[str]:
        """Gera ou renova o JWT do Clerk da conta PredictionHero do usuário"""
        now = time.time()
        if self._jwt_token and (self._jwt_expiry - now) > 60:
            return self._jwt_token

        clerk_url = f"https://clerk.predictionhero.com/v1/client/sessions/{CLERK_SESSION_ID}/tokens?__clerk_api_version=2026-05-12&_clerk_js_version=6.39.0"
        try:
            req = urllib.request.Request(
                clerk_url,
                data=b"organization_id=&tab_state=visible",
                headers={
                    "Origin": "https://predictionhero.com",
                    "Referer": "https://predictionhero.com/",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": f"__client={CLERK_CLIENT_COOKIE}; __client_uat=1791906700;"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                jwt = data.get("jwt")
                if jwt:
                    self._jwt_token = jwt
                    self._jwt_expiry = now + 50  # Validade típica de 60s
                    return jwt
        except Exception as e:
            pass
        return self._jwt_token

    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return None

    def fetch_top_events(self) -> List[Dict[str, Any]]:
        """Extrai os 50 maiores eventos em volume direto da página inicial do PredictionHero"""
        html = self._fetch_html("https://predictionhero.com/")
        if not html:
            return []

        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        events = []
        for s in scripts:
            if "ItemList" in s and "events" in s:
                try:
                    d = json.loads(s)
                    graph = d.get("@graph", [])
                    for node in graph:
                        if node.get("@type") == "ItemList":
                            for item_obj in node.get("itemListElement", []):
                                it = item_obj.get("item", {})
                                name = it.get("name")
                                u = it.get("url")
                                props = {p.get("name"): p.get("value") for p in it.get("additionalProperty", [])}
                                platforms = str(props.get("Platforms", ""))
                                vol = float(props.get("Total volume", 0))
                                markets_count = int(props.get("Markets", 0))

                                if name and u:
                                    events.append({
                                        "name": name,
                                        "url": u,
                                        "platforms": [p.strip() for p in platforms.split(",") if p.strip()],
                                        "volume_usd": vol,
                                        "markets_count": markets_count,
                                        "is_multi_venue": len([p for p in ["Polymarket", "Kalshi"] if p in platforms]) >= 2
                                    })
                except Exception:
                    pass
        return events

    def fetch_event_market_breakdown(self, event_url: str) -> Dict[str, Any]:
        """
        Extrai cotações de todas as plataformas para um evento específico.
        Retorna dicionário com cotações da Polymarket, Kalshi e consenso.
        """
        html = self._fetch_html(event_url)
        if not html:
            return {}

        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        if len(scripts) < 2:
            return {}

        breakdown = {
            "url": event_url,
            "markets_by_venue": {},
            "consensus_by_outcome": {},
            "arbitrage_opportunities": []
        }

        for s in scripts:
            if "@graph" in s and "itemListElement" in s:
                try:
                    d = json.loads(s)
                    for node in d.get("@graph", []):
                        if node.get("@type") == "ItemList":
                            for m in node.get("itemListElement", []):
                                item = m.get("item", {})
                                brand = (item.get("brand", {}).get("name") or "unknown").lower()
                                name = item.get("name", "").strip()
                                props = {p.get("name"): p.get("value") for p in item.get("additionalProperty", [])}
                                
                                # Extrai preço e probabilidade
                                p_str = str(props.get("Current price", "0")).replace("¢", "").replace("$", "").strip()
                                pr_str = str(props.get("Current probability", "0")).replace("%", "").strip()
                                try:
                                    price = float(p_str) / (100.0 if "¢" in str(props.get("Current price", "")) or float(p_str) > 1.0 else 1.0)
                                except Exception:
                                    price = 0.0
                                try:
                                    prob = float(pr_str) / 100.0
                                except Exception:
                                    prob = price

                                if name and brand:
                                    breakdown["markets_by_venue"].setdefault(brand, {})[name] = {
                                        "price": round(price, 3),
                                        "prob": round(prob, 3)
                                    }
                except Exception:
                    pass

        # Calcula Consenso e Divergências
        poly_m = breakdown["markets_by_venue"].get("polymarket", {})
        kalshi_m = breakdown["markets_by_venue"].get("kalshi", {})

        # Compara outcomes equivalentes
        for p_name, p_data in poly_m.items():
            best_match = None
            p_clean = re.sub(r'[^a-zA-Z0-9]', '', p_name.lower())
            
            for k_name, k_data in kalshi_m.items():
                k_clean = re.sub(r'[^a-zA-Z0-9]', '', k_name.lower())
                # Checa similaridade de texto básica
                if p_clean in k_clean or k_clean in p_clean or (p_name.split()[0].lower() == k_name.split()[0].lower()):
                    best_match = (k_name, k_data)
                    break

            if best_match:
                k_name, k_data = best_match
                poly_p = p_data["prob"]
                kalshi_p = k_data["prob"]
                consensus_p = round((poly_p + kalshi_p) / 2.0, 3)
                divergence = round(abs(poly_p - kalshi_p), 3)

                breakdown["consensus_by_outcome"][p_name] = {
                    "polymarket_prob": poly_p,
                    "kalshi_prob": kalshi_p,
                    "kalshi_name": k_name,
                    "consensus_prob": consensus_p,
                    "divergence_pct": round(divergence * 100, 1),
                    "is_whale_divergence": divergence >= 0.08  # >= 8% descolamento
                }

                # Checa Arbitragem Pura Cross-Venue
                # Custo 1: Buy YES on Poly + Buy NO on Kalshi
                # Custo 2: Buy YES on Kalshi + Buy NO on Poly
                poly_yes = p_data["price"]
                poly_no = max(0.01, round(1.0 - poly_yes, 3))
                kalshi_yes = k_data["price"]
                kalshi_no = max(0.01, round(1.0 - kalshi_yes, 3))

                cost_1 = round(poly_yes + kalshi_no, 3)
                cost_2 = round(kalshi_yes + poly_no, 3)

                if cost_1 < 0.97:
                    breakdown["arbitrage_opportunities"].append({
                        "type": "BUY_POLY_YES_KALSHI_NO",
                        "outcome": p_name,
                        "cost": cost_1,
                        "net_profit_pct": round((1.0 - cost_1) * 100, 2),
                        "poly_price": poly_yes,
                        "kalshi_price": kalshi_no
                    })
                elif cost_2 < 0.97:
                    breakdown["arbitrage_opportunities"].append({
                        "type": "BUY_KALSHI_YES_POLY_NO",
                        "outcome": p_name,
                        "cost": cost_2,
                        "net_profit_pct": round((1.0 - cost_2) * 100, 2),
                        "kalshi_price": kalshi_yes,
                        "poly_price": poly_no
                    })

        return breakdown

    def update_cycle(self):
        """Executa um ciclo completo de varredura e atualização do cache de consenso"""
        global _CONSENSUS_CACHE, _ARBITRAGE_ALERTS, _LAST_UPDATE_TS

        events = self.fetch_top_events()
        if not events:
            return

        # Prioriza eventos multi-venue (Polymarket + Kalshi) e mercados prioritários da nossa frota
        multi_venue_events = [e for e in events if e.get("is_multi_venue")]
        priority_keywords = ["bitcoin", "btc", "fed", "rate", "gold", "cpi", "seahawks", "broncos", "nfl", "election"]
        
        target_events = []
        for e in multi_venue_events:
            n_low = e["name"].lower()
            if any(k in n_low for k in priority_keywords):
                target_events.append(e)

        # Se tiver poucos, adiciona os top multi-venue restantes até 6 eventos para não estourar tempo
        for e in multi_venue_events:
            if len(target_events) >= 6:
                break
            if e not in target_events:
                target_events.append(e)

        new_consensus = {}
        new_arbs = []

        for ev in target_events[:6]:
            bd = self.fetch_event_market_breakdown(ev["url"])
            if bd and bd.get("consensus_by_outcome"):
                ev_name = ev["name"]
                new_consensus[ev_name] = {
                    "url": ev["url"],
                    "volume_usd": ev["volume_usd"],
                    "platforms": ev["platforms"],
                    "outcomes": bd["consensus_by_outcome"]
                }
                for arb in bd.get("arbitrage_opportunities", []):
                    new_arbs.append({**arb, "event": ev_name, "url": ev["url"]})

        with _CACHE_LOCK:
            _CONSENSUS_CACHE = new_consensus
            _ARBITRAGE_ALERTS = new_arbs
            _LAST_UPDATE_TS = time.time()

        self._save_state(events_count=len(events), multi_count=len(multi_venue_events))

    def _save_state(self, events_count: int, multi_count: int):
        try:
            state = {
                "watcher_name": "PredictionHero Multi-Venue Watcher",
                "account_user": "user_3Ke8VwrGLe1hd0vS9RlDDFbbuno",
                "plan": "Standard",
                "status": "ONLINE",
                "last_update_utc": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
                "total_events_indexed": events_count,
                "multi_venue_events": multi_count,
                "monitored_consensus_events": len(_CONSENSUS_CACHE),
                "arbitrage_alerts_count": len(_ARBITRAGE_ALERTS),
                "arbitrage_alerts": _ARBITRAGE_ALERTS,
                "consensus_data": _CONSENSUS_CACHE
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def run_loop(self):
        print("=" * 80)
        print("🦅 PREDICTIONHERO MULTI-VENUE WATCHER INICIADO")
        print("   Conta: user_3Ke8VwrGLe1hd0vS9RlDDFbbuno (Plano Standard)")
        print(f"   Intervalo de Atualização: {self.update_interval}s")
        print("=" * 80)

        while self._running:
            try:
                self.update_cycle()
                with _CACHE_LOCK:
                    c_count = len(_CONSENSUS_CACHE)
                    a_count = len(_ARBITRAGE_ALERTS)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] PredictionHero Feed: {c_count} eventos sincronizados | {a_count} alertas de arbitragem")
            except Exception as e:
                print(f"[!] Erro no ciclo PredictionHero Watcher: {e}")
            time.sleep(self.update_interval)

    def start_background(self):
        """Inicia o watcher em thread daemon separada"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self.run_loop, daemon=True, name="PredictionHeroWatcher")
        self._thread.start()


# Instância global singleton para importação direta em outros módulos
predictionhero_watcher = PredictionHeroWatcher(update_interval=60)


def get_cross_venue_consensus(keyword: str) -> Optional[Dict[str, Any]]:
    """
    Função utilitária de altíssima velocidade (<0.1ms) consultada pelo Cão de Guarda Jev.
    Retorna o consenso entre Polymarket e Kalshi para um termo/evento específico.
    """
    k_low = keyword.lower().strip()
    with _CACHE_LOCK:
        for ev_name, ev_data in _CONSENSUS_CACHE.items():
            if k_low in ev_name.lower():
                return ev_data
            for out_name, out_data in ev_data.get("outcomes", {}).items():
                if k_low in out_name.lower():
                    return {"event": ev_name, "outcome": out_name, **out_data}
    return None


def get_arbitrage_alerts() -> List[Dict[str, Any]]:
    """Retorna todas as oportunidades de arbitragem pura ativas no momento"""
    with _CACHE_LOCK:
        return list(_ARBITRAGE_ALERTS)


if __name__ == "__main__":
    watcher = PredictionHeroWatcher(update_interval=30)
    watcher._running = True
    # Executa 1 ciclo síncrono para teste imediato
    print("Testando 1 ciclo do PredictionHero Watcher...")
    watcher.update_cycle()
    print("Ciclo concluído com sucesso!")
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        print(f.read()[:2000])
