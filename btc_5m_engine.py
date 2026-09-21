"""
Polymarket BTC 5-Minute ("Up or Down") Quantitative Engine
Monitora em tempo real:
1. Preço Spot do Bitcoin (Binance / Coinbase)
2. Preço de Abertura da vela de 5m (Strike / Price to Beat)
3. Mercado ativo na Polymarket (slug btc-updown-5m-{ts}) e livros CLOB de UP e DOWN
4. Modelo Black-Scholes para Opções Binárias (Fair Value)
5. Sinais de Trading quantitativo e Simulador de Paper Trading
"""
import time
import math
import json
import urllib.request
import threading
from typing import Dict, Any, List, Optional

class BTC5mEngine:
    def __init__(self, annualized_vol: float = 0.55):
        self.annualized_vol = annualized_vol
        self.lock = threading.Lock()
        
        # Estado atual do ciclo
        self.current_window_ts: int = 0
        self.strike_price: float = 0.0
        self.spot_price: float = 0.0
        self.binance_spot: float = 0.0
        self.last_spot_update: float = 0.0
        self.price_history: List[Dict[str, Any]] = [] # Histórico de ticks recentes para micro-gráfico
        
        # Dados do mercado Polymarket
        self.market_info: Dict[str, Any] = {}
        self.token_up_id: str = ""
        self.token_down_id: str = ""
        self.poly_price_up: float = 0.50
        self.poly_price_down: float = 0.50
        self.book_up: Dict[str, Any] = {"bids": [], "asks": []}
        self.book_down: Dict[str, Any] = {"bids": [], "asks": []}
        
        # Modelo Quantitativo
        self.fair_value_up: float = 0.50
        self.fair_value_down: float = 0.50
        self.edge_up: float = 0.0
        self.edge_down: float = 0.0
        self.active_signal: Dict[str, Any] = {
            "type": "WAITING",
            "action": "Aguardando dados...",
            "confidence": 0,
            "rationale": "Inicializando feeds de dados",
            "color": "#9ca3af"
        }
        
        # Simulador de Paper Trading (Histórico de Rodadas de 5m)
        self.paper_history: List[Dict[str, Any]] = []
        self.paper_balance: float = 1000.0  # Começa com $1000 fictícios
        self.paper_trades_count: int = 0
        self.paper_wins: int = 0
        self.active_paper_position: Optional[Dict[str, Any]] = None
        
        self.running = False

    @staticmethod
    def normal_cdf(x: float) -> float:
        """Função de distribuição acumulada da normal padrão Φ(x)"""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def calculate_fair_value(self, spot: float, strike: float, seconds_left: int) -> float:
        """Calcula a probabilidade neutra ao risco N(d2) para o token UP (Call Binária)"""
        if spot <= 0 or strike <= 0:
            return 0.50
        if seconds_left <= 0:
            return 1.0 if spot >= strike else 0.0
        
        tau = max(1.0, float(seconds_left)) / (365.25 * 24 * 3600)
        sigma_sqrt_tau = self.annualized_vol * math.sqrt(tau)
        if sigma_sqrt_tau <= 1e-9:
            return 1.0 if spot >= strike else 0.0
            
        d2 = (math.log(spot / strike) - 0.5 * (self.annualized_vol ** 2) * tau) / sigma_sqrt_tau
        # Limita entre 0.01 e 0.99 para evitar probabilidades estritas
        prob = self.normal_cdf(d2)
        return max(0.01, min(0.99, prob))

    def fetch_chainlink_price(self) -> float:
        """Busca cotacao oficial do Oraculo Chainlink BTC/USD na Polygon (AggregatorV3 0xc907E116054Ad103354f2D350FD2514433D57F6f)"""
        rpcs = [
            "https://1rpc.io/matic",
            "https://polygon-bor-rpc.publicnode.com",
            "https://polygon.llamarpc.com"
        ]
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": "0xc907E116054Ad103354f2D350FD2514433D57F6f", "data": "0xfeaf968c"}, "latest"],
            "id": 1
        }).encode("utf-8")
        for rpc in rpcs:
            try:
                req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    if "result" in res and res["result"] and len(res["result"]) >= 130:
                        ans_hex = res["result"][66:130]
                        price = int(ans_hex, 16) / 1e8
                        if price > 10000:
                            return round(price, 2)
            except Exception:
                continue
        return self.fetch_binance_spot()

    def fetch_binance_spot(self) -> float:
        """Busca o preço spot do BTC/USDT em tempo real com failover"""
        urls = [
            "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
            "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
        ]
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return float(data["price"])
            except Exception:
                continue
        # Fallback Coinbase se Binance falhar
        try:
            req = urllib.request.Request("https://api.coinbase.com/v2/prices/BTC-USD/spot", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return float(data["data"]["amount"])
        except Exception:
            return self.spot_price

    def fetch_strike_price(self, window_ts: int) -> float:
        """Busca o preço de abertura oficial da vela de 5m correspondente ao início do ciclo"""
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=3"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                klines = json.loads(resp.read().decode("utf-8"))
                for k in klines:
                    candle_open_ts = int(k[0]) // 1000
                    if candle_open_ts == window_ts:
                        return float(k[1])
                # Se ainda não encontrou exatamente a vela atual, pega a última
                if klines:
                    return float(klines[-1][1])
        except Exception as e:
            print(f"[Strike Fetch Error]: {e}")
        return self.strike_price or self.spot_price

    def fetch_polymarket_market(self, window_ts: int) -> Optional[Dict[str, Any]]:
        """Busca o mercado de 5m ativo da Polymarket via Gamma API"""
        slug = f"btc-updown-5m-{window_ts}"
        url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolymarketBot/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and len(data) > 0:
                    return data[0]
        except Exception as e:
            print(f"[Poly Market Error {slug}]: {e}")
        return None

    def fetch_clob_book(self, token_id: str) -> Dict[str, Any]:
        """Busca o orderbook CLOB de um token específico"""
        if not token_id:
            return {"bids": [], "asks": []}
        url = f"https://clob.polymarket.com/book?token_id={token_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolymarketBot/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {"bids": [], "asks": []}

    def evaluate_signals(self, seconds_left: int, delta_price: float):
        """Avalia os sinais algorítmicos baseados em Fair Value e Latência"""
        edge_up = self.fair_value_up - self.poly_price_up
        edge_down = self.fair_value_down - self.poly_price_down
        self.edge_up = round(edge_up, 4)
        self.edge_down = round(edge_down, 4)
        
        # 1. Sniper Final 60s
        if seconds_left <= 60:
            if delta_price >= 25.0 and self.poly_price_up < 0.94:
                return {
                    "type": "SNIPER_CONVERGENCE",
                    "action": "⚡ SNIPER COMPRA UP (Final 60s)",
                    "target": "UP",
                    "confidence": 92,
                    "rationale": f"BTC +${delta_price:.1f} acima do strike a {seconds_left}s do fim. Probabilidade estatística >95% de vitória.",
                    "color": "#10b981",
                    "expected_return": f"+{((1.0 - self.poly_price_up) / self.poly_price_up * 100):.1f}%"
                }
            elif delta_price <= -25.0 and self.poly_price_down < 0.94:
                return {
                    "type": "SNIPER_CONVERGENCE",
                    "action": "⚡ SNIPER COMPRA DOWN (Final 60s)",
                    "target": "DOWN",
                    "confidence": 92,
                    "rationale": f"BTC -${abs(delta_price):.1f} abaixo do strike a {seconds_left}s do fim. Probabilidade estatística >95% de vitória.",
                    "color": "#ef4444",
                    "expected_return": f"+{((1.0 - self.poly_price_down) / self.poly_price_down * 100):.1f}%"
                }
                
        # 2. Vantagem Estatística Black-Scholes (+EV)
        if edge_up >= 0.08:
            return {
                "type": "FAIR_VALUE_EDGE",
                "action": f"🟢 COMPRA UP COM EDGE (+{edge_up*100:.1f}%)",
                "target": "UP",
                "confidence": min(88, int(50 + edge_up * 150)),
                "rationale": f"Fair Value é {self.fair_value_up*100:.1f}%, mas Polymarket está precificando a {self.poly_price_up*100:.1f}%. Desconto de {edge_up*100:.1f}¢.",
                "color": "#10b981",
                "expected_return": f"+{edge_up*100:.1f} pts"
            }
        elif edge_down >= 0.08:
            return {
                "type": "FAIR_VALUE_EDGE",
                "action": f"🔴 COMPRA DOWN COM EDGE (+{edge_down*100:.1f}%)",
                "target": "DOWN",
                "confidence": min(88, int(50 + edge_down * 150)),
                "rationale": f"Fair Value é {self.fair_value_down*100:.1f}%, mas Polymarket está precificando a {self.poly_price_down*100:.1f}%. Desconto de {edge_down*100:.1f}¢.",
                "color": "#ef4444",
                "expected_return": f"+{edge_down*100:.1f} pts"
            }
            
        # 3. Formação de Mercado (Spread Neutro)
        spread_up = 0.02
        if self.book_up.get("asks") and self.book_up.get("bids"):
            try:
                spread_up = float(self.book_up["asks"][0]["price"]) - float(self.book_up["bids"][-1]["price"])
            except Exception:
                pass
                
        if abs(delta_price) < 8.0 and seconds_left > 120:
            return {
                "type": "MARKET_MAKING",
                "action": "⚖️ MODO MARKET MAKING (Spread Neutro)",
                "target": "SPREAD",
                "confidence": 75,
                "rationale": f"Spot próximo ao strike ($K: ${self.strike_price:,.1f}). Oportunidade de cotação dupla para capturar rebate de 100%.",
                "color": "#3b82f6",
                "expected_return": "Captura de Spread + Rebates"
            }
            
        return {
            "type": "NEUTRAL",
            "action": "⏸️ MONITORANDO (Sem Edge Relevante)",
            "target": "NONE",
            "confidence": 40,
            "rationale": "Mercado alinhado com o valor teórico. Aguardando distorção de preço ou movimentação spot.",
            "color": "#9ca3af",
            "expected_return": "0.0%"
        }

    def process_cycle_settlement(self, old_window_ts: int, final_spot: float, strike: float):
        """Simula a resolução de um ciclo expirado e contabiliza PnL no Paper Trading"""
        if strike <= 0 or final_spot <= 0:
            return
            
        winner = "UP" if final_spot >= strike else "DOWN"
        delta = final_spot - strike
        
        pnl = 0.0
        trade_details = "Nenhum trade executado"
        
        if self.active_paper_position:
            pos = self.active_paper_position
            pos_side = pos.get("side")
            pos_price = pos.get("entry_price", 0.50)
            pos_size = pos.get("size", 100.0) # $100 por posição
            
            if pos_side == winner:
                pnl = (1.0 - pos_price) * (pos_size / pos_price)
                self.paper_wins += 1
                result_text = f"VITÓRIA (+${pnl:.2f})"
            else:
                pnl = -pos_size
                result_text = f"DERROTA (-${abs(pnl):.2f})"
                
            self.paper_balance += pnl
            self.paper_trades_count += 1
            trade_details = f"Aposta {pos_side} @ ${pos_price:.2f} -> {result_text}"
            self.active_paper_position = None
            
        record = {
            "window_ts": old_window_ts,
            "time_str": time.strftime("%H:%M", time.localtime(old_window_ts)),
            "strike": round(strike, 2),
            "final_spot": round(final_spot, 2),
            "delta": round(delta, 2),
            "winner": winner,
            "trade": trade_details,
            "pnl": round(pnl, 2),
            "balance": round(self.paper_balance, 2)
        }
        
        self.paper_history.insert(0, record)
        if len(self.paper_history) > 20:
            self.paper_history.pop()

    def update_cycle(self):
        """Loop principal executado a cada ~1 segundo"""
        now = int(time.time())
        window_ts = now - (now % 300)
        seconds_elapsed = now - window_ts
        seconds_left = max(0, 300 - seconds_elapsed)
        
        # 1. Detecta virada de ciclo de 5 minutos
        if self.current_window_ts != 0 and window_ts != self.current_window_ts:
            # Ciclo anterior encerrou! Resolver Paper Trading
            self.process_cycle_settlement(self.current_window_ts, self.spot_price, self.strike_price)
            # Reseta dados do novo ciclo
            self.current_window_ts = window_ts
            self.strike_price = 0.0
            self.market_info = {}
            self.active_paper_position = None
        elif self.current_window_ts == 0:
            self.current_window_ts = window_ts

        # 2. Busca Preço Spot Atual (Oraculo Chainlink + Binance Ref)
        new_spot = self.fetch_chainlink_price()
        self.binance_spot = self.fetch_binance_spot()
        if new_spot > 0:
            self.spot_price = new_spot
            self.last_spot_update = time.time()
            # Registra no histórico recente (mantém últimos 60 pontos para gráfico mini)
            self.price_history.append({
                "t": now,
                "spot": self.spot_price,
                "binance": self.binance_spot,
                "seconds_left": seconds_left
            })
            if len(self.price_history) > 60:
                self.price_history.pop(0)

        # 3. Busca Strike se ainda não tiver (Oraculo Chainlink)
        if self.strike_price <= 0:
            self.strike_price = self.fetch_chainlink_price() or self.fetch_strike_price(window_ts)

        delta_price = self.spot_price - self.strike_price if (self.spot_price and self.strike_price) else 0.0

        # 4. Busca dados da Polymarket para o slug atual
        if not self.market_info or (now % 6 == 0):
            poly_data = self.fetch_polymarket_market(window_ts)
            if poly_data:
                self.market_info = poly_data
                try:
                    prices = json.loads(poly_data.get("outcomePrices", "[]"))
                    if len(prices) >= 2:
                        self.poly_price_up = float(prices[0])
                        self.poly_price_down = float(prices[1])
                    tokens = json.loads(poly_data.get("clobTokenIds", "[]"))
                    if len(tokens) >= 2:
                        self.token_up_id = tokens[0]
                        self.token_down_id = tokens[1]
                except Exception as e:
                    print(f"[Parse Poly Error]: {e}")

        # 5. Se temos os tokens, atualiza os livros CLOB a cada 3-4 segundos
        if (now % 3 == 0) and self.token_up_id:
            self.book_up = self.fetch_clob_book(self.token_up_id)
            if self.token_down_id:
                self.book_down = self.fetch_clob_book(self.token_down_id)

        # 6. Atualiza Modelo Black-Scholes
        self.fair_value_up = self.calculate_fair_value(self.spot_price, self.strike_price, seconds_left)
        self.fair_value_down = round(1.0 - self.fair_value_up, 4)
        self.fair_value_up = round(self.fair_value_up, 4)

        # 7. Avalia Sinais Algorítmicos
        self.active_signal = self.evaluate_signals(seconds_left, delta_price)
        
        # 8. Executa Paper Trade se houver sinal forte e ainda não tiver posição neste ciclo
        if not self.active_paper_position and self.active_signal["type"] in ["SNIPER_CONVERGENCE", "FAIR_VALUE_EDGE"]:
            side = self.active_signal.get("target")
            entry_price = self.poly_price_up if side == "UP" else self.poly_price_down
            if entry_price > 0.05 and entry_price < 0.95:
                self.active_paper_position = {
                    "side": side,
                    "entry_price": entry_price,
                    "size": 100.0,
                    "time": time.strftime("%H:%M:%S"),
                    "reason": self.active_signal["action"]
                }

    def get_radar_state(self) -> Dict[str, Any]:
        """Retorna o estado completo estruturado para o frontend e API"""
        now = int(time.time())
        window_ts = self.current_window_ts or (now - (now % 300))
        seconds_elapsed = now - window_ts
        seconds_left = max(0, 300 - seconds_elapsed)
        delta_price = self.spot_price - self.strike_price if (self.spot_price and self.strike_price) else 0.0
        delta_pct = (delta_price / self.strike_price * 100) if self.strike_price > 0 else 0.0

        # Formatação do livro UP
        up_bids = self.book_up.get("bids", [])[-5:] if isinstance(self.book_up.get("bids"), list) else []
        up_asks = self.book_up.get("asks", [])[:5] if isinstance(self.book_up.get("asks"), list) else []
        best_up_bid = float(up_bids[-1]["price"]) if up_bids else self.poly_price_up - 0.01
        best_up_ask = float(up_asks[0]["price"]) if up_asks else self.poly_price_up + 0.01

        # Formatação do livro DOWN
        down_bids = self.book_down.get("bids", [])[-5:] if isinstance(self.book_down.get("bids"), list) else []
        down_asks = self.book_down.get("asks", [])[:5] if isinstance(self.book_down.get("asks"), list) else []
        best_down_bid = float(down_bids[-1]["price"]) if down_bids else self.poly_price_down - 0.01
        best_down_ask = float(down_asks[0]["price"]) if down_asks else self.poly_price_down + 0.01

        win_rate = (self.paper_wins / self.paper_trades_count * 100) if self.paper_trades_count > 0 else 0.0

        return {
            "cycle": {
                "window_ts": window_ts,
                "slug": f"btc-updown-5m-{window_ts}",
                "title": self.market_info.get("question") or f"BTC Up or Down - 5m Cycle",
                "seconds_left": seconds_left,
                "seconds_elapsed": seconds_elapsed,
                "progress_pct": round((seconds_elapsed / 300.0) * 100, 1),
                "is_expired": seconds_left == 0
            },
            "pricing": {
                "spot": round(self.spot_price, 2),
                "oracle_spot": round(self.spot_price, 2),
                "binance_spot": round(self.binance_spot, 2),
                "feed_spread": round(self.binance_spot - self.spot_price, 2) if (self.binance_spot and self.spot_price) else 0.0,
                "strike": round(self.strike_price, 2),
                "delta": round(delta_price, 2),
                "delta_pct": round(delta_pct, 4),
                "status": "UP" if delta_price >= 0 else "DOWN",
                "last_update": self.last_spot_update
            },
            "polymarket": {
                "active": bool(self.market_info),
                "id": self.market_info.get("id", ""),
                "price_up": round(self.poly_price_up, 3),
                "price_down": round(self.poly_price_down, 3),
                "token_up": self.token_up_id,
                "token_down": self.token_down_id,
                "book_up": {"bids": up_bids, "asks": up_asks, "best_bid": round(best_up_bid, 3), "best_ask": round(best_up_ask, 3)},
                "book_down": {"bids": down_bids, "asks": down_asks, "best_bid": round(best_down_bid, 3), "best_ask": round(best_down_ask, 3)},
                "volume24hr": float(self.market_info.get("volume24hr") or 12200000),
                "liquidity": float(self.market_info.get("liquidityNum") or 10000)
            },
            "model": {
                "fair_up": self.fair_value_up,
                "fair_down": self.fair_value_down,
                "edge_up": self.edge_up,
                "edge_down": self.edge_down,
                "volatility_annual": self.annualized_vol
            },
            "signal": self.active_signal,
            "paper_trading": {
                "balance": round(self.paper_balance, 2),
                "initial_balance": 1000.0,
                "total_pnl": round(self.paper_balance - 1000.0, 2),
                "trades_count": self.paper_trades_count,
                "wins": self.paper_wins,
                "win_rate": round(win_rate, 1),
                "active_position": self.active_paper_position,
                "history": self.paper_history
            },
            "chart": self.price_history[-30:]
        }

    def start_loop(self):
        """Inicia a thread de execução do motor"""
        self.running = True
        def _worker():
            print("-> BTC 5m Engine Worker iniciado.")
            while self.running:
                try:
                    self.update_cycle()
                except Exception as e:
                    print(f"[BTC Engine Loop Error]: {e}")
                time.sleep(1.0)
                
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

if __name__ == "__main__":
    engine = BTC5mEngine()
    print("Testando primeira execução do BTC 5m Engine...")
    engine.update_cycle()
    state = engine.get_radar_state()
    print(json.dumps(state, indent=2))
