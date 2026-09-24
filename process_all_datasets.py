"""
Compute empirical statistical matrices across all available local datasets:
1. Gold Spot (XAU/USD 5m) - 2.4 million candles
2. S&P 500 E-mini (ES 5y) - 353k bars
3. Nasdaq 100 (NQ 5y) - 329k bars
4. EUR/USD (1m) - 189k bars
5. PolyResearch Multi-Asset Polymarket Orderbooks (BTC, ETH, SOL, XRP)
"""

import os
import sys
import json
import glob
import pandas as pd
import numpy as np

base_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"

results = {}

# 1. GOLD SPOT 5M
print("[1/5] Processing Gold Spot (XAU/USD)...")
gold_path = os.path.join(base_dir, "Gold-Spot-XAUUSD-5-Minute-OHLC-Candles.csv")
if os.path.exists(gold_path):
    gdf = pd.read_csv(gold_path)
    gdf = gdf.tail(500000).copy() # Last 500,000 5m candles
    gdf["open"] = gdf["open"].astype(float)
    gdf["close"] = gdf["close"].astype(float)
    gdf["high"] = gdf["high"].astype(float)
    gdf["low"] = gdf["low"].astype(float)
    
    gdf["ret"] = (gdf["close"] - gdf["open"]) / gdf["open"]
    gdf["prev_ret"] = gdf["ret"].shift(1)
    gdf["bps"] = gdf["ret"].abs() * 10000
    
    # Drift from open to midpoint vs final close
    mid_proxy = (gdf["high"] + gdf["low"]) / 2.0
    drift = mid_proxy - gdf["open"]
    final = gdf["close"] - gdf["open"]
    
    # Filter by bps
    gold_bps_stats = {}
    for min_bps in [0.5, 1.0, 2.0, 3.5, 5.0]:
        mask = (drift.abs() / gdf["open"] * 10000) >= min_bps
        sub_drift = drift[mask]
        sub_final = final[mask]
        wins = (sub_drift * sub_final > 0).sum()
        total = len(sub_drift)
        wr = (wins / total * 100) if total > 0 else 0
        gold_bps_stats[f">= {min_bps} bps"] = f"{wins}/{total} ({wr:.1f}%)"
    
    # Candle-to-candle continuation
    valid = (gdf["ret"] != 0) & (gdf["prev_ret"] != 0)
    cont_rate = ((gdf.loc[valid, "ret"] * gdf.loc[valid, "prev_ret"]) > 0).mean() * 100
    
    results["gold_5m"] = {
        "sample_size": len(gdf),
        "period": f"{gdf['date'].iloc[0]} to {gdf['date'].iloc[-1]}",
        "avg_bps_per_5m_bar": float(gdf["bps"].mean()),
        "candle_continuation_rate": f"{cont_rate:.1f}% (Mean-reversion: {100-cont_rate:.1f}%)",
        "midpoint_drift_win_rate_by_bps": gold_bps_stats
    }

# 2. ES & NQ FUTURES (5 Years)
print("[2/5] Processing Equity Index Futures (ES & NQ)...")
for sym, fname in [("ES_SP500_Futures", "ES_5Years_8_11_2024.csv"), ("NQ_Nasdaq100_Futures", "NQ_5Years_8_11_2024.csv")]:
    p = os.path.join(base_dir, fname)
    if os.path.exists(p):
        df = pd.read_csv(p)
        df["ret"] = (df["Close"] - df["Open"]) / df["Open"]
        df["prev_ret"] = df["ret"].shift(1)
        df["bps"] = df["ret"].abs() * 10000
        
        mid_proxy = (df["High"] + df["Low"]) / 2.0
        drift = mid_proxy - df["Open"]
        final = df["Close"] - df["Open"]
        
        bps_stats = {}
        for min_bps in [1.0, 2.0, 3.5, 5.0, 10.0]:
            mask = (drift.abs() / df["Open"] * 10000) >= min_bps
            sub_drift = drift[mask]
            sub_final = final[mask]
            wins = (sub_drift * sub_final > 0).sum()
            total = len(sub_drift)
            wr = (wins / total * 100) if total > 0 else 0
            bps_stats[f">= {min_bps} bps"] = f"{wins}/{total} ({wr:.1f}%)"
            
        valid = (df["ret"] != 0) & (df["prev_ret"] != 0)
        cont_rate = ((df.loc[valid, "ret"] * df.loc[valid, "prev_ret"]) > 0).mean() * 100
        
        results[sym] = {
            "sample_size": len(df),
            "avg_bps_per_bar": float(df["bps"].mean()),
            "candle_continuation_rate": f"{cont_rate:.1f}% (Mean-reversion: {100-cont_rate:.1f}%)",
            "midpoint_drift_win_rate_by_bps": bps_stats
        }

# 3. EUR/USD (1m)
print("[3/5] Processing EUR/USD Forex...")
eur_path = os.path.join(base_dir, "EURUSD_1m.csv")
if os.path.exists(eur_path):
    edf = pd.read_csv(eur_path)
    edf["ret"] = (edf["close"] - edf["open"]) / edf["open"]
    edf["prev_ret"] = edf["ret"].shift(1)
    edf["bps"] = edf["ret"].abs() * 10000
    
    valid = (edf["ret"] != 0) & (edf["prev_ret"] != 0)
    cont_rate = ((edf.loc[valid, "ret"] * edf.loc[valid, "prev_ret"]) > 0).mean() * 100
    
    results["eurusd_1m"] = {
        "sample_size": len(edf),
        "avg_bps_per_bar": float(edf["bps"].mean()),
        "candle_continuation_rate": f"{cont_rate:.1f}% (Mean-reversion: {100-cont_rate:.1f}%)"
    }

# 4. POLYRESEARCH MULTI-TOKEN POLYMARKET ORDER BOOKS (BTC, ETH, SOL, XRP)
print("[4/5] Processing PolyResearch Polymarket Order Books (BTC, ETH, SOL, XRP)...")
prr_dir = os.path.join(base_dir, "PolyResearch_Crypto_Sample", "PolyResearchRobotics_Crypto_Dataset_Sample")
token_metrics = {}

for token in ["btc", "eth", "sol", "xrp"]:
    t_metrics = {}
    for tf in ["5m", "15m"]:
        folder = os.path.join(prr_dir, f"{token}_{tf}")
        files = glob.glob(os.path.join(folder, "*.parquet"))
        if not files: continue
        
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_parquet(f))
            except Exception:
                pass
        if not dfs: continue
        full_df = pd.concat(dfs, ignore_index=True)
        
        avg_spread = float(full_df["spread"].mean())
        avg_top_bid = float(full_df["top_bid_size"].mean())
        avg_top_ask = float(full_df["top_ask_size"].mean())
        avg_total_depth = float((full_df["sum_bid_size"] + full_df["sum_ask_size"]).mean())
        
        # Orderbook Imbalance vs Microprice divergence
        full_df["micro_mid_diff"] = full_df["microprice"] - full_df["mid_price"]
        avg_micro_drift = float(full_df["micro_mid_diff"].abs().mean())
        
        t_metrics[tf] = {
            "samples_ticks": len(full_df),
            "avg_spread": f"${avg_spread:.4f} ({avg_spread*100:.1f} cents)",
            "avg_top_depth_shares": f"Bid: {avg_top_bid:.1f} | Ask: {avg_top_ask:.1f}",
            "avg_total_book_depth_shares": f"{avg_total_depth:.0f}",
            "avg_microprice_disparity": f"${avg_micro_drift:.4f}"
        }
    token_metrics[token.upper()] = t_metrics

results["polymarket_multi_asset_microstructure"] = token_metrics

# 5. HEDGE FUND 13F HOLDINGS DATASET (2018-2026)
print("[5/5] Processing Hedge Fund 13F dataset...")
hf_path = os.path.join(base_dir, "stockfries_hedgefund_13fdata_byStockPosition_2018to2026.csv")
if os.path.exists(hf_path):
    hf_df = pd.read_csv(hf_path, nrows=50000)
    top_issuers = hf_df["nameOfIssuer"].value_counts().head(5).to_dict()
    results["hedge_fund_13f_sample"] = {
        "analyzed_filings": len(hf_df),
        "top_institutional_holdings_count": top_issuers
    }

out_file = os.path.join(base_dir, "all_datasets_matrix_summary.json")
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"\n[OK] Summary saved to {out_file}")
