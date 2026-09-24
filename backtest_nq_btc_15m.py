import os
import sys
import json
import pandas as pd
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("=" * 80)
print("  EMPIRICAL QUANTITATIVE BACKTEST: NASDAQ-100 (NQ/QQQ) VS BTC ON 15-MINUTE TIMEFRAME")
print("=" * 80)

# 1. Load NQ 5m and resample to 15m
print("[*] Loading and resampling NQ to 15-minute bars...")
df_nq = pd.read_csv("NQ_5Years_8_11_2024.csv")
df_nq['dt'] = pd.to_datetime(df_nq['Time'], format='%m/%d/%Y %H:%M')
df_nq = df_nq.sort_values('dt').set_index('dt')
df_nq_15m = df_nq.resample('15min').agg({
    'Open': 'first',
    'High': 'max',
    'Low': 'min',
    'Close': 'last',
    'Volume': 'sum'
}).dropna().reset_index()

df_nq_15m['nq_ret'] = (df_nq_15m['Close'] - df_nq_15m['Open']) / df_nq_15m['Open']
df_nq_15m['nq_bps'] = df_nq_15m['nq_ret'] * 10000
df_nq_15m['nq_dir'] = np.where(df_nq_15m['nq_ret'] > 0.0001, 1, np.where(df_nq_15m['nq_ret'] < -0.0001, -1, 0))
print(f"    Resampled {len(df_nq_15m):,} 15-minute NQ bars.")

# 2. Load BTC 15m data
print("[*] Loading BTCUSDT_15minutes.csv...")
df_btc_15m = pd.read_csv("BTCUSDT_15minutes.csv")
if 'timestamp' in df_btc_15m.columns:
    df_btc_15m['dt'] = pd.to_datetime(df_btc_15m['timestamp'], unit='ms')
elif 'open_time' in df_btc_15m.columns:
    df_btc_15m['dt'] = pd.to_datetime(df_btc_15m['open_time'], unit='ms')
else:
    df_btc_15m['dt'] = pd.to_datetime(df_btc_15m.iloc[:, 0])

# Ensure column names are standard
cols = {c: c.lower() for c in df_btc_15m.columns}
df_btc_15m = df_btc_15m.rename(columns=cols)
df_btc_15m = df_btc_15m.sort_values('dt').reset_index(drop=True)
df_btc_15m['btc_ret'] = (df_btc_15m['close'] - df_btc_15m['open']) / df_btc_15m['open']
df_btc_15m['btc_bps'] = df_btc_15m['btc_ret'] * 10000

min_dt = max(df_nq_15m['dt'].min(), df_btc_15m['dt'].min())
max_dt = min(df_nq_15m['dt'].max(), df_btc_15m['dt'].max())
print(f"[*] Overlapping 15m period: {min_dt} to {max_dt}")

# Merge on exact 15m timestamp
merged_15m = pd.merge(
    df_btc_15m[(df_btc_15m['dt'] >= min_dt) & (df_btc_15m['dt'] <= max_dt)][['dt', 'open', 'close', 'btc_ret', 'btc_bps']],
    df_nq_15m[(df_nq_15m['dt'] >= min_dt) & (df_nq_15m['dt'] <= max_dt)][['dt', 'Open', 'Close', 'nq_ret', 'nq_bps', 'nq_dir']],
    on='dt', how='inner'
)
print(f"[*] Matched concurrent 15-minute bars: {len(merged_15m):,}")

# US Market Hours Feature (13:30 to 20:00 UTC)
merged_15m['hour_utc'] = merged_15m['dt'].dt.hour
merged_15m['minute_utc'] = merged_15m['dt'].dt.minute
merged_15m['is_us_session'] = (
    ((merged_15m['hour_utc'] == 13) & (merged_15m['minute_utc'] >= 30)) |
    ((merged_15m['hour_utc'] > 13) & (merged_15m['hour_utc'] < 20))
)

# 1. Contemporaneous Correlation on 15m
corr_15m_global = merged_15m['btc_ret'].corr(merged_15m['nq_ret'])
corr_15m_us = merged_15m[merged_15m['is_us_session']]['btc_ret'].corr(merged_15m[merged_15m['is_us_session']]['nq_ret'])
print(f"\n1. Correlação no Mesmo Candle de 15m:")
print(f"   - Global (24/5): r = {corr_15m_global:.4f}")
print(f"   - Horário de NY (US Session): r = {corr_15m_us:.4f}")

# 2. Lead-Lag: NQ(t) prevendo BTC(t+1) no 15m
merged_15m['next_btc_ret'] = merged_15m['btc_ret'].shift(-1)
merged_15m['next_btc_bps'] = merged_15m['btc_bps'].shift(-1)
corr_lead_lag_15m = merged_15m['nq_ret'].corr(merged_15m['next_btc_ret'])
corr_lead_lag_15m_us = merged_15m[merged_15m['is_us_session']]['nq_ret'].corr(merged_15m[merged_15m['is_us_session']]['next_btc_ret'])
print(f"\n2. Correlação Lead-Lag (NQ 15m no candle t -> BTC no próximo 15m candle t+1):")
print(f"   - Global: r = {corr_lead_lag_15m:.4f}")
print(f"   - Horário de NY: r = {corr_lead_lag_15m_us:.4f}")

# 3. Concordância Direcional em 15m
print(f"\n3. Probabilidade de BTC acompanhar NQ em 15m:")
for th_bps in [10, 20, 30, 50, 100]:
    nq_pump = merged_15m[merged_15m['nq_bps'] >= th_bps]
    nq_dump = merged_15m[merged_15m['nq_bps'] <= -th_bps]
    
    concord_pump = (nq_pump['btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    concord_dump = (nq_dump['btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_concord = (concord_pump + concord_dump) / 2
    
    lead_pump = (nq_pump['next_btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    lead_dump = (nq_dump['next_btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_lead = (lead_pump + lead_dump) / 2
    
    n_total = len(nq_pump) + len(nq_dump)
    print(f"   - NQ |bps| >= {th_bps:3d} (N={n_total:5,d}): Mesmo 15m: {avg_concord*100:.1f}% | Próximo 15m: {avg_lead*100:.1f}%")

# 4. Horário de NY em 15m
print(f"\n4. Sessão Americana (13:30 - 20:00 UTC) em 15m:")
merged_us_15m = merged_15m[merged_15m['is_us_session']]
for th_bps in [10, 20, 30, 50, 100]:
    nq_pump = merged_us_15m[merged_us_15m['nq_bps'] >= th_bps]
    nq_dump = merged_us_15m[merged_us_15m['nq_bps'] <= -th_bps]
    
    concord_pump = (nq_pump['btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    concord_dump = (nq_dump['btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_concord = (concord_pump + concord_dump) / 2
    
    lead_pump = (nq_pump['next_btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    lead_dump = (nq_dump['next_btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_lead = (lead_pump + lead_dump) / 2
    
    n_total = len(nq_pump) + len(nq_dump)
    print(f"   - US NQ |bps| >= {th_bps:3d} (N={n_total:5,d}): Mesmo 15m: {avg_concord*100:.1f}% | Próximo 15m: {avg_lead*100:.1f}%")

# 5. Teste de Veto no Robô de 15m (Kalshi BTC 15m)
# Deadband de 15m: |drift| >= 3.5 bps
print(f"\n5. Teste de Veto em Estratégia de 15m (|BTC Drift| >= 3.5 bps):")
th_btc = 3.5
sig_up = merged_15m['btc_bps'] >= th_btc
sig_down = merged_15m['btc_bps'] <= -th_btc
total_sigs = (sig_up | sig_down).sum()

# Next candle continuation
up_win = merged_15m['next_btc_bps'] > 0
down_win = merged_15m['next_btc_bps'] < 0
baseline_wins = (sig_up & up_win).sum() + (sig_down & down_win).sum()
baseline_wr_15m = baseline_wins / total_sigs if total_sigs > 0 else 0

# Com filtro NQ
allowed_up = sig_up & (merged_15m['nq_dir'] >= 0)
allowed_down = sig_down & (merged_15m['nq_dir'] <= 0)
total_filtered = (allowed_up | allowed_down).sum()
filtered_wins = (allowed_up & up_win).sum() + (allowed_down & down_win).sum()
filtered_wr_15m = filtered_wins / total_filtered if total_filtered > 0 else 0

conflict_up = sig_up & (merged_15m['nq_dir'] < 0)
conflict_down = sig_down & (merged_15m['nq_dir'] > 0)
total_conflicts = (conflict_up | conflict_down).sum()
conflict_wins = (conflict_up & up_win).sum() + (conflict_down & down_win).sum()
conflict_wr_15m = conflict_wins / total_conflicts if total_conflicts > 0 else 0

print(f"   - [Global 15m] Total Sinais: {total_sigs:,} | Baseline WR: {baseline_wr_15m*100:.2f}%")
print(f"   - [Global 15m] Com Filtro NQ: {total_filtered:,} | Filtered WR: {filtered_wr_15m*100:.2f}% (Delta: {(filtered_wr_15m - baseline_wr_15m)*100:+.2f}%)")
print(f"   - [Global 15m] Trades Vetados por Conflito: {total_conflicts:,} | WR dos Conflitos: {conflict_wr_15m*100:.2f}%")

# Save summary
res_15m = {
    "total_bars_15m": len(merged_15m),
    "us_session_bars_15m": int(merged_15m['is_us_session'].sum()),
    "corr_global_15m": round(corr_15m_global, 4),
    "corr_us_15m": round(corr_15m_us, 4),
    "lead_lag_global_15m": round(corr_lead_lag_15m, 4),
    "lead_lag_us_15m": round(corr_lead_lag_15m_us, 4),
    "baseline_wr_15m": round(baseline_wr_15m * 100, 2),
    "filtered_wr_15m": round(filtered_wr_15m * 100, 2),
    "conflict_wr_15m": round(conflict_wr_15m * 100, 2)
}

with open("nq_btc_15m_results.json", "w", encoding="utf-8") as f:
    json.dump(res_15m, f, indent=2)

print("\n[*] Resultados de 15m salvos em nq_btc_15m_results.json")
