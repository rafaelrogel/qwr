"""
=============================================================================
SOLANA 5-MINUTE ALGO TRADER (POLYMARKET sol-updown-5m) — MODO PAPER
=============================================================================
- Exchange: Polymarket CLOB — Série: sol-updown-5m-{window_ts}
- Frequência: Ciclos de 5 Minutos (300 segundos)
- Ponto de Avaliação: 135s (2m15s da vela de 5m)
- Estratégia Quantitativa:
  * Deadband Dinâmico: 5.0 bps (Jev Sweet-Spot, min floor $0.06)
  * Microprice Ponderado L2 (PolyResearch Robotics)
  * Teto de Preço: 60 centavos ($0.60)
  * Filtro Jev Trend Continuation (Alinhamento com vela de 5m anterior da Binance)
  * Take-Profit Antecipado (SirMartingale): Venda com lucro se cota atingir >= 86¢
- Modo: PAPER (Simulação em tempo real com livro de ofertas oficial da CLOB)
=============================================================================
"""

import os
import sys
import time
import json
import urllib.request
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

# Garante suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_JSON = os.path.join(BASE_DIR, "sol_trading_journal.json")

# ===================== PARÂMETROS QUANTITATIVOS (JEV AI CALIBRATED) =====================
FIXED_STAKE = 1.00                # $1.00 por aposta
DEADBAND_BPS = 0.00050            # 5.0 bps (0.050%) do preço da SOL
DEADBAND_MIN_FLOOR = 0.06         # Piso mínimo de $0.06 de variação na SOL
PRIMARY_MAX_PRICE = 0.60          # Preço máximo de entrada (60¢)
PRIMARY_MIN_PRICE = 0.35          # Preço mínimo de entrada (35¢)
TAKE_PROFIT_PRICE = 0.86          # Take Profit antecipado (86¢)
EVAL_POINT_SEC = 135              # 135s (2m15s da vela de 5m)
REQUIRE_PRIOR_CANDLE = True       # Filtro Jev Trend Continuation

# ===================== DATA PROVIDERS (BINANCE REF) =====================
def get_binance_sol_spot() -> Optional[float]:
    """Preço Spot em tempo real da Solana (SOL/USDT) na Binance"""
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
        "https://data-api.binance.vision/api/v3/ticker/price?symbol=SOLUSDT"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return float(json.loads(r.read().decode())["price"])
        except Exception:
            pass
    return None

def get_binance_sol_5m_prior_candle() -> Optional[Dict[str, Any]]:
    """Consulta a última vela de 5m FECHADA na Binance para validação de tendência"""
    urls = [
        "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2",
        "https://data-api.binance.vision/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read().decode())
                if len(data) >= 2:
                    prior = data[0]
                    p_open = float(prior[1])
                    p_close = float(prior[4])
                    p_dir = "UP" if p_close >= p_open else "DOWN"
                    ret_bps = (abs(p_close - p_open) / p_open) * 10000
                    return {"dir": p_dir, "open": p_open, "close": p_close, "ret_bps": ret_bps}
        except Exception:
            pass
    return None

def get_sol_candle_open(window_ts: int) -> Optional[float]:
    """Obtém a abertura da vela de 5m correspondente ao window_ts"""
    url = f"https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&startTime={window_ts * 1000}&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return float(data[0][1])
    except Exception:
        pass
    return None

# ===================== POLYMARKET CLOB & GAMMA API =====================
def get_polymarket_sol_market(window_ts: int) -> Optional[Dict[str, Any]]:
    """Busca o mercado de Solana 5m na Gamma API"""
    slug = f"sol-updown-5m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return data[0]
    except Exception:
        pass
    return None

def get_clob_orderbook(token_id: str) -> Optional[Dict[str, Any]]:
    """Consulta livro de ordens L2 e calcula Microprice e Imbalance"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            book = json.loads(r.read().decode())
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            if not bids or not asks:
                return None

            bids_sorted = sorted(bids, key=lambda x: float(x["price"]), reverse=True)
            asks_sorted = sorted(asks, key=lambda x: float(x["price"]))

            best_bid = float(bids_sorted[0]["price"])
            best_ask = float(asks_sorted[0]["price"])
            bid_size = float(bids_sorted[0]["size"])
            ask_size = float(asks_sorted[0]["size"])

            spread = round(best_ask - best_bid, 4)
            # Microprice ponderado pelo tamanho do topo
            total_size = bid_size + ask_size
            microprice = ((best_bid * ask_size) + (best_ask * bid_size)) / total_size if total_size > 0 else (best_bid + best_ask) / 2.0
            imbalance = (bid_size - ask_size) / total_size if total_size > 0 else 0.0

            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "spread": spread,
                "microprice": round(microprice, 4),
                "imbalance": round(imbalance, 2)
            }
    except Exception:
        return None

# ===================== SOLANA PAPER TRADER ENGINE =====================
class SolanaPaperTrader5M:
    def __init__(self):
        self.balance = 25.00 # Banca virtual inicial
        self.trades = []
        self.load_journal()

    def load_journal(self):
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.balance = data.get("current_balance", self.balance)
                    self.trades = data.get("trades", [])
            except Exception:
                pass

    def save_journal(self, trade_data: dict):
        self.trades.append(trade_data)
        wins = sum(1 for t in self.trades if "VITÓRIA" in t.get("result", ""))
        losses = sum(1 for t in self.trades if "DERROTA" in t.get("result", ""))
        total = len(self.trades)
        wr = round(wins / total * 100, 1) if total > 0 else 0.0

        journal = {
            "mode": "PAPER_SIMULATION_SOL_5M",
            "current_balance": round(self.balance, 4),
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wr,
            "trades": self.trades
        }
        try:
            with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                json.dump(journal, f, indent=2)
        except Exception as e:
            print(f"[Erro ao gravar {JOURNAL_JSON}]: {e}")

    def run_cycle(self):
        now_ts = int(time.time())
        window_ts = (now_ts // 300) * 300
        elapsed_sec = now_ts - window_ts
        remaining_sec = 300 - elapsed_sec
        dt_str = datetime.fromtimestamp(window_ts, timezone.utc).strftime("%H:%M:%S")

        print("\n" + "=" * 80)
        print(f" [SOLANA 5M PAPER] Janela Ativa: {dt_str} UTC | Timestamp: {window_ts}")
        print(f" Tempo Decorrido: {elapsed_sec}s / 300s | Restam: {remaining_sec}s | Saldo: ${self.balance:,.2f} USD")
        print("=" * 80)

        # 1. Aguarda até o ponto de decisão (135s)
        if elapsed_sec < EVAL_POINT_SEC:
            wait = EVAL_POINT_SEC - elapsed_sec
            print(f"[*] Aguardando {wait}s até o ponto quantitativo de decisão ({EVAL_POINT_SEC}s / 45% da vela)...")
            time.sleep(min(wait, 15))
            return

        # 2. Busca Mercado na Polymarket
        market = get_polymarket_sol_market(window_ts)
        if not market:
            print(f"[i] Mercado sol-updown-5m-{window_ts} ainda não listado na Polymarket. Aguardando...")
            time.sleep(15)
            return

        try:
            tokens = json.loads(market.get("clobTokenIds", "[]"))
            token_up = tokens[0]
            token_down = tokens[1]
        except Exception:
            print("[!] Falha ao decodificar clobTokenIds de Solana.")
            time.sleep(15)
            return

        # 3. Strike e Spot Atual
        strike = get_sol_candle_open(window_ts)
        spot_now = get_binance_sol_spot()
        if not strike or not spot_now:
            print("[!] Falha ao ler Strike/Spot da Solana. Aguardando...")
            time.sleep(10)
            return

        delta = spot_now - strike
        dynamic_deadband = max(DEADBAND_MIN_FLOOR, round(strike * DEADBAND_BPS, 4))

        print(f"\n[📊 ANÁLISE QUANTITATIVA SOLANA]:")
        print(f"   Strike (Open): ${strike:.2f} | Spot Atual (135s): ${spot_now:.2f}")
        print(f"   Drift Real (Delta): ${delta:+.4f} | Deadband Dinâmico: ${dynamic_deadband:.4f} ({DEADBAND_BPS*10000:.1f} bps)")

        # 4. Decisão de Sinal
        candidate_side = None
        target_token = None
        if delta >= dynamic_deadband:
            candidate_side = "UP"
            target_token = token_up
            print(f"   -> [SINAL INTRA-VELA]: UP (Drift de +${delta:.4f} superou deadband de ${dynamic_deadband:.4f})")
        elif delta <= -dynamic_deadband:
            candidate_side = "DOWN"
            target_token = token_down
            print(f"   -> [SINAL INTRA-VELA]: DOWN (Drift de -${abs(delta):.4f} superou deadband de ${dynamic_deadband:.4f})")
        else:
            print(f"   -> [🛡️ FILTRO DEADBAND]: Delta de ${delta:+.4f} na zona morta (< ${dynamic_deadband:.4f}). Preservando capital.")
            time.sleep(25)
            return

        # 5. Filtro de Vela Anterior (Jev Trend Continuation)
        if REQUIRE_PRIOR_CANDLE:
            prior = get_binance_sol_5m_prior_candle()
            if prior:
                prior_dir = prior["dir"]
                ret_bps = prior["ret_bps"]
                print(f"   [🕯️ FILTRO VELA ANTERIOR - JEV]: Vela 5m Anterior fechou {prior_dir} ({ret_bps:.1f} bps)")
                if candidate_side != prior_dir:
                    print(f"   -> [🛡️ VETO JEV]: Sinal {candidate_side} rejeitado por divergir da vela 5m anterior ({prior_dir}).")
                    print("      Preservando capital contra reversões e repiques de contratendência.")
                    time.sleep(25)
                    return
                else:
                    print(f"   -> [🔥 CONFIRMAÇÃO JEV]: Tendência da vela anterior ({prior_dir}) alinhada com drift ({candidate_side})! Convicção alta.")

        # 6. Microestrutura do Order Book CLOB da Polymarket
        book = get_clob_orderbook(target_token)
        if not book:
            print("[!] Livro de ordens da CLOB não retornou dados. Pulando.")
            time.sleep(15)
            return

        best_ask = book["best_ask"]
        best_bid = book["best_bid"]
        microprice = book["microprice"]
        spread = book["spread"]
        imbalance = book["imbalance"]

        print(f"\n[⚡ MICROESTRUTURA CLOB SOL 5M]:")
        print(f"   Best Bid: ${best_bid:.2f} | Best Ask: ${best_ask:.2f} | Spread: ${spread:.4f}")
        print(f"   Microprice: ${microprice:.4f} | Imbalance L1: {imbalance:+.2f}")

        # Filtro de Preço Sniper (Teto de 60¢)
        exec_price = microprice if microprice <= best_ask else best_ask
        if exec_price > PRIMARY_MAX_PRICE:
            print(f"   [🛡️ FILTRO TETO DE PREÇO]: Preço ${exec_price:.2f} > ${PRIMARY_MAX_PRICE:.2f} (Breakeven desfavorável). Pulando entrada.")
            time.sleep(25)
            return

        stake = FIXED_STAKE
        shares = round(stake / exec_price, 4)
        print(f"\n[🚀 ORDEM PAPER EXECUTADA]: 1 Contrato SOL 5m ({candidate_side}) @ ${exec_price:.2f} | Shares: {shares}")

        # 7. Monitoramento até o Fechamento (Take-Profit e Liquidação)
        print(f"[🎯 MONITORAMENTO]: Acompanhando Take-Profit (>= ${TAKE_PROFIT_PRICE:.2f}) até os 300s...")
        sold_early = False
        while True:
            cur_elapsed = int(time.time()) - window_ts
            if cur_elapsed >= 285:
                break

            # Checagem de Take-Profit no Book
            cur_book = get_clob_orderbook(target_token)
            if cur_book and cur_book["best_bid"] >= TAKE_PROFIT_PRICE:
                sold_early = True
                sell_price = cur_book["best_bid"]
                payout = round(shares * sell_price, 4)
                cycle_pnl = round(payout - stake, 4)
                self.balance += cycle_pnl
                print(f"\n[💰 TAKE-PROFIT SOLANA!]: Vendido antecipadamente a ${sell_price:.2f}!")
                print(f"   Payout: ${payout:.2f} | P&L: {cycle_pnl:+.2f} USD | Novo Saldo: ${self.balance:,.2f}")
                self.save_journal({
                    "cycle_ts": window_ts,
                    "time_str": dt_str,
                    "strike": strike,
                    "target_side": candidate_side,
                    "entry_price": exec_price,
                    "shares": shares,
                    "result": "VITÓRIA (TAKE-PROFIT)",
                    "sold_early": True,
                    "sell_price": sell_price,
                    "payout": payout,
                    "pnl": cycle_pnl,
                    "balance": round(self.balance, 4)
                })
                time.sleep(max(1, 300 - cur_elapsed))
                return

            time.sleep(5)

        # 8. Liquidação no Fechamento da Vela (300s)
        if not sold_early:
            time.sleep(max(1, 300 - (int(time.time()) - window_ts)) + 3)
            final_spot = get_binance_sol_spot() or spot_now
            is_win = (final_spot >= strike) if candidate_side == "UP" else (final_spot < strike)
            winner = "UP" if final_spot >= strike else "DOWN"
            payout = round(shares * 1.00, 4) if is_win else 0.00
            cycle_pnl = round(payout - stake, 4)
            self.balance += cycle_pnl
            res_str = "VITÓRIA" if is_win else "DERROTA"

            print(f"\n[🏁 APURAÇÃO FINAL SOLANA 5M]:")
            print(f"   Strike: ${strike:.2f} | Final Spot: ${final_spot:.2f} | Vencedor: {winner}")
            print(f"   Resultado: {res_str} | Payout: ${payout:.2f} | P&L Ciclo: {cycle_pnl:+.2f} USD")
            print(f"   Saldo Atualizado: ${self.balance:,.2f} USD")

            self.save_journal({
                "cycle_ts": window_ts,
                "time_str": dt_str,
                "strike": strike,
                "final_spot": final_spot,
                "target_side": candidate_side,
                "entry_price": exec_price,
                "shares": shares,
                "winner": winner,
                "result": res_str,
                "sold_early": False,
                "payout": payout,
                "pnl": cycle_pnl,
                "balance": round(self.balance, 4)
            })

    def start(self):
        print("\n" + "=" * 80)
        print("  INICIANDO BOT SOLANA 5-MINUTE ALGO TRADER (POLYMARKET)")
        print(f"  Modo: PAPER | Banca Inicial: ${self.balance:.2f} USD")
        print("=" * 80)
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                print(f"[Erro no ciclo Solana]: {e}")
            time.sleep(5)

if __name__ == "__main__":
    bot = SolanaPaperTrader5M()
    bot.start()
