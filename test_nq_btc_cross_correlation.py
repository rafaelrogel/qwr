import pandas as pd
import numpy as np
from datetime import datetime

print("Loading NQ data...")
df_nq = pd.read_csv("NQ_5Years_8_11_2024.csv")
df_nq['dt'] = pd.to_datetime(df_nq['Time'], format='%m/%d/%Y %H:%M')
df_nq = df_nq.sort_values('dt').reset_index(drop=True)
df_nq['nq_ret'] = (df_nq['Close'] - df_nq['Open']) / df_nq['Open']

print("Loading BTC 5m data...")
# Read sample of BTC data overlapping NQ range (2019-08-11 to 2024-08-09)
df_btc = pd.read_csv("BTCUSDT_5minutes.csv")
df_btc['dt'] = pd.to_datetime(df_btc['timestamp'], unit='ms')
df_btc = df_btc.sort_values('dt').reset_index(drop=True)
df_btc['btc_ret'] = (df_btc['close'] - df_btc['open']) / df_btc['open']

# Filter BTC to overlapping range
min_dt = df_nq['dt'].min()
max_dt = df_nq['dt'].max()

print(f"NQ range: {min_dt} to {max_dt}")
print(f"BTC range: {df_btc['dt'].min()} to {df_btc['dt'].max()}")

# Let's test timezone offsets from -7 to +7 hours
results = []
# Take a slice of 3 months to quickly test cross-correlation
slice_start = pd.Timestamp("2021-01-01")
slice_end = pd.Timestamp("2021-06-01")

nq_slice = df_nq[(df_nq['dt'] >= slice_start) & (df_nq['dt'] <= slice_end)][['dt', 'nq_ret']].set_index('dt')
btc_slice = df_btc[(df_btc['dt'] >= slice_start - pd.Timedelta(days=1)) & (df_btc['dt'] <= slice_end + pd.Timedelta(days=1))][['dt', 'btc_ret']].set_index('dt')

for offset_hours in range(-7, 8):
    shifted_nq = nq_slice.copy()
    shifted_nq.index = shifted_nq.index + pd.Timedelta(hours=offset_hours)
    joined = shifted_nq.join(btc_slice, how='inner')
    corr = joined['nq_ret'].corr(joined['btc_ret'])
    results.append((offset_hours, corr, len(joined)))
    print(f"Offset {offset_hours:+d}h: corr = {corr:.4f} (N={len(joined)})")

best = max(results, key=lambda x: x[1])
print(f"\n>>> Best alignment offset: {best[0]:+d} hours (corr = {best[1]:.4f})")
