"""
Análise Forense de Microestrutura: As 52 Quintas-Feiras do Relatório EIA (Henry Hub)
==================================================================================
Varre os 337 arquivos diários de TBBO do Gás Natural (NYMEX NG.c.0) e extrai o
comportamento do preço e livro de ofertas exatamente às 10:30 AM ET (14:30 UTC).
"""

import os
import sys
import glob
import time
import json
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import databento as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data_databento", "GLBX-20260927-KN86V6VDKR")

def analyze_eia_releases():
    print("=" * 80)
    print("  ⛽ AUDITORIA FORENSE DAS QUINTAS-FEIRAS DA EIA (NYMEX HENRY HUB TBBO)")
    print(f"  Diretório dos Dados: {DATA_DIR}")
    print("=" * 80)

    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.tbbo.dbn.zst")))
    print(f"[*] Total de arquivos diários de TBBO: {len(files)}")

    thursday_events = []

    for f in files:
        basename = os.path.basename(f)
        # Extrai data do nome do arquivo: glbx-mdp3-YYYYMMDD.tbbo.dbn.zst
        try:
            date_str = basename.split(".")[0].split("-")[-1]
            dt = pd.to_datetime(date_str)
            # Quinta-feira é weekday == 3
            if dt.weekday() != 3:
                continue

            store = db.DBNStore.from_file(f)
            df = store.to_df()
            if df.empty or 'price' not in df.columns:
                continue

            # Janela da EIA: 14:25 UTC a 14:45 UTC (10:25 a 10:45 AM ET)
            # ou 15:25 a 15:45 UTC em horário padrão
            eia_window = df.between_time('14:28', '14:45')
            if eia_window.empty:
                eia_window = df.between_time('15:28', '15:45')

            if eia_window.empty or len(eia_window) < 100:
                continue

            px_before = eia_window.iloc[0]['price']
            px_max = eia_window['price'].max()
            px_min = eia_window['price'].min()
            px_after_15m = eia_window.iloc[-1]['price']
            
            delta_15m = px_after_15m - px_before
            max_swing = max(abs(px_max - px_before), abs(px_min - px_before))
            swing_bps = (max_swing / px_before) * 10000

            thursday_events.append({
                "date": date_str,
                "px_pre": float(px_before),
                "px_post_15m": float(px_after_15m),
                "delta": round(float(delta_15m), 4),
                "max_swing_dollars": round(float(max_swing), 4),
                "swing_bps": round(float(swing_bps), 1),
                "total_trades_window": len(eia_window)
            })

        except Exception:
            continue

    df_eia = pd.DataFrame(thursday_events)
    print(f"\n[OK] Quintas-feiras de anúncio da EIA analisadas com sucesso: {len(df_eia)}")

    if not df_eia.empty:
        avg_swing = df_eia['swing_bps'].mean()
        median_swing = df_eia['swing_bps'].median()
        p90_swing = df_eia['swing_bps'].quantile(0.90)
        print(f"  - Salto Médio na Janela do Relatório: {avg_swing:.1f} bps (${df_eia['max_swing_dollars'].mean():.4f}/MMBtu)")
        print(f"  - Salto Mediano:                     {median_swing:.1f} bps (${df_eia['max_swing_dollars'].median():.4f}/MMBtu)")
        print(f"  - Salto Extremo (Percentil 90):      {p90_swing:.1f} bps (${df_eia['max_swing_dollars'].quantile(0.90):.4f}/MMBtu)")
        print("\n  [Exemplo dos Últimos 5 Relatórios Semanais]:")
        for _, row in df_eia.tail(5).iterrows():
            print(f"    * {row['date']}: Preço ${row['px_pre']:.3f} -> Variação {row['delta']:+.3f} (${row['swing_bps']} bps) | Trades: {row['total_trades_window']}")

    # Salva resultado em JSON
    out_file = os.path.join(BASE_DIR, "eia_52_weeks_analysis.json")
    with open(out_file, "w", encoding="utf-8") as out:
        json.dump({
            "timestamp": time.time(),
            "count": len(df_eia),
            "avg_swing_bps": round(float(df_eia['swing_bps'].mean()), 1) if not df_eia.empty else 0,
            "events": thursday_events
        }, out, indent=2)
    print(f"\n[✓] Relatório salvo em: {out_file}")

if __name__ == "__main__":
    analyze_eia_releases()
