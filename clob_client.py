"""
Cliente de Conexão com as APIs do Polymarket (Gamma & CLOB)
"""
import urllib.request
import json
import time
from typing import List, Dict, Any, Optional

class PolymarketClient:
    def __init__(self, gamma_url: str = "https://gamma-api.polymarket.com", clob_url: str = "https://clob.polymarket.com"):
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.headers = {
            "User-Agent": "PolymarketAlgoTrader/1.0",
            "Accept": "application/json"
        }

    def _get(self, url: str) -> Any:
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_top_markets(self, limit: int = 25, min_volume: float = 5000.0) -> List[Dict[str, Any]]:
        """Busca os mercados mais ativos e com maior volume negociado."""
        endpoint = f"{self.gamma_url}/markets?limit={limit}&active=true&closed=false&order=volume24hr&ascending=false"
        raw_markets = self._get(endpoint)
        
        filtered = []
        for m in raw_markets:
            vol = float(m.get("volume24hr") or 0)
            if vol >= min_volume:
                filtered.append(m)
        return filtered

    def get_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Busca um mercado específico pelo seu identificador (slug)."""
        endpoint = f"{self.gamma_url}/markets?slug={slug}"
        res = self._get(endpoint)
        return res[0] if res else None

    def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """Consulta o livro de ofertas (CLOB) para um token específico (YES ou NO)."""
        endpoint = f"{self.clob_url}/book?token_id={token_id}"
        return self._get(endpoint)

    def get_midpoint_price(self, token_id: str) -> Optional[float]:
        """Obtém o preço médio atual de um token."""
        try:
            endpoint = f"{self.clob_url}/midpoint?token_id={token_id}"
            res = self._get(endpoint)
            return float(res.get("mid", 0))
        except Exception:
            return None

    def get_spread(self, token_id: str) -> Optional[Dict[str, float]]:
        """Calcula o melhor preço de compra (bid), venda (ask) e o spread."""
        book = self.get_order_book(token_id)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        
        best_bid = float(bids[0]["price"]) if bids else None
        best_ask = float(asks[0]["price"]) if asks else None
        spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
        
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread
        }
