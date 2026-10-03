"""
Example Backtest utilizing Dukascopy Historical Swiss Data feeds
with institutional execution_math (Kelly Sizing, Net Edge, and Fair Value).
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from dukascopy_manager import DukascopyManager
from execution_math import (
    bayesian_fair_value,
    calculate_executable_edge,
    compute_fractional_kelly_stake
)


def run_sample_backtest(symbol: str = "BTCUSD", timeframe: str = "m15"):
    mgr = DukascopyManager()
    print(f"\n--- Running Dukascopy Quant Backtest on {symbol} ({timeframe}) ---")

    try:
        df = mgr.load_candles(symbol, timeframe)
    except Exception as e:
        print(f"Dataset not ready yet: {e}")
        return

    print(f"Loaded {len(df):,} candles from {df.index[0]} to {df.index[-1]}")

    # Compute returns and volatility
    df["return"] = df["close"].pct_change()
    df["volatility_20"] = df["return"].rolling(20).std()
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()

    # Simple Mean Reversion / Momentum signal for demonstration
    df["signal"] = 0
    df.loc[df["close"] > df["sma_20"] + 1.5 * df["volatility_20"] * df["close"], "signal"] = -1 # Overbought
    df.loc[df["close"] < df["sma_20"] - 1.5 * df["volatility_20"] * df["close"], "signal"] = 1  # Oversold

    trades = []
    capital = 1000.0

    for i in range(50, len(df)):
        sig = df["signal"].iloc[i]
        close_p = df["close"].iloc[i]
        vol = df["volatility_20"].iloc[i]

        if sig != 0 and vol > 0:
            prob_win = 0.55 if sig == 1 else 0.53
            raw_edge, net_edge, is_tradable = calculate_executable_edge(
                fair_value=prob_win,
                expected_fill_price=0.50,
                trading_fee=0.0
            )
            stake, full_kelly, status = compute_fractional_kelly_stake(
                bankroll=capital,
                win_probability=prob_win,
                entry_price=0.50,
                kelly_fraction=0.25,
                min_stake=5.0,
                max_stake=30.0
            )

            # Look forward 1 candle
            next_ret = df["return"].iloc[i + 1] if i + 1 < len(df) else 0
            pnl = stake * (next_ret if sig == 1 else -next_ret) * 10
            capital += pnl

            trades.append({
                "datetime": df.index[i],
                "signal": "BUY" if sig == 1 else "SELL",
                "price": close_p,
                "stake": round(stake, 2),
                "edge": round(net_edge, 4),
                "pnl": round(pnl, 2),
                "capital": round(capital, 2)
            })

    print(f"Total Trades Evaluated: {len(trades)}")
    if trades:
        win_trades = [t for t in trades if t["pnl"] > 0]
        print(f"Win Rate: {len(win_trades) / len(trades) * 100:.1f}%")
        print(f"Final Capital: ${capital:,.2f} (from $1,000.00)")


if __name__ == "__main__":
    run_sample_backtest("BTCUSD", "m15")
