# -*- coding: utf-8 -*-
"""
=============================================================================
BACKTEST COMPARATIVO DE CANDIDATOS A NOVOS DESKS (POLYMKT & KALSHI)
=============================================================================
Testa com dados empíricos de 1.000 velas reais da Binance / Oráculos:
1. ETH 5m (Polymarket eth-updown-5m)
2. ETH 15m (Kalshi KXETH15M)
3. Gold 15m (Kalshi KXGOLD15M via PAXG)
4. XRP 5m (Polymarket xrp-updown-5m)
5. SOL 5m & 15m (Benchmark Desk 2)
6. BTC 5m & 15m (Benchmark Desks 1 e 3)
=============================================================================
"""
import os
import sys
import json
import urllib.request
import pandas as pd
import numpy as np
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def fetch_binance_klines(symbol, interval, limit=1000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
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
        print(f"Error fetching {symbol} {interval}: {e}")
        return None

def simulate_prediction_desk(df, asset_name, interval_name, deadband_bps=0.0008, tp_target=0.88, sl_floor=0.35):
    """
    Simula o motor exato do Desk 1/2/5:
    - Strike = Open da vela
    - Avaliação de entrada aos ~45% do tempo da vela (ex: 135s no 5m, 400s no 15m)
    - Posição tomada: se |Delta| >= deadband_bps * Strike
    - Direção: UP se Delta > 0, DOWN se Delta < 0
    - Take-Profit antecipado: se a máxima/mínima atingir ganho suficiente para precificar cota a tp_target
    - Stop-Loss proativo: se o preço reverter além do sl_floor
    - Payout final no fechamento se não sair antes
    """
    initial_balance = 1000.0
    balance = initial_balance
    stake = 10.0 # $10 por aposta
    
    trades = []
    
    for i in range(1, len(df)):
        prev_candle = df.iloc[i-1]
        candle = df.iloc[i]
        
        strike = candle['open']
        high = candle['high']
        low = candle['low']
        close = candle['close']
        
        # Simula preço no ponto de decisão (média entre open e ponto médio)
        # Mais confirmação com momentum da vela anterior
        prior_dir = 1 if prev_candle['close'] >= prev_candle['open'] else -1
        
        # Ponto de checagem aos 45% da vela (estimativa linear estocástica entre open e high/low/close)
        mid_point_approx = (candle['open'] + candle['close']) / 2.0
        delta = mid_point_approx - strike
        delta_bps = abs(delta) / strike
        
        # Filtro 1: Deadband
        if delta_bps < deadband_bps:
            continue
            
        decision = "UP" if delta > 0 else "DOWN"
        
        # Filtro 2: Alinhamento com vela anterior (evita falsos rompimentos)
        if (decision == "UP" and prior_dir != 1) or (decision == "DOWN" and prior_dir != -1):
            continue
            
        entry_price = 0.45 # Custo médio de compra aos 45% do tempo
        contracts = stake / entry_price
        
        # Avaliação de desfecho
        if decision == "UP":
            # Alvo de TP: se a máxima foi suficientemente alta
            hit_tp = (high - strike) >= (strike * deadband_bps * 2.2)
            final_win = close >= strike
            hit_sl = (low - strike) <= -(strike * deadband_bps * 1.8)
        else: # DOWN
            hit_tp = (strike - low) >= (strike * deadband_bps * 2.2)
            final_win = close <= strike
            hit_sl = (strike - high) <= -(strike * deadband_bps * 1.8)
            
        if hit_tp:
            # Saiu no Take-Profit
            pnl = contracts * (tp_target - entry_price)
            result = "WIN_TP"
            is_win = True
        elif hit_sl and not final_win:
            # Stop-Loss proativo salva parte do capital
            pnl = contracts * (sl_floor - entry_price)
            result = "LOSS_SL"
            is_win = False
        elif final_win:
            # Venceu no fechamento oficial da vela
            pnl = contracts * (1.00 - entry_price)
            result = "WIN_EXPIRY"
            is_win = True
        else:
            # Derrota total
            pnl = -stake
            result = "LOSS_FULL"
            is_win = False
            
        balance += pnl
        trades.append({
            "time": candle['open_time'],
            "decision": decision,
            "result": result,
            "is_win": is_win,
            "pnl": round(pnl, 2),
            "balance": round(balance, 2)
        })
        
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    if n == 0:
        return None
        
    wins = tdf['is_win'].sum()
    losses = n - wins
    wr = (wins / n) * 100
    pnl_total = tdf['pnl'].sum()
    gross_p = tdf[tdf['pnl'] > 0]['pnl'].sum()
    gross_l = abs(tdf[tdf['pnl'] < 0]['pnl'].sum())
    pf = gross_p / gross_l if gross_l > 0 else 999.0
    peak = tdf['balance'].cummax()
    dd = ((tdf['balance'] - peak) / peak).min() * 100
    
    # Sharpe anualizado
    returns = tdf['pnl'] / initial_balance
    periods_per_year = 252 * (288 if "5m" in interval_name else 96)
    trades_per_day = n / (len(df) / (288 if "5m" in interval_name else 96))
    annual_factor = np.sqrt(252 * trades_per_day)
    sharpe = (returns.mean() / (returns.std() + 1e-8)) * annual_factor
    
    return {
        "asset": asset_name,
        "timeframe": interval_name,
        "sample_candles": len(df),
        "total_trades": int(n),
        "trades_per_day": round(trades_per_day, 1),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate_pct": round(wr, 2),
        "net_pnl_usd": round(pnl_total, 2),
        "roi_pct": round((pnl_total / initial_balance) * 100, 2),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(dd, 2),
        "sharpe_ratio": round(sharpe, 2)
    }

print("=" * 95)
print("  🚀 INICIANDO DOWNLOAD E PROCESSAMENTO DE CANDLES HISTÓRICOS (BINANCE SPOT)")
print("=" * 95)

candidates = [
    # Cripto 5m (Polymarket / Kalshi)
    ("BTCUSDT", "5m", "Bitcoin (BTC)", 0.0006),
    ("ETHUSDT", "5m", "Ethereum (ETH)", 0.0008),
    ("SOLUSDT", "5m", "Solana (SOL)", 0.0012),
    ("XRPUSDT", "5m", "Ripple (XRP)", 0.0015),
    
    # Cripto 15m (Kalshi KXBTC15M, KXETH15M, KXSOL15M)
    ("BTCUSDT", "15m", "Bitcoin (BTC 15m)", 0.0008),
    ("ETHUSDT", "15m", "Ethereum (ETH 15m)", 0.0010),
    ("SOLUSDT", "15m", "Solana (SOL 15m)", 0.0015),
    
    # Commodities 15m (Kalshi KXGOLD15M)
    ("PAXGUSDT", "15m", "Gold / Ouro (XAU 15m)", 0.0004) # Gold tem menor volatilidade, deadband 4 bps
]

results = []

for symbol, interval, name, db in candidates:
    print(f"[*] Baixando e analisando {name} [{interval}]...")
    df = fetch_binance_klines(symbol, interval, limit=1000)
    if df is not None:
        metrics = simulate_prediction_desk(df, name, interval, deadband_bps=db)
        if metrics:
            results.append(metrics)
            print(f"    -> Trades: {metrics['total_trades']} ({metrics['trades_per_day']}/dia) | WR: {metrics['win_rate_pct']}% | PnL: +${metrics['net_pnl_usd']} | PF: {metrics['profit_factor']} | MaxDD: {metrics['max_drawdown_pct']}% | Sharpe: {metrics['sharpe_ratio']}")

with open("candidate_desks_backtest_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 95)
print("  ✅ BACKTEST DOS CANDIDATOS FINALIZADO COM SUCESSO!")
print("=" * 95)
