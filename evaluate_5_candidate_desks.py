# -*- coding: utf-8 -*-
"""
=============================================================================
AVALIAÇÃO QUANTITATIVA & LIVE SCAN: 5 CANDIDATOS ADICIONAIS
=============================================================================
Candidatos:
1. Polymarket: xrp-updown-5m
2. Polymarket: doge-updown-5m
3. Kalshi: KXETH15M
4. Kalshi: KXWTI15M
5. Kalshi: KXNDQ15M
=============================================================================
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
import pandas as pd
import numpy as np
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GAMMA_URL = "https://gamma-api.polymarket.com/events"
CLOB_URL = "https://clob.polymarket.com"
KALSHI_API = "https://external-api.kalshi.com/trade-api/v2"

# 1. VERIFICAÇÃO DE LIQUIDEZ E BOOK EM TEMPO REAL NA POLYMARKET
def inspect_polymarket_series(series_slug):
    print(f"\n--- Inspecionando Polymarket: {series_slug} ---")
    now_ts = int(time.time())
    window_ts = (now_ts // 300) * 300
    slug = f"{series_slug}-{window_ts}"
    
    url = f"{GAMMA_URL}?slug={slug}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            if data and len(data) > 0:
                event = data[0]
                markets = event.get("markets", [])
                if markets:
                    m = markets[0]
                    tokens = json.loads(m.get("clobTokenIds", "[]")) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", [])
                    vol = m.get("volume", 0)
                    liq = m.get("liquidity", 0)
                    print(f"  [+] Mercado encontrado: {m.get('question')}")
                    print(f"      Volume: ${float(vol):,.2f} | Liquidez: ${float(liq):,.2f}")
                    
                    if len(tokens) >= 2:
                        up_token = tokens[0]
                        book_url = f"{CLOB_URL}/book?token_id={up_token}"
                        b_req = urllib.request.Request(book_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(b_req, timeout=5) as b_resp:
                            b_data = json.loads(b_resp.read().decode())
                            bids = b_data.get("bids", [])
                            asks = b_data.get("asks", [])
                            best_bid = float(bids[-1]["price"]) if bids else 0.0
                            best_ask = float(asks[0]["price"]) if asks else 0.0
                            spread = round(best_ask - best_bid, 3) if best_ask > 0 and best_bid > 0 else 999
                            print(f"      Book UP Token: Best Bid ${best_bid:.2f} | Best Ask ${best_ask:.2f} | Spread ${spread:.2f}")
                            print(f"      Profundidade: {len(bids)} ordens de compra, {len(asks)} ordens de venda")
                            return {"active": True, "spread": spread, "volume": float(vol), "liquidity": float(liq), "best_bid": best_bid, "best_ask": best_ask}
            else:
                print(f"  [-] Mercado {slug} não listado na Gamma API no momento.")
    except Exception as e:
        print(f"  [!] Erro ao inspecionar {series_slug}: {e}")
    return {"active": False, "spread": 999, "volume": 0, "liquidity": 0}

# 2. VERIFICAÇÃO DE LIQUIDEZ E BOOK EM TEMPO REAL NA KALSHI
def inspect_kalshi_series(series_ticker):
    print(f"\n--- Inspecionando Kalshi: {series_ticker} ---")
    url = f"{KALSHI_API}/markets?series_ticker={series_ticker}&status=open&limit=5"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            markets = data.get("markets", [])
            if markets:
                m = markets[0]
                ticker = m.get("ticker")
                vol = m.get("volume", 0)
                oi = m.get("open_interest", 0)
                yes_bid = m.get("yes_bid", 0) / 100.0 if "yes_bid" in m else 0.0
                yes_ask = m.get("yes_ask", 0) / 100.0 if "yes_ask" in m else 0.0
                spread = round(yes_ask - yes_bid, 2) if yes_ask > 0 and yes_bid > 0 else 999
                print(f"  [+] Mercado encontrado: {ticker} ({m.get('title')})")
                print(f"      Volume: {vol} contratos | Open Interest: {oi}")
                print(f"      Cotação YES: Bid ${yes_bid:.2f} | Ask ${yes_ask:.2f} | Spread: ${spread:.2f}")
                return {"active": True, "ticker": ticker, "volume": vol, "oi": oi, "yes_bid": yes_bid, "yes_ask": yes_ask, "spread": spread}
            else:
                print(f"  [-] Nenhum mercado aberto atualmente para {series_ticker}")
    except Exception as e:
        print(f"  [!] Erro ao inspecionar Kalshi {series_ticker}: {e}")
    return {"active": False, "spread": 999, "volume": 0, "oi": 0}

# 3. BACKTESTING FORENSE RIGOROSO (SEM LOOK-AHEAD)
def fetch_1m_data(symbol, limit=1000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_vol', 'trades_count', 'taker_buy_vol',
                'taker_buy_quote_vol', 'ignore'
            ])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            return df
    except Exception as e:
        print(f"Erro ao baixar 1m de {symbol}: {e}")
        return None

def run_backtest_candidate(df_1m, asset_label, window_size=5, decision_minute=2, deadband_bps=0.0008, tp_price=0.88, sl_price=0.35, spread_friction=0.04):
    initial_bankroll = 100.0
    bankroll = initial_bankroll
    stake = 1.0 # $1 por aposta
    
    trades = []
    total_windows = len(df_1m) // window_size
    
    for w in range(1, total_windows):
        prev_start = (w - 1) * window_size
        prev_end = prev_start + window_size
        cur_start = w * window_size
        cur_end = cur_start + window_size
        
        prev_df = df_1m.iloc[prev_start:prev_end]
        cur_df = df_1m.iloc[cur_start:cur_end]
        
        if len(prev_df) < window_size or len(cur_df) < window_size:
            continue
            
        prev_open = prev_df.iloc[0]['open']
        prev_close = prev_df.iloc[-1]['close']
        prior_dir = 1 if prev_close >= prev_open else -1
        
        strike = cur_df.iloc[0]['open']
        decision_df = cur_df.iloc[:decision_minute + 1]
        spot_at_decision = decision_df.iloc[-1]['close']
        
        delta = spot_at_decision - strike
        delta_bps = abs(delta) / strike
        
        if delta_bps < deadband_bps:
            continue
            
        decision = "UP" if delta > 0 else "DOWN"
        
        # Filtro de continuação de tendência Jev
        if (decision == "UP" and prior_dir != 1) or (decision == "DOWN" and prior_dir != -1):
            continue
            
        # Preço de compra com atrito de spread
        entry_price = 0.48 + (spread_friction / 2.0)
        contracts = stake / entry_price
        
        outcome_won = None
        exit_payout = 0.0
        exit_reason = "EXPIRE"
        
        subsequent_df = cur_df.iloc[decision_minute + 1:]
        
        for _, row in subsequent_df.iterrows():
            m_high, m_low = row['high'], row['low']
            if decision == "UP":
                favorable_move = m_high - strike
                adverse_move = strike - m_low
            else:
                favorable_move = strike - m_low
                adverse_move = m_high - strike
                
            favorable_bps = favorable_move / strike
            adverse_bps = adverse_move / strike
            
            # Take Profit Dinâmico
            if favorable_bps >= (deadband_bps * 2.5):
                outcome_won = True
                exit_payout = contracts * tp_price
                exit_reason = "TAKE_PROFIT"
                break
                
            # Stop Loss Proativo
            if adverse_bps >= (deadband_bps * 1.5):
                outcome_won = False
                exit_payout = contracts * sl_price
                exit_reason = "STOP_LOSS"
                break
                
        if outcome_won is None:
            final_spot = cur_df.iloc[-1]['close']
            winner = "UP" if final_spot >= strike else "DOWN"
            outcome_won = (winner == decision)
            exit_payout = contracts * 1.00 if outcome_won else 0.0
            exit_reason = "EXPIRY_WIN" if outcome_won else "EXPIRY_LOSS"
            
        trade_pnl = exit_payout - stake
        bankroll += trade_pnl
        trades.append({
            "pnl": trade_pnl,
            "won": outcome_won,
            "reason": exit_reason,
            "entry_price": entry_price
        })
        
    total_trades = len(trades)
    if total_trades == 0:
        return {"trades": 0, "wr": 0, "pf": 0, "pnl": 0, "sharpe": 0, "ev": 0}
        
    wins = sum(1 for t in trades if t["pnl"] > 0)
    wr = (wins / total_trades) * 100
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = sum(abs(t["pnl"]) for t in trades if t["pnl"] < 0)
    pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
    ev = sum(t["pnl"] for t in trades) / total_trades
    pnls = [t["pnl"] for t in trades]
    std = np.std(pnls) if len(pnls) > 1 else 1.0
    sharpe = (np.mean(pnls) / std) * np.sqrt(total_trades) if std > 0 else 0.0
    
    return {
        "asset": asset_label,
        "trades": total_trades,
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "total_pnl": round(bankroll - initial_bankroll, 2),
        "ev": round(ev, 3),
        "sharpe": round(sharpe, 2)
    }

def main():
    print("=" * 80)
    print("   INVESTIGAÇÃO DOS 5 CANDIDATOS ADICIONAIS: QUANTITATIVO + ORDER BOOK")
    print("=" * 80)
    
    # Inspeciona books
    poly_xrp = inspect_polymarket_series("xrp-updown-5m")
    poly_doge = inspect_polymarket_series("doge-updown-5m")
    kalshi_eth = inspect_kalshi_series("KXETH15M")
    kalshi_wti = inspect_kalshi_series("KXWTI15M")
    kalshi_ndq = inspect_kalshi_series("KXNDQ15M")
    
    # Baixa dados 1m e roda backtest
    print("\n" + "=" * 80)
    print("   RODANDO BACKTESTS FORENSES HISTÓRICOS (1.000 VELAS)")
    print("=" * 80)
    
    # 1. XRP 5m
    df_xrp = fetch_1m_data("XRPUSDT", limit=1000)
    res_xrp = run_backtest_candidate(df_xrp, "XRP 5m (Polymarket)", window_size=5, decision_minute=2, deadband_bps=0.0010, tp_price=0.86, sl_price=0.35, spread_friction=0.06) if df_xrp is not None else {}
    
    # 2. DOGE 5m
    df_doge = fetch_1m_data("DOGEUSDT", limit=1000)
    res_doge = run_backtest_candidate(df_doge, "DOGE 5m (Polymarket)", window_size=5, decision_minute=2, deadband_bps=0.0012, tp_price=0.86, sl_price=0.35, spread_friction=0.08) if df_doge is not None else {}
    
    # 3. ETH 15m (Kalshi KXETH15M)
    df_eth = fetch_1m_data("ETHUSDT", limit=1000)
    res_eth15 = run_backtest_candidate(df_eth, "ETH 15m (Kalshi KXETH15M)", window_size=15, decision_minute=7, deadband_bps=0.0005, tp_price=0.88, sl_price=0.35, spread_friction=0.04) if df_eth is not None else {}

    results = {
        "poly_xrp": poly_xrp,
        "poly_doge": poly_doge,
        "kalshi_eth": kalshi_eth,
        "kalshi_wti": kalshi_wti,
        "kalshi_ndq": kalshi_ndq,
        "backtest_xrp": res_xrp,
        "backtest_doge": res_doge,
        "backtest_eth15": res_eth15
    }
    
    print("\n--- RESULTADOS DOS BACKTESTS ---")
    for r in [res_xrp, res_doge, res_eth15]:
        if r:
            print(f"Ativo: {r.get('asset')} | Trades: {r.get('trades')} | Win Rate: {r.get('wr')}% | Profit Factor: {r.get('pf')} | EV/Trade: ${r.get('ev')} | P&L ($1 stake): +${r.get('total_pnl')}")
            
    with open(os.path.join(BASE_DIR, "candidate_desks_scan_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
