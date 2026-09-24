import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

nq_file = "NQ_5Years_8_11_2024.csv"
btc_file = "BTCUSDT_5minutes.csv"

print(f"[*] Reading {nq_file}...")
df_nq = pd.read_csv(nq_file)
print(f"    Loaded {len(df_nq):,} rows of NQ.")
df_nq['dt'] = pd.to_datetime(df_nq['Time'], format='%m/%d/%Y %H:%M')
df_nq = df_nq.sort_values('dt').reset_index(drop=True)
df_nq['nq_ret'] = (df_nq['Close'] - df_nq['Open']) / df_nq['Open']
df_nq['nq_dir'] = np.where(df_nq['nq_ret'] > 0.0001, 1, np.where(df_nq['nq_ret'] < -0.0001, -1, 0))

print(f"[*] Reading {btc_file}...")
df_btc = pd.read_csv(btc_file, usecols=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df_btc['dt'] = pd.to_datetime(df_btc['timestamp'], unit='ms')
df_btc = df_btc.sort_values('dt').reset_index(drop=True)
df_btc['btc_ret'] = (df_btc['close'] - df_btc['open']) / df_btc['open']
df_btc['btc_bps'] = df_btc['btc_ret'] * 10000

min_dt = max(df_nq['dt'].min(), df_btc['dt'].min())
max_dt = min(df_nq['dt'].max(), df_btc['dt'].max())
print(f"[*] Overlapping period: {min_dt} to {max_dt}")

# Merge on exact timestamp
df_nq_clean = df_nq[(df_nq['dt'] >= min_dt) & (df_nq['dt'] <= max_dt)][['dt', 'Open', 'Close', 'nq_ret', 'nq_dir']].rename(
    columns={'Open': 'nq_open', 'Close': 'nq_close'}
)
df_btc_clean = df_btc[(df_btc['dt'] >= min_dt) & (df_btc['dt'] <= max_dt)][['dt', 'open', 'close', 'btc_ret', 'btc_bps']].rename(
    columns={'open': 'btc_open', 'close': 'btc_close'}
)

merged = pd.merge(df_btc_clean, df_nq_clean, on='dt', how='inner')
print(f"[*] Matched concurrent 5-minute candles: {len(merged):,} bars")

# Feature: US Market Hours (13:30 UTC to 20:00 UTC)
merged['hour_utc'] = merged['dt'].dt.hour
merged['minute_utc'] = merged['dt'].dt.minute
merged['is_us_session'] = (
    ((merged['hour_utc'] == 13) & (merged['minute_utc'] >= 30)) |
    ((merged['hour_utc'] > 13) & (merged['hour_utc'] < 20))
)

# Test different BTC signal thresholds (2.1 bps Deadband, 3.5 bps, 5.0 bps)
thresholds = [2.1, 3.5, 5.0, 7.5]

results_summary = {}

for th in thresholds:
    print(f"\n--- Analisando Threshold: |BTC Drift| >= {th} bps ---")
    
    # BTC Signal: UP if drift >= th, DOWN if drift <= -th
    sig_up = merged['btc_bps'] >= th
    sig_down = merged['btc_bps'] <= -th
    
    # 1. BASELINE (ALL HOURS, NO NQ FILTER)
    # Win condition: Does the candle close in the direction of the signal?
    # Note: In our sniper, we enter at 135s when drift >= th. In full candle, drift >= th already reflects momentum.
    # To test lead-lag or filter:
    # Does NQ alignment improve continuation?
    
    # Let's test Next Candle Continuation and Same Candle Alignment:
    merged['next_btc_bps'] = merged['btc_bps'].shift(-1)
    
    # Next candle continuation:
    up_next_win = merged['next_btc_bps'] > 0
    down_next_win = merged['next_btc_bps'] < 0
    
    total_up = sig_up.sum()
    total_down = sig_down.sum()
    total_signals = total_up + total_down
    
    # Baseline continuation win rate:
    wins_up = (sig_up & up_next_win).sum()
    wins_down = (sig_down & down_next_win).sum()
    baseline_wr = (wins_up + wins_down) / total_signals if total_signals > 0 else 0
    
    # FILTERED BY NQ:
    # UP is allowed only if NQ >= 0 (NQ is not negative)
    # DOWN is allowed only if NQ <= 0 (NQ is not positive)
    allowed_up = sig_up & (merged['nq_dir'] >= 0)
    allowed_down = sig_down & (merged['nq_dir'] <= 0)
    total_filtered = allowed_up.sum() + allowed_down.sum()
    
    wins_up_filtered = (allowed_up & up_next_win).sum()
    wins_down_filtered = (allowed_down & down_next_win).sum()
    filtered_wr = (wins_up_filtered + wins_down_filtered) / total_filtered if total_filtered > 0 else 0
    
    # CONFLICT TRADES (WHERE NQ CONTRADICTED BTC):
    conflict_up = sig_up & (merged['nq_dir'] < 0)
    conflict_down = sig_down & (merged['nq_dir'] > 0)
    total_conflicts = conflict_up.sum() + conflict_down.sum()
    conflict_wins = (conflict_up & up_next_win).sum() + (conflict_down & down_next_win).sum()
    conflict_wr = conflict_wins / total_conflicts if total_conflicts > 0 else 0
    
    # US SESSION SPECIFIC:
    us_signals = (sig_up | sig_down) & merged['is_us_session']
    us_wins = ((sig_up & up_next_win) | (sig_down & down_next_win)) & merged['is_us_session']
    us_baseline_wr = us_wins.sum() / us_signals.sum() if us_signals.sum() > 0 else 0
    
    us_allowed = (allowed_up | allowed_down) & merged['is_us_session']
    us_allowed_wins = ((allowed_up & up_next_win) | (allowed_down & down_next_win)) & merged['is_us_session']
    us_filtered_wr = us_allowed_wins.sum() / us_allowed.sum() if us_allowed.sum() > 0 else 0
    
    us_conflicts = (conflict_up | conflict_down) & merged['is_us_session']
    us_conflict_wins = ((conflict_up & up_next_win) | (conflict_down & down_next_win)) & merged['is_us_session']
    us_conflict_wr = us_conflict_wins.sum() / us_conflicts.sum() if us_conflicts.sum() > 0 else 0
    
    print(f"  [Global] Total Sinais: {total_signals:,} | Baseline WR: {baseline_wr*100:.2f}%")
    print(f"  [Global] Com Filtro NQ: {total_filtered:,} trades | Filtered WR: {filtered_wr*100:.2f}% (Δ: {(filtered_wr - baseline_wr)*100:+.2f}%)")
    print(f"  [Global] Sinais Vetados por Conflito NQ: {total_conflicts:,} trades | WR dos Conflitos: {conflict_wr*100:.2f}%")
    print(f"  [US Hours] Sinais: {us_signals.sum():,} | Baseline WR: {us_baseline_wr*100:.2f}%")
    print(f"  [US Hours] Com Filtro NQ: {us_allowed.sum():,} | Filtered WR: {us_filtered_wr*100:.2f}% (Δ: {(us_filtered_wr - us_baseline_wr)*100:+.2f}%)")
    print(f"  [US Hours] Conflitos Vetados: {us_conflicts.sum():,} | WR dos Conflitos: {us_conflict_wr*100:.2f}%")
    
    results_summary[f"{th}_bps"] = {
        "total_signals": int(total_signals),
        "baseline_wr": round(baseline_wr * 100, 2),
        "filtered_signals": int(total_filtered),
        "filtered_wr": round(filtered_wr * 100, 2),
        "wr_delta_global": round((filtered_wr - baseline_wr) * 100, 2),
        "vetoed_conflicts": int(total_conflicts),
        "conflict_wr": round(conflict_wr * 100, 2),
        "us_baseline_wr": round(us_baseline_wr * 100, 2),
        "us_filtered_wr": round(us_filtered_wr * 100, 2),
        "us_wr_delta": round((us_filtered_wr - us_baseline_wr) * 100, 2),
        "us_conflict_wr": round(us_conflict_wr * 100, 2)
    }

# Save results to json
with open("nq_btc_backtest_results.json", "w", encoding="utf-8") as f:
    json.dump(results_summary, f, indent=2)

print("\n[*] Resultados salvos em nq_btc_backtest_results.json")
