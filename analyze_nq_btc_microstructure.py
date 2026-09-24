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

nq_file = "NQ_5Years_8_11_2024.csv"
btc_file = "BTCUSDT_5minutes.csv"

df_nq = pd.read_csv(nq_file)
df_nq['dt'] = pd.to_datetime(df_nq['Time'], format='%m/%d/%Y %H:%M')
df_nq = df_nq.sort_values('dt').reset_index(drop=True)
df_nq['nq_ret'] = (df_nq['Close'] - df_nq['Open']) / df_nq['Open']
df_nq['nq_bps'] = df_nq['nq_ret'] * 10000

df_btc = pd.read_csv(btc_file, usecols=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df_btc['dt'] = pd.to_datetime(df_btc['timestamp'], unit='ms')
df_btc = df_btc.sort_values('dt').reset_index(drop=True)
df_btc['btc_ret'] = (df_btc['close'] - df_btc['open']) / df_btc['open']
df_btc['btc_bps'] = df_btc['btc_ret'] * 10000

min_dt = max(df_nq['dt'].min(), df_btc['dt'].min())
max_dt = min(df_nq['dt'].max(), df_btc['dt'].max())

df_nq_clean = df_nq[(df_nq['dt'] >= min_dt) & (df_nq['dt'] <= max_dt)][['dt', 'nq_ret', 'nq_bps']]
df_btc_clean = df_btc[(df_btc['dt'] >= min_dt) & (df_btc['dt'] <= max_dt)][['dt', 'btc_ret', 'btc_bps']]

merged = pd.merge(df_btc_clean, df_nq_clean, on='dt', how='inner')
merged['hour_utc'] = merged['dt'].dt.hour
merged['minute_utc'] = merged['dt'].dt.minute
merged['is_us_session'] = (
    ((merged['hour_utc'] == 13) & (merged['minute_utc'] >= 30)) |
    ((merged['hour_utc'] > 13) & (merged['hour_utc'] < 20))
)

print(f"Total concurrent bars: {len(merged):,}")
print(f"US Session bars (13:30 - 20:00 UTC): {merged['is_us_session'].sum():,}")

# 1. Contemporaneous Correlation
corr_global = merged['btc_ret'].corr(merged['nq_ret'])
corr_us = merged[merged['is_us_session']]['btc_ret'].corr(merged[merged['is_us_session']]['nq_ret'])
print(f"\n1. Correlação Contemporânea (mesmo candle de 5m):")
print(f"   - Global (24/5): {corr_global:.4f}")
print(f"   - Horário de NY (US Session): {corr_us:.4f}")

# 2. Lead-Lag: NQ(t) prevendo BTC(t+1)
merged['next_btc_ret'] = merged['btc_ret'].shift(-1)
merged['next_btc_bps'] = merged['btc_bps'].shift(-1)
corr_lead_lag = merged['nq_ret'].corr(merged['next_btc_ret'])
corr_lead_lag_us = merged[merged['is_us_session']]['nq_ret'].corr(merged[merged['is_us_session']]['next_btc_ret'])
print(f"\n2. Correlação Lead-Lag (NQ no candle t -> BTC no candle t+1):")
print(f"   - Global: {corr_lead_lag:.4f}")
print(f"   - Horário de NY: {corr_lead_lag_us:.4f}")

# 3. Análise de Continuidade quando NQ tem Movimento Forte (> 10 bps, > 25 bps, > 50 bps)
print(f"\n3. Probabilidade de BTC acompanhar NQ quando NQ tem movimento expressivo:")
for threshold_bps in [5, 10, 20, 30, 50]:
    nq_pump = merged[merged['nq_bps'] >= threshold_bps]
    nq_dump = merged[merged['nq_bps'] <= -threshold_bps]
    
    btc_followed_pump = (nq_pump['btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    btc_followed_dump = (nq_dump['btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_concordance = (btc_followed_pump + btc_followed_dump) / 2
    
    # Next bar lead-lag:
    btc_next_pump = (nq_pump['next_btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    btc_next_dump = (nq_dump['next_btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_next_concordance = (btc_next_pump + btc_next_dump) / 2
    
    print(f"   - NQ |bps| >= {threshold_bps:2d} (N={len(nq_pump)+len(nq_dump):6,d}): Mesmo candle: {avg_concordance*100:.1f}% | Próximo candle (Lead): {avg_next_concordance*100:.1f}%")

# 4. Análise Específica da Sessão Americana (US Hours) em Movimentos Fortes:
print(f"\n4. Sessão Americana (13:30 - 20:00 UTC) em Movimentos Fortes do NQ:")
merged_us = merged[merged['is_us_session']]
for threshold_bps in [5, 10, 20, 30, 50]:
    nq_pump = merged_us[merged_us['nq_bps'] >= threshold_bps]
    nq_dump = merged_us[merged_us['nq_bps'] <= -threshold_bps]
    
    btc_followed_pump = (nq_pump['btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    btc_followed_dump = (nq_dump['btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_concordance = (btc_followed_pump + btc_followed_dump) / 2
    
    btc_next_pump = (nq_pump['next_btc_bps'] > 0).mean() if len(nq_pump) > 0 else 0
    btc_next_dump = (nq_dump['next_btc_bps'] < 0).mean() if len(nq_dump) > 0 else 0
    avg_next_concordance = (btc_next_pump + btc_next_dump) / 2
    
    print(f"   - US NQ |bps| >= {threshold_bps:2d} (N={len(nq_pump)+len(nq_dump):5,d}): Mesmo candle: {avg_concordance*100:.1f}% | Próximo candle (Lead): {avg_next_concordance*100:.1f}%")

# 5. O EFEITO VETO: Se BTC dá sinal, o que acontece se NQ discorda vs se NQ concorda?
print(f"\n5. Teste de Veto no Mesmo Candle (Se BTC move > 2.1 bps):")
for btc_th in [2.1, 5.0, 10.0]:
    btc_signals = merged[abs(merged['btc_bps']) >= btc_th]
    # Concordante: mesmo sinal
    concordant = btc_signals[(btc_signals['btc_bps'] * btc_signals['nq_bps']) > 0]
    # Discordante: sinais opostos
    discordant = btc_signals[(btc_signals['btc_bps'] * btc_signals['nq_bps']) < 0]
    
    pct_concordant = len(concordant) / len(btc_signals) if len(btc_signals) > 0 else 0
    pct_discordant = len(discordant) / len(btc_signals) if len(btc_signals) > 0 else 0
    
    print(f"   - BTC |bps| >= {btc_th:4.1f}: Concordância NQ: {pct_concordant*100:.1f}% ({len(concordant):,} bars) | Discordância NQ: {pct_discordant*100:.1f}% ({len(discordant):,} bars)")

# Compilar resumo dos dados para enviar ao JEV
summary_data = {
    "total_bars_5y": len(merged),
    "us_session_bars": int(merged['is_us_session'].sum()),
    "contemporaneous_correlation_global": round(corr_global, 4),
    "contemporaneous_correlation_us_hours": round(corr_us, 4),
    "lead_lag_correlation_nq_to_btc_next_global": round(corr_lead_lag, 4),
    "lead_lag_correlation_nq_to_btc_next_us_hours": round(corr_lead_lag_us, 4),
    "concordance_by_nq_magnitude_us_hours": {
        ">=5_bps": round(((merged_us[merged_us['nq_bps']>=5]['btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-5]['btc_bps']<0).mean())/2*100, 2),
        ">=10_bps": round(((merged_us[merged_us['nq_bps']>=10]['btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-10]['btc_bps']<0).mean())/2*100, 2),
        ">=20_bps": round(((merged_us[merged_us['nq_bps']>=20]['btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-20]['btc_bps']<0).mean())/2*100, 2),
        ">=30_bps": round(((merged_us[merged_us['nq_bps']>=30]['btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-30]['btc_bps']<0).mean())/2*100, 2),
        ">=50_bps": round(((merged_us[merged_us['nq_bps']>=50]['btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-50]['btc_bps']<0).mean())/2*100, 2)
    },
    "lead_lag_concordance_us_hours": {
        ">=5_bps": round(((merged_us[merged_us['nq_bps']>=5]['next_btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-5]['next_btc_bps']<0).mean())/2*100, 2),
        ">=10_bps": round(((merged_us[merged_us['nq_bps']>=10]['next_btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-10]['next_btc_bps']<0).mean())/2*100, 2),
        ">=20_bps": round(((merged_us[merged_us['nq_bps']>=20]['next_btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-20]['next_btc_bps']<0).mean())/2*100, 2),
        ">=30_bps": round(((merged_us[merged_us['nq_bps']>=30]['next_btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-30]['next_btc_bps']<0).mean())/2*100, 2),
        ">=50_bps": round(((merged_us[merged_us['nq_bps']>=50]['next_btc_bps']>0).mean() + (merged_us[merged_us['nq_bps']<=-50]['next_btc_bps']<0).mean())/2*100, 2)
    }
}

with open("nq_btc_correlation_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary_data, f, indent=2)

print("\n[*] Análise estatística concluída e salva em nq_btc_correlation_summary.json")
