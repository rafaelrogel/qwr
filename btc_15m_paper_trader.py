"""
Desk 3B — Polymarket BTC 15-Minute Paper Trader
================================================================================
Modo: PAPER (simulacao pura — nenhuma ordem real colocada)
Mercado: btc-updown-15m-{window_ts} (Polymarket Gamma API)
Janela: 900 segundos (15 minutos)
Ponto de Entrada: 700s (77% da vela — JEV: mais tarde que o 5m para deixar direcao confirmar)
Deadband: $25.00 minimo (JEV: maior que o 5m pois 15m tem mais ruido de reversao)
Objetivo: Validar edge por 2 semanas em paper antes de qualquer promocao para LIVE

Calibracao JEV SystemOne vs Desk 1 (BTC 5m):
  Desk 1 — entrada 135s/300s (45%), deadband $17.52, stake $1.00 LIVE
  Desk 3B — entrada 700s/900s (77%), deadband $25.00, stake $1.00 PAPER
================================================================================
"""
import os
import sys

# Garante UTF-8 no Windows (sem crash de emoji)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import json
import urllib.request
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from anti_sweep_shield import evaluate_anti_sweep_shield

def _global_exception_handler(exc_type, exc_val, exc_tb):
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desk3b_crash.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now(timezone.utc).isoformat()}] CRASH:\n")
        traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
    sys.__excepthook__(exc_type, exc_val, exc_tb)

sys.excepthook = _global_exception_handler

# ============================================================
#  CONSTANTES — CALIBRADAS PARA BTC 15M (JEV SystemOne)
# ============================================================
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_JSON       = os.path.join(BASE_DIR, "desk3b_btc15m_paper_state.json")
JOURNAL_JSON     = os.path.join(BASE_DIR, "desk3b_btc15m_paper_journal.json")

WINDOW_SIZE      = 900      # 15 minutos em segundos
ENTRY_POINT      = 500      # Entrada antecipada aos 500s (55% da vela) — Consenso JEV
TP_POINT         = 620      # Take-profit monitoramento após 620s
CLOSE_POINT      = 870      # Encerramento forçado aos 870s se sem resolucao
FIXED_STAKE      = 1.00     # Aposta simulada em USDC (paper)
INITIAL_BALANCE  = 100.00   # Saldo inicial de paper

# Filtros recalibrados para 15m (JEV: assimetria positiva estrita)
DEADBAND_FLOOR   = 25.0     # Drift mínimo em USD para entrar ($25 vs $17.52 no 5m)
DEADBAND_BPS     = 0.00030  # 3.0 bps do strike (ligeiramente maior que 5m)
PRIMARY_MIN_PRICE = 0.40    # Preco mínimo da cota JEV (elimina cotas de cauda com spread largo e falso SL)
PRIMARY_MAX_PRICE = 0.65    # Preco máximo estrito JEV (veta compras a 80c-99c)
STOP_LOSS_MIN_BID = 0.15    # Preço mínimo de bid aceitável para Stop-Loss de emergência
SPREAD_MAX       = 0.06     # Spread máximo tolerável no CLOB
BINANCE_DRIFT_UP  = -8.0   # Drift Binance mínimo para entrar em UP (mais tolerante que 5m)
BINANCE_DRIFT_DOWN = 8.0   # Drift Binance máximo para entrar em DOWN

# Circuit breakers (paper mode — para aprendizado)
MAX_LOSS_PAPER   = -20.00   # Pausa paper se perder $20 simulados
TAKE_PROFIT_PAPER = 50.00   # Pausa paper se lucrar $50 simulados


# ============================================================
#  FUNÇÕES DE DADOS (reutilizadas do Desk 1)
# ============================================================

def get_binance_spot() -> Optional[float]:
    """Busca preco spot BTC/USDT na Binance"""
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return float(json.loads(r.read().decode())["price"])
        except Exception:
            pass
    return None


def get_chainlink_price() -> Optional[float]:
    """Consulta oraculo Chainlink BTC/USD na Polygon (contrato AggregatorV3)"""
    rpcs = [
        "https://polygon.drpc.org",
        "https://gateway.tenderly.co/public/polygon",
        "https://polygon.publicnode.com",
    ]
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "eth_call",
        "params": [{"to": "0xc907E116054Ad103354f2D350FD2514433D57F6f", "data": "0xfeaf968c"}, "latest"],
        "id": 1
    }).encode("utf-8")
    for rpc in rpcs:
        try:
            req = urllib.request.Request(rpc, data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.5) as r:
                res = json.loads(r.read().decode())
                if "result" in res and res["result"] and len(res["result"]) >= 130:
                    price = int(res["result"][66:130], 16) / 1e8
                    if price > 10000:
                        return round(price, 2)
        except Exception:
            continue
    return None


def get_candle_open_15m(window_ts: int) -> Optional[float]:
    """Busca preco de abertura da vela 15m na Binance como fallback do strike"""
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=3"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            klines = json.loads(r.read().decode())
            for k in klines:
                if int(k[0]) // 1000 == window_ts:
                    return float(k[1])
            if klines:
                return float(klines[-1][1])
    except Exception:
        pass
    return None


def get_polymarket_15m_market(window_ts: int) -> Optional[Dict[str, Any]]:
    """Busca mercado btc-updown-15m na Gamma API para o window_ts dado"""
    slug = f"btc-updown-15m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Desk3BPaperBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return data[0]
    except Exception as e:
        print(f"   [Gamma API 15m]: {e}")
    return None


def get_polymarket_15m_resolution(window_ts: int, max_retries: int = 20) -> Optional[str]:
    """
    Busca resolucao oficial do mercado btc-updown-15m.
    Aguarda ate 60s pos-fechamento para que o relayer processe o TWAP.
    """
    slug = f"btc-updown-15m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Desk3BPaperBot/1.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                events = json.loads(r.read().decode())
                if events:
                    markets = events[0].get("markets", [])
                    for m in markets:
                        prices = m.get("outcomePrices", [])
                        if isinstance(prices, str):
                            try:
                                prices = json.loads(prices)
                            except Exception:
                                prices = []
                        if prices and len(prices) >= 2:
                            try:
                                p_up = float(prices[0])
                                p_down = float(prices[1])
                                if p_up >= 0.98:
                                    return "UP"
                                elif p_down >= 0.98:
                                    return "DOWN"
                            except Exception:
                                pass
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(3)
    return None


def get_clob_orderbook_15m(token_id: str) -> Optional[Dict[str, Any]]:
    """Consulta order book L2 do token (read-only — sem autenticacao)"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Desk3BPaperBot/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            book = json.loads(r.read().decode())
            bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", [])
                    if "price" in b and "size" in b and float(b["size"]) >= 1.0]
            asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", [])
                    if "price" in a and "size" in a and float(a["size"]) >= 1.0]
            if not bids or not asks:
                return None
            best_bid = max(bids, key=lambda x: x[0])[0]
            best_ask = min(asks, key=lambda x: x[0])[0]
            top_bid_sz = max(bids, key=lambda x: x[0])[1]
            top_ask_sz = min(asks, key=lambda x: x[0])[1]
            spread = best_ask - best_bid
            microprice = (best_bid * top_ask_sz + best_ask * top_bid_sz) / (top_bid_sz + top_ask_sz) \
                if (top_bid_sz + top_ask_sz) > 0 else (best_bid + best_ask) / 2.0
            return {
                "best_bid": round(best_bid, 4),
                "best_ask": round(best_ask, 4),
                "spread": round(spread, 4),
                "microprice": round(microprice, 4),
                "top_bid_size": round(top_bid_sz, 2),
                "top_ask_size": round(top_ask_sz, 2),
            }
    except Exception:
        return None


# ============================================================
#  JOURNAL
# ============================================================

def load_journal() -> Dict:
    if os.path.exists(JOURNAL_JSON):
        try:
            with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "desk": "Desk 3B — BTC 15m Polymarket PAPER",
        "mode": "PAPER",
        "initial_balance": INITIAL_BALANCE,
        "current_balance": INITIAL_BALANCE,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "trades": []
    }


def save_journal(j: Dict):
    try:
        with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
            json.dump(j, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"   [AVISO Journal]: {e}")


def save_state(data: Dict):
    try:
        with open(STATE_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"   [AVISO State]: {e}")


# ============================================================
#  CICLO PRINCIPAL
# ============================================================

def run_cycle(journal: Dict) -> Dict:
    """Executa um ciclo completo de uma janela de 15 minutos"""
    now = time.time()
    # Calcula timestamp da janela actual (arredonda para 900s)
    window_ts = int(now) - (int(now) % WINDOW_SIZE)
    elapsed = now - window_ts
    seconds_left = WINDOW_SIZE - elapsed

    now_utc = datetime.fromtimestamp(now, tz=timezone.utc)
    ts_str = now_utc.strftime("%Y-%m-%dT%H:%M:%S UTC")

    print(f"\n{'='*80}")
    print(f"  [DESK 3B] BTC 15m POLYMARKET PAPER | Janela: {datetime.fromtimestamp(window_ts, tz=timezone.utc).strftime('%H:%M')} UTC")
    print(f"  Elapsed: {int(elapsed)}s / {WINDOW_SIZE}s | Restam: {int(seconds_left)}s | Saldo Paper: ${journal['current_balance']:.2f}")
    print(f"{'='*80}")

    # Guarda state basico
    state = {
        "desk": "Desk 3B BTC 15m Paper",
        "window_ts": window_ts,
        "seconds_elapsed": int(elapsed),
        "seconds_left": int(seconds_left),
        "progress_pct": round(elapsed / WINDOW_SIZE * 100, 1),
        "mode": "PAPER",
        "balance": round(journal["current_balance"], 2),
        "status_signal": "Inicializando...",
        "spot": 0.0,
        "strike": 0.0,
        "delta": 0.0,
    }

    # Circuit breakers paper
    pnl_total = journal.get("total_pnl", 0.0)
    if pnl_total <= MAX_LOSS_PAPER:
        print(f"   [CIRCUIT BREAKER]: P&L cumulativo ${pnl_total:.2f} atingiu teto de perda paper (${MAX_LOSS_PAPER:.2f}).")
        state["status_signal"] = f"Circuit Breaker Paper — Loss Limit (${pnl_total:.2f})"
        save_state(state)
        # Aguarda inicio da proxima janela
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    if pnl_total >= TAKE_PROFIT_PAPER:
        print(f"   [CIRCUIT BREAKER]: P&L cumulativo ${pnl_total:.2f} atingiu meta paper (${TAKE_PROFIT_PAPER:.2f}). Parabens!")
        state["status_signal"] = f"Circuit Breaker Paper — Take Profit (${pnl_total:.2f})"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # Aguarda ponto de entrada (700s) em loop contínuo
    while elapsed < ENTRY_POINT:
        wait = ENTRY_POINT - elapsed
        print(f"   [AGUARDANDO ENTRADA]: {int(elapsed)}s elapsed. Entrada em {ENTRY_POINT}s. Aguardando {int(wait)}s...")
        state["seconds_elapsed"] = int(elapsed)
        state["seconds_left"] = int(seconds_left)
        state["progress_pct"] = round(elapsed / WINDOW_SIZE * 100, 1)
        state["status_signal"] = f"Aguardando Ponto de Entrada ({int(elapsed)}s / {ENTRY_POINT}s)"

        # Busca spot enquanto aguarda
        spot = get_chainlink_price() or get_binance_spot()
        if spot:
            state["spot"] = round(spot, 2)

        # Busca strike da vela 15m (Binance open ou spot inicial)
        try:
            k_open = get_candle_open_15m(window_ts)
            if k_open:
                state["strike"] = round(k_open, 2)
            elif spot and state.get("strike", 0.0) == 0.0:
                state["strike"] = round(spot, 2)
        except Exception:
            if spot and state.get("strike", 0.0) == 0.0:
                state["strike"] = round(spot, 2)

        if state.get("strike", 0.0) > 0 and spot:
            state["delta"] = round(spot - state["strike"], 2)

        save_state(state)
        sleep_dur = min(wait, 10)
        time.sleep(sleep_dur)
        now = time.time()
        elapsed = now - window_ts
        seconds_left = WINDOW_SIZE - elapsed

    # ── PONTO DE ENTRADA (700s) ─────────────────────────────────────────────
    print(f"\n   [PONTO DE DECISAO 700s]: Avaliando entrada BTC 15m...")

    # 1. Busca mercado
    market = get_polymarket_15m_market(window_ts)
    if not market:
        print("   [SEM MERCADO]: btc-updown-15m nao encontrado na Gamma API. Pulando janela.")
        state["status_signal"] = "Sem mercado Polymarket 15m disponivel"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    question = market.get("question", "")
    active = market.get("active", False)
    outcome_prices_raw = market.get("outcomePrices", ["0.5", "0.5"])
    if isinstance(outcome_prices_raw, str):
        try:
            outcome_prices = json.loads(outcome_prices_raw)
        except Exception:
            outcome_prices = ["0.5", "0.5"]
    else:
        outcome_prices = outcome_prices_raw or ["0.5", "0.5"]

    tokens_raw = market.get("clobTokenIds", "[]")
    try:
        tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw
    except Exception:
        tokens = []

    print(f"   Mercado: {question}")
    p_up_disp = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
    p_down_disp = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
    print(f"   Active: {active} | UP: ${p_up_disp:.3f} | DOWN: ${p_down_disp:.3f}")

    if not active:
        print("   [MERCADO INATIVO]: Pulando janela.")
        state["status_signal"] = "Mercado inativo"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # 2. Strike da janela — tenta extrair da question string
    strike = None
    try:
        # Question: "Bitcoin Up or Down - October 1, 4:30AM-4:45AM ET"
        # Strike vem do preco Chainlink no inicio da janela
        strike = get_candle_open_15m(window_ts)
    except Exception:
        pass
    if not strike:
        strike = get_chainlink_price() or get_binance_spot()

    if not strike:
        print("   [SEM STRIKE]: Impossivel obter preco de referencia. Pulando.")
        state["status_signal"] = "Sem preco de referencia"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    state["strike"] = round(strike, 2)

    # 3. Spot actual (Chainlink)
    spot = get_chainlink_price()
    if not spot:
        spot = get_binance_spot()
    if not spot:
        print("   [SEM SPOT]: Impossivel obter spot actual. Pulando.")
        state["status_signal"] = "Sem spot actual"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    state["spot"] = round(spot, 2)
    delta = spot - strike
    state["delta"] = round(delta, 2)

    # 4. Deadband dinamico
    deadband_dyn = max(DEADBAND_FLOOR, strike * DEADBAND_BPS)
    state["deadband"] = round(deadband_dyn, 2)
    print(f"   Strike: ${strike:,.2f} | Spot: ${spot:,.2f} | Delta: ${delta:+.2f} | Deadband: ${deadband_dyn:.2f}")

    if abs(delta) < deadband_dyn:
        print(f"   [FILTRO DEADBAND]: |Delta| ${abs(delta):.2f} < Deadband ${deadband_dyn:.2f}. Sem sinal claro.")
        state["status_signal"] = f"Deadband — Delta ${delta:+.2f} / Piso ${deadband_dyn:.2f}"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # 5. Direccao
    target_side = "UP" if delta > 0 else "DOWN"
    print(f"   Direcao: {target_side} (Delta ${delta:+.2f})")

    # 6. Confirmacao Binance (drift adicional)
    binance_spot = get_binance_spot()
    if binance_spot:
        binance_drift = binance_spot - strike
        print(f"   Binance drift: ${binance_drift:+.2f}")
        if target_side == "UP" and binance_drift < BINANCE_DRIFT_UP:
            print(f"   [FILTRO BINANCE]: Drift Binance ${binance_drift:+.2f} < ${BINANCE_DRIFT_UP:.1f} para UP. Abortando.")
            state["status_signal"] = f"Veto Binance Drift — UP rejeitado (${binance_drift:+.2f})"
            save_state(state)
            time.sleep(max(1, int(seconds_left) + 5))
            return journal
        if target_side == "DOWN" and binance_drift > BINANCE_DRIFT_DOWN:
            print(f"   [FILTRO BINANCE]: Drift Binance ${binance_drift:+.2f} > ${BINANCE_DRIFT_DOWN:.1f} para DOWN. Abortando.")
            state["status_signal"] = f"Veto Binance Drift — DOWN rejeitado (${binance_drift:+.2f})"
            save_state(state)
            time.sleep(max(1, int(seconds_left) + 5))
            return journal

    # 7. Order Book L2 — preco e spread (read-only)
    token_idx = 0 if target_side == "UP" else 1
    target_token = tokens[token_idx] if len(tokens) > token_idx else None
    entry_price = None

    if target_token:
        ob = get_clob_orderbook_15m(target_token)
        if ob:
            entry_price = ob["best_ask"]
            spread = ob["spread"]
            microprice = ob["microprice"]
            print(f"   CLOB L2: Best Ask=${entry_price:.3f} | Spread=${spread:.3f} | Microprice=${microprice:.4f}")
            if spread > SPREAD_MAX:
                print(f"   [FILTRO SPREAD]: Spread ${spread:.3f} > max ${SPREAD_MAX:.3f}. Abortando.")
                state["status_signal"] = f"Veto Spread CLOB (${spread:.3f})"
                save_state(state)
                time.sleep(max(1, int(seconds_left) + 5))
                return journal
            if entry_price < PRIMARY_MIN_PRICE or entry_price > PRIMARY_MAX_PRICE:
                print(f"   [FILTRO PRECO]: ${entry_price:.3f} fora da faixa [${PRIMARY_MIN_PRICE:.2f}, ${PRIMARY_MAX_PRICE:.2f}]. Abortando.")
                state["status_signal"] = f"Veto Preco (${entry_price:.3f} fora da faixa)"
                save_state(state)
                time.sleep(max(1, int(seconds_left) + 5))
                return journal

    if not entry_price:
        entry_price = float(outcome_prices[token_idx])

    # Validação estrita universal de preço (CLOB ou Gamma API — Regra JEV Anti-Assimetria)
    if entry_price < PRIMARY_MIN_PRICE or entry_price > PRIMARY_MAX_PRICE:
        print(f"   [FILTRO PREÇO ESTRITO JEV]: Preço ${entry_price:.3f} fora da faixa institucional [${PRIMARY_MIN_PRICE:.2f}, ${PRIMARY_MAX_PRICE:.2f}]. Abortando para proteger capital.")
        state["status_signal"] = f"Veto Preco JEV (${entry_price:.3f} fora da faixa)"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # ── ENTRADA PAPER ────────────────────────────────────────────────────────
    shares = round(FIXED_STAKE / entry_price, 4)
    now_utc_str = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")

    print(f"\n   [ENTRADA PAPER] {target_side} @ ${entry_price:.4f} | {shares:.4f} cotas | Stake: ${FIXED_STAKE:.2f}")
    print(f"   Payout potencial: ${shares:.4f} | EV estimado: ${shares - FIXED_STAKE:+.4f}")

    state["status_signal"] = f"PAPER {target_side} @ ${entry_price:.4f} — Monitorando..."
    state["entry_side"] = target_side
    state["entry_price"] = entry_price
    state["entry_time"] = now_utc_str
    save_state(state)

    # ── MONITORAMENTO POS-ENTRADA COM DEFESA ATIVA (BONEREAPER & SIRMARTINGALE) ──
    cur_time = time.time()
    cur_elapsed = cur_time - window_ts

    while cur_elapsed < WINDOW_SIZE + 30:
        cur_elapsed = time.time() - window_ts
        remaining = WINDOW_SIZE - cur_elapsed

        # Amostragem contínua do Order Book para gestão da posição
        if target_token:
            ob_now = get_clob_orderbook_15m(target_token)
            if ob_now:
                cur_price = ob_now.get("best_bid", entry_price)
                cur_pnl = (cur_price - entry_price) * shares
                state["current_price"] = cur_price
                state["unrealized_pnl"] = round(cur_pnl, 4)

                # 1. BONEREAPER STOP-LOSS (Defesa de Emergência contra Reversão de Delta)
                cur_spot = get_chainlink_price() or get_binance_spot()
                if cur_spot:
                    live_delta = cur_spot - strike
                    reversed_delta = (target_side == "UP" and live_delta < -DEADBAND_FLOOR) or \
                                     (target_side == "DOWN" and live_delta > DEADBAND_FLOOR)
                else:
                    live_delta = delta
                    reversed_delta = False

                # SL Dinâmico Proporcional JEV: Stop só dispara em caso de reversão real de Delta OU perda de > 40% da cota comprada
                sl_threshold = max(STOP_LOSS_MIN_BID, round(entry_price * 0.60, 3))
                if (reversed_delta or cur_price <= sl_threshold) and cur_elapsed >= ENTRY_POINT + 30:
                    if cur_price >= STOP_LOSS_MIN_BID:
                        print(f"\n   [🚨 BONEREAPER STOP-LOSS ACIONADO (PROPORCIONAL JEV)]:")
                        print(f"      Delta reverteu ({live_delta:+.2f}) ou cota caiu para ${cur_price:.3f} (<= ${sl_threshold:.3f}). Vendendo antecipado!")
                        final_price = cur_price
                        final_pnl = round((final_price - entry_price) * shares, 4)
                        outcome_label = "DEFESA_SL"
                        journal = _register_trade(journal, window_ts, target_side, entry_price,
                                                  final_price, shares, final_pnl, outcome_label, live_delta)
                        save_state({**state, "status_signal": f"DEFESA SL @ ${final_price:.3f} | PnL ${final_pnl:+.4f}"})
                        time.sleep(max(1, int(remaining) + 10))
                        return journal

                # 2. SIRMARTINGALE TAKE-PROFIT (Realização Antecipada de Lucro)
                if cur_price >= 0.86 and cur_elapsed >= TP_POINT:
                    print(f"\n   [💰 SIRMARTINGALE TAKE-PROFIT]: Preço atingiu ${cur_price:.3f} >= $0.86 aos {int(cur_elapsed)}s. Realizando lucro!")
                    final_price = cur_price
                    final_pnl = round((final_price - entry_price) * shares, 4)
                    outcome_label = "WIN_TP"
                    journal = _register_trade(journal, window_ts, target_side, entry_price,
                                              final_price, shares, final_pnl, outcome_label, live_delta if cur_spot else delta)
                    save_state({**state, "status_signal": f"PAPER WIN TP @ ${final_price:.3f} | PnL ${final_pnl:+.4f}"})
                    time.sleep(max(1, int(remaining) + 10))
                    return journal

        # Janela encerrou — busca resolucao oficial
        if cur_elapsed >= WINDOW_SIZE:
            print(f"\n   [FIM DA JANELA]: Buscando resolucao oficial Polymarket...")
            resolution = get_polymarket_15m_resolution(window_ts, max_retries=20)

            if resolution:
                won = (resolution == target_side)
                if won:
                    pnl = round(shares - FIXED_STAKE, 4)   # ganho
                    outcome_label = "WIN"
                else:
                    pnl = -FIXED_STAKE                       # perda total da aposta
                    outcome_label = "LOSS"
                print(f"   [RESOLUCAO]: {resolution} | Apostou: {target_side} | {'GANHOU' if won else 'PERDEU'} | PnL: ${pnl:+.4f}")
                journal = _register_trade(journal, window_ts, target_side, entry_price,
                                          1.0 if won else 0.0, shares, pnl, outcome_label, delta)
                save_state({**state, "status_signal": f"{'WIN' if won else 'LOSS'} @ {resolution} | PnL ${pnl:+.4f}"})
            else:
                print("   [RESOLUCAO NAO ENCONTRADA]: Registrando como VOID.")
                journal = _register_trade(journal, window_ts, target_side, entry_price,
                                          entry_price, shares, 0.0, "VOID", delta)
                save_state({**state, "status_signal": "VOID — resolucao nao obtida"})
            return journal

        save_state(state)
        time.sleep(15)
        cur_elapsed = time.time() - window_ts

    return journal


def _register_trade(journal: Dict, window_ts: int, side: str, entry: float,
                    exit_price: float, shares: float, pnl: float,
                    outcome: str, delta: float) -> Dict:
    """Registra trade no journal e atualiza estatisticas"""
    journal["total_trades"] = journal.get("total_trades", 0) + 1
    if outcome in ("WIN", "WIN_TP"):
        journal["wins"] = journal.get("wins", 0) + 1
    elif outcome == "LOSS":
        journal["losses"] = journal.get("losses", 0) + 1

    total = journal["total_trades"]
    wins = journal.get("wins", 0)
    journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0
    journal["total_pnl"] = round(journal.get("total_pnl", 0.0) + pnl, 4)
    journal["current_balance"] = round(journal.get("current_balance", INITIAL_BALANCE) + pnl, 4)

    trade_record = {
        "timestamp": datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC"),
        "window_ts": window_ts,
        "side": side,
        "entry_price": round(entry, 4),
        "exit_price": round(exit_price, 4),
        "shares": round(shares, 4),
        "stake": FIXED_STAKE,
        "pnl": round(pnl, 4),
        "outcome": outcome,
        "delta_at_entry": round(delta, 2),
    }
    journal.setdefault("trades", []).append(trade_record)
    save_journal(journal)

    print(f"\n   {'='*60}")
    print(f"   TRADE #{total} REGISTRADO | {outcome} | PnL: ${pnl:+.4f}")
    print(f"   Win Rate: {journal['win_rate']:.1f}% ({wins}W / {journal.get('losses',0)}L) | Balance Paper: ${journal['current_balance']:.2f}")
    print(f"   {'='*60}")

    return journal


def _acquire_instance_lock(lock_path: str):
    """Garante que apenas uma instancia do Desk 3B esteja rodando por vez"""
    if sys.platform == "win32":
        import msvcrt
        f = open(lock_path, "w")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return f
        except OSError:
            print("\n[ERRO FATAL] Outra instancia do Desk 3B ja esta rodando (lock ativo). Abortando.")
            sys.exit(1)
    else:
        import fcntl
        f = open(lock_path, "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except IOError:
            print("\n[ERRO FATAL] Outra instancia do Desk 3B ja esta rodando (lock ativo). Abortando.")
            sys.exit(1)


def main():
    lock_path = os.path.join(BASE_DIR, "btc_15m_paper.lock")
    lock_file = _acquire_instance_lock(lock_path)
    print(f"-> Instance Lock adquirido com sucesso: {lock_path}")
    print("\n" + "="*80)
    print("  DESK 3B — POLYMARKET BTC 15M PAPER TRADER")
    print("  Modo: PAPER (zero risco real) | Janela: 15 minutos")
    print(f"  Entrada: {ENTRY_POINT}s | Deadband: ${DEADBAND_FLOOR:.0f} | Stake simulado: ${FIXED_STAKE:.2f}")
    print("  Objetivo: Validar edge por 2 semanas antes de qualquer LIVE")
    print("="*80)

    journal = load_journal()
    print(f"  Saldo paper actual: ${journal['current_balance']:.2f} | Trades: {journal['total_trades']} | WR: {journal['win_rate']:.1f}%")

    try:
        while True:
            try:
                journal = run_cycle(journal)
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n\n   [DESK 3B] Encerrado pelo utilizador.")
                break
            except Exception as e:
                print(f"\n   [ERRO CICLO DESK 3B]: {e}")
                time.sleep(10)
    finally:
        if lock_file:
            try:
                lock_file.close()
            except Exception:
                pass
            try:
                if os.path.exists(lock_path):
                    os.remove(lock_path)
            except Exception:
                pass
        print("-> Instance Lock do Desk 3B liberado com sucesso.")


if __name__ == "__main__":
    main()
