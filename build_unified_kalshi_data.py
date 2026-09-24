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

print("=" * 90)
print("  BUILDING UNIFIED KALSHI NATURAL GAS & CLIMATE TIME SERIES (2010 - 2026)")
print("=" * 90)

# 1. Parse EIA Storage Excel
eia_path = os.path.join("natural_gas_dataset", "ngshistory.xls")
xl = pd.ExcelFile(eia_path)

# Sheet 1: html_report_history (Total Storage in Bcf)
df_tot = xl.parse("html_report_history", skiprows=5)
df_tot = df_tot.iloc[:, [0, 9]].dropna()
df_tot.columns = ['Date', 'total_storage_bcf']
df_tot['Date'] = pd.to_datetime(df_tot['Date'], errors='coerce')
df_tot['total_storage_bcf'] = pd.to_numeric(df_tot['total_storage_bcf'], errors='coerce')
df_tot = df_tot.dropna().sort_values('Date').reset_index(drop=True)

# Sheet 2: weekly_net_changes (Net Change in Bcf)
df_chg = xl.parse("weekly_net_changes", skiprows=5)
df_chg = df_chg.iloc[:, [0, 9]].dropna()
df_chg.columns = ['Date', 'net_change_bcf']
df_chg['Date'] = pd.to_datetime(df_chg['Date'], errors='coerce')
df_chg['net_change_bcf'] = pd.to_numeric(df_chg['net_change_bcf'], errors='coerce')
df_chg = df_chg.dropna().sort_values('Date').reset_index(drop=True)

# Merge EIA storage
eia_merged = pd.merge(df_tot, df_chg, on='Date', how='inner')
print(f"[*] EIA Weekly Records: {len(eia_merged)} weeks ({eia_merged['Date'].min().strftime('%Y-%m-%d')} to {eia_merged['Date'].max().strftime('%Y-%m-%d')})")

# 2. Merge with Henry Hub Daily Prices
hh_path = os.path.join("natural_gas_dataset", "daily.csv")
df_hh = pd.read_csv(hh_path)
df_hh['Date'] = pd.to_datetime(df_hh['Date'])
df_hh['Price'] = pd.to_numeric(df_hh['Price'], errors='coerce')
df_hh = df_hh.dropna().sort_values('Date').reset_index(drop=True)

# Align Henry Hub price to closest date before or on the EIA report date
eia_merged = pd.merge_asof(eia_merged.sort_values('Date'), df_hh.sort_values('Date'), on='Date', direction='backward')
eia_merged = eia_merged.rename(columns={'Price': 'henry_hub_spot_price'})

# Calculate 5-year rolling average for each calendar week
eia_merged['week_of_year'] = eia_merged['Date'].dt.isocalendar().week
eia_merged['month'] = eia_merged['Date'].dt.month

# 5-year average storage by week of year
weekly_5yr_avg = eia_merged.groupby('week_of_year')['total_storage_bcf'].transform(lambda x: x.rolling(5, min_periods=1).mean().shift(1))
eia_merged['storage_5yr_avg'] = weekly_5yr_avg
eia_merged['storage_surplus_deficit_bcf'] = eia_merged['total_storage_bcf'] - eia_merged['storage_5yr_avg']
eia_merged['storage_surplus_deficit_pct'] = (eia_merged['storage_surplus_deficit_bcf'] / eia_merged['storage_5yr_avg']) * 100

# Save clean combined dataset
clean_csv_path = os.path.join("natural_gas_dataset", "eia_henryhub_unified_weekly_2010_2026.csv")
eia_merged.to_csv(clean_csv_path, index=False)
print(f"[*] Unified dataset saved to {clean_csv_path}")
print(eia_merged.tail(5)[['Date', 'total_storage_bcf', 'net_change_bcf', 'henry_hub_spot_price', 'storage_surplus_deficit_bcf', 'storage_surplus_deficit_pct']])
