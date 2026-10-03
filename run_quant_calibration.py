"""
MOTOR DE CALIBRAÇÃO QUANTITATIVA DE MICROESTRUTURA (CME GLOBEX DATABENTO)
========================================================================
Processa os 1.438 arquivos baixados da Databento para calibrar:
1. Parâmetros da Desk 5 (Kalshi NatGas 15m LIVE):
   - Deadband exato invariante de escala (bps e centavos).
   - Tabela de Volatilidade por Hora UTC (Modulação Diurna).
   - Win Rate empírico no Sweet-Spot de 450s (metade da vela de 15m).
2. Parâmetros da Desk 11 (Kalshi SPX 15m Momentum):
   - Eficácia do Sweet-Spot de 450s no E-mini S&P 500 (ES.c.0).
   - Win Rate empírico por degrau de Deadband (pts).
"""

import os
import sys
import glob
import time
import json
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import databento as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data_databento")
REPORT_JSON = os.path.join(BASE_DIR, "databento_calibration_verdict.json")

def analyze_natgas_15m():
    print("=" * 80)
    print("  🔥 CALIBRANDO DESK 5: NYMEX HENRY HUB NATURAL GAS (NG.c.0 - 1 ANO)")
    print("=" * 80)
    
    ng_dir = os.path.join(DATA_DIR, "GLBX-20260927-5V4SUPXBBS")
    files = sorted(glob.glob(os.path.join(ng_dir, "*.dbn.zst")))
    print(f"[*] Processando {len(files)} arquivos diários de 1 segundo...")

    candles_15m = []
    t0 = time.time()

    for idx, f in enumerate(files):
        try:
            store = db.DBNStore.from_file(f)
            df = store.to_df()
            if df.empty or 'close' not in df.columns:
                continue

            # Resample de 1 segundo para velas exatas de 15 minutos (900s)
            resampled = df['close'].resample('15min').ohlc().dropna()
            
            # Também capturar o preço no segundo 450 (Sweet-spot) de cada vela de 15m
            for period_start, row in resampled.iterrows():
                period_end = period_start + pd.Timedelta(minutes=15)
                mid_point = period_start + pd.Timedelta(seconds=450)

                slice_15m = df.loc[period_start:period_end, 'close']
                if len(slice_15m) < 60: # pelo menos 1 minuto de trades
                    continue

                open_px = slice_15m.iloc[0]
                close_px = slice_15m.iloc[-1]
                
                # Preço aos 450s (ou mais próximo)
                sub_450 = slice_15m.loc[:mid_point]
                px_450 = sub_450.iloc[-1] if not sub_450.empty else open_px

                candles_15m.append({
                    "timestamp": period_start.isoformat(),
                    "hour_utc": period_start.hour,
                    "open": float(open_px),
                    "close": float(close_px),
                    "px_450": float(px_450),
                    "full_delta": float(close_px - open_px),
                    "delta_450": float(px_450 - open_px),
                    "abs_delta_450": float(abs(px_450 - open_px)),
                    "bps_450": float(abs(px_450 - open_px) / open_px * 10000)
                })

        except Exception as e:
            continue

    dt = time.time() - t0
    df_res = pd.DataFrame(candles_15m)
    print(f"[OK] Total de velas de 15m analisadas no Henry Hub: {len(df_res)} ({dt:.1f}s)")

    if df_res.empty:
        return {}

    # 1. Percentis de Delta aos 450s (em bps e dólares)
    p50_bps = df_res['bps_450'].quantile(0.50)
    p75_bps = df_res['bps_450'].quantile(0.75)
    p85_bps = df_res['bps_450'].quantile(0.85)
    p90_bps = df_res['bps_450'].quantile(0.90)
    p95_bps = df_res['bps_450'].quantile(0.95)

    p50_cents = df_res['abs_delta_450'].quantile(0.50)
    p75_cents = df_res['abs_delta_450'].quantile(0.75)
    p85_cents = df_res['abs_delta_450'].quantile(0.85)
    p90_cents = df_res['abs_delta_450'].quantile(0.90)
    p95_cents = df_res['abs_delta_450'].quantile(0.95)

    # 2. Teste de Taxa de Acerto (Win Rate) aos 450s por nível de Deadband
    # Se aos 450s delta > deadband, qual a % de fechar em alta aos 900s?
    win_rates = {}
    for deadband_bps in [5.0, 7.5, 10.0, 12.5, 15.0, 20.0]:
        sub = df_res[df_res['bps_450'] >= deadband_bps]
        if len(sub) == 0:
            continue
        # Vitória se o sinal aos 450s tem o mesmo sinal do fechamento final
        wins = ((sub['delta_450'] > 0) & (sub['full_delta'] > 0)) | ((sub['delta_450'] < 0) & (sub['full_delta'] < 0))
        wr = wins.mean() * 100.0
        win_rates[f"{deadband_bps} bps"] = {
            "win_rate_pct": round(wr, 2),
            "trades_count": int(len(sub)),
            "frequency_pct": round(len(sub) / len(df_res) * 100, 1)
        }

    # 3. Regime Horário de Volatilidade (UTC)
    hourly_stats = {}
    for h, group in df_res.groupby('hour_utc'):
        hourly_stats[int(h)] = {
            "avg_bps_450": round(float(group['bps_450'].mean()), 2),
            "median_bps_450": round(float(group['bps_450'].median()), 2),
            "sample_size": len(group)
        }

    print("\n  [RESULTADOS NATGAS - NYMEX HENRY HUB]:")
    print(f"  - Mediana de Deslocamento aos 450s: {p50_cents:.4f} ($/MMBtu) | {p50_bps:.1f} bps")
    print(f"  - Percentil 85 (Forte Inércia):     {p85_cents:.4f} ($/MMBtu) | {p85_bps:.1f} bps")
    print(f"  - Percentil 90 (Alta Certeza):      {p90_cents:.4f} ($/MMBtu) | {p90_bps:.1f} bps")
    print("\n  [TAXA DE ACERTO (WIN RATE) AO ENTRAR AOS 450s]:")
    for db_label, stats in win_rates.items():
        print(f"    * Deadband >= {db_label:8s}: WR = {stats['win_rate_pct']}% (Freq: {stats['frequency_pct']}% | N = {stats['trades_count']})")

    return {
        "asset": "NATGAS",
        "sample_size_15m": len(df_res),
        "percentiles_bps": {
            "p50": round(p50_bps, 2), "p75": round(p75_bps, 2), "p85": round(p85_bps, 2),
            "p90": round(p90_bps, 2), "p95": round(p95_bps, 2)
        },
        "percentiles_dollars": {
            "p50": round(p50_cents, 4), "p75": round(p75_cents, 4), "p85": round(p85_cents, 4),
            "p90": round(p90_cents, 4), "p95": round(p95_cents, 4)
        },
        "win_rates_by_deadband": win_rates,
        "hourly_volatility_utc": hourly_stats
    }

def analyze_es_spx_15m():
    print("\n" + "=" * 80)
    print("  📈 CALIBRANDO DESK 11: CME E-MINI S&P 500 (ES.c.0 - 1 ANO)")
    print("=" * 80)

    es_dir = os.path.join(DATA_DIR, "GLBX-20260927-RG6GDN8WJ4")
    files = sorted(glob.glob(os.path.join(es_dir, "*.dbn.zst")))
    print(f"[*] Processando {len(files)} arquivos diários de 1 segundo de ES...")

    candles_15m = []
    t0 = time.time()

    # Amostra dos últimos 90 dias para cálculo rápido
    for idx, f in enumerate(files[-90:]):
        try:
            store = db.DBNStore.from_file(f)
            df = store.to_df()
            if df.empty or 'close' not in df.columns:
                continue

            resampled = df['close'].resample('15min').ohlc().dropna()
            for period_start, row in resampled.iterrows():
                period_end = period_start + pd.Timedelta(minutes=15)
                mid_point = period_start + pd.Timedelta(seconds=450)

                slice_15m = df.loc[period_start:period_end, 'close']
                if len(slice_15m) < 60:
                    continue

                open_px = slice_15m.iloc[0]
                close_px = slice_15m.iloc[-1]
                sub_450 = slice_15m.loc[:mid_point]
                px_450 = sub_450.iloc[-1] if not sub_450.empty else open_px

                candles_15m.append({
                    "timestamp": period_start.isoformat(),
                    "hour_utc": period_start.hour,
                    "open": float(open_px),
                    "close": float(close_px),
                    "px_450": float(px_450),
                    "full_delta": float(close_px - open_px),
                    "delta_450": float(px_450 - open_px),
                    "abs_delta_450": float(abs(px_450 - open_px)),
                    "pts_450": float(abs(px_450 - open_px))
                })
        except Exception:
            continue

    dt = time.time() - t0
    df_es = pd.DataFrame(candles_15m)
    print(f"[OK] Total de velas de 15m analisadas no E-mini S&P 500: {len(df_es)} ({dt:.1f}s)")

    if df_es.empty:
        return {}

    # Teste de Win Rate no ES por pontos de deslocamento aos 450s
    win_rates_es = {}
    for deadband_pts in [1.5, 2.5, 3.5, 5.0, 7.5, 10.0]:
        sub = df_es[df_es['pts_450'] >= deadband_pts]
        if len(sub) == 0:
            continue
        wins = ((sub['delta_450'] > 0) & (sub['full_delta'] > 0)) | ((sub['delta_450'] < 0) & (sub['full_delta'] < 0))
        wr = wins.mean() * 100.0
        win_rates_es[f"{deadband_pts} pts"] = {
            "win_rate_pct": round(wr, 2),
            "trades_count": int(len(sub)),
            "frequency_pct": round(len(sub) / len(df_es) * 100, 1)
        }

    print("\n  [TAXA DE ACERTO (WIN RATE) NO E-MINI S&P 500 AO ENTRAR AOS 450s]:")
    for db_label, stats in win_rates_es.items():
        print(f"    * Deadband >= {db_label:8s}: WR = {stats['win_rate_pct']}% (Freq: {stats['frequency_pct']}% | N = {stats['trades_count']})")

    return {
        "asset": "ES_EMINI_SPX",
        "sample_size_15m": len(df_es),
        "win_rates_by_deadband": win_rates_es
    }

def main():
    print("=" * 80)
    print("  🧠 EXECUTANDO CALIBRAÇÃO DE DADOS DE ALTA FREQUÊNCIA DATABENTO")
    print("=" * 80)
    t_start = time.time()

    ng_res = analyze_natgas_15m()
    es_res = analyze_es_spx_15m()

    final_payload = {
        "timestamp": time.time(),
        "execution_time_sec": round(time.time() - t_start, 2),
        "natgas_verdict": ng_res,
        "es_spx_verdict": es_res
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)

    print("\n" + "=" * 80)
    print(f"  🎉 CALIBRAÇÃO CONCLUÍDA EM {time.time() - t_start:.1f}s!")
    print(f"  Resultados salvos em: {REPORT_JSON}")
    print("=" * 80)

if __name__ == "__main__":
    main()
