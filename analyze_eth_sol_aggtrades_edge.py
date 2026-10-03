# -*- coding: utf-8 -*-
"""
Análise Estatística Forense dos 50 GB de Tick Data (Lote 2):
Ethereum (ETHUSDT) e Solana (SOLUSDT) AggTrades na Microestrutura de 5 Minutos.
"""
import os
import sys
import zipfile
import csv
import io
import time
import json
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "tick_datasets_50gb" / "binance_aggtrades"

def analyze_symbol(sym, drift_threshold, sample_limit_trades=2000000):
    folder = DATA_DIR / sym
    zips = sorted(list(folder.glob(f"{sym}-aggTrades-2026-*.zip")), reverse=True)
    if not zips:
        zips = sorted(list(folder.glob(f"{sym}-aggTrades-*.zip")), reverse=True)[:2]

    print(f"\n[ANALISANDO {sym}] Processando arquivos de tick data...")
    windows = defaultdict(lambda: {
        "buy_vol": 0.0, "sell_vol": 0.0,
        "buy_vol_135": 0.0, "sell_vol_135": 0.0,
        "open": None, "close": None, "close_135": None
    })

    total_trades = 0
    t0 = time.time()

    for zp in zips:
        print(f"  Lendo {zp.name} ({zp.stat().st_size / (1024**2):.1f} MB)...")
        with zipfile.ZipFile(zp, "r") as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
                for row in reader:
                    if not row or len(row) < 7:
                        continue
                    try:
                        price = float(row[1])
                        qty = float(row[2])
                        ts_ms = int(row[5])
                        is_buyer_maker = (row[6].lower() == "true")
                    except (ValueError, IndexError):
                        continue

                    total_trades += 1
                    ts_sec = ts_ms / 1_000_000.0 if ts_ms > 1e14 else ts_ms / 1000.0
                    w_ts = int(ts_sec // 300) * 300
                    elapsed = ts_sec - w_ts

                    w = windows[w_ts]
                    if w["open"] is None:
                        w["open"] = price
                    w["close"] = price

                    is_buyer_taker = not is_buyer_maker
                    if is_buyer_taker:
                        w["buy_vol"] += qty
                        if elapsed <= 135.0:
                            w["buy_vol_135"] += qty
                    else:
                        w["sell_vol"] += qty
                        if elapsed <= 135.0:
                            w["sell_vol_135"] += qty

                    if elapsed <= 135.0:
                        w["close_135"] = price

                    if total_trades >= sample_limit_trades:
                        break
        if total_trades >= sample_limit_trades:
            break

    el = time.time() - t0
    print(f"  Total trades analisados: {total_trades:,} em {el:.2f}s ({total_trades/el:,.0f} trades/s)")

    completed = [
        w for w in windows.values()
        if w["open"] is not None and w["close"] is not None and w["close_135"] is not None and (w["buy_vol_135"] + w["sell_vol_135"]) > 0
    ]

    drift_preds = []
    ofi_preds = []
    concordant = []
    divergent = []

    for w in completed:
        tot_vol_135 = w["buy_vol_135"] + w["sell_vol_135"]
        ofi_135 = (w["buy_vol_135"] - w["sell_vol_135"]) / tot_vol_135
        drift_135 = w["close_135"] - w["open"]
        final_dir = "UP" if w["close"] >= w["open"] else "DOWN"

        d_pred = "UP" if drift_135 >= drift_threshold else ("DOWN" if drift_135 <= -drift_threshold else "NEUTRAL")
        o_pred = "UP" if ofi_135 >= 0.15 else ("DOWN" if ofi_135 <= -0.15 else "NEUTRAL")

        if d_pred != "NEUTRAL":
            drift_preds.append(d_pred == final_dir)
        if o_pred != "NEUTRAL":
            ofi_preds.append(o_pred == final_dir)
        if d_pred != "NEUTRAL" and d_pred == o_pred:
            concordant.append(d_pred == final_dir)
        if d_pred != "NEUTRAL" and o_pred != "NEUTRAL" and d_pred != o_pred:
            divergent.append(o_pred == final_dir)

    wr_drift = (sum(drift_preds) / len(drift_preds) * 100) if drift_preds else 0.0
    wr_ofi = (sum(ofi_preds) / len(ofi_preds) * 100) if ofi_preds else 0.0
    wr_concordant = (sum(concordant) / len(concordant) * 100) if concordant else 0.0
    div_reversal_pct = (sum(divergent) / len(divergent) * 100) if divergent else 0.0

    print(f"  Velas 5m Completas: {len(completed)}")
    print(f"  1. Apenas Preço (|Drift| >= {drift_threshold}): Win Rate = {wr_drift:.2f}% (N = {len(drift_preds)})")
    print(f"  2. Apenas OFI (|Imbalance| >= 15%): Win Rate = {wr_ofi:.2f}% (N = {len(ofi_preds)})")
    print(f"  3. Convergência DUPLA (Preço + OFI): Win Rate = {wr_concordant:.2f}% (N = {len(concordant)}) [Lift: {wr_concordant - wr_drift:+.2f}%]")
    print(f"  4. Divergência Tóxica (N = {len(divergent)}): Fluxo reverte a vela em {div_reversal_pct:.2f}% dos casos!")

    return {
        "symbol": sym,
        "trades_analyzed": total_trades,
        "completed_candles": len(completed),
        "wr_drift_pct": round(wr_drift, 2),
        "wr_ofi_pct": round(wr_ofi, 2),
        "wr_concordant_pct": round(wr_concordant, 2),
        "divergent_reversal_pct": round(div_reversal_pct, 2),
        "divergent_count": len(divergent)
    }

if __name__ == "__main__":
    eth_res = analyze_symbol("ETHUSDT", drift_threshold=1.50) # ETH $1.50 drift threshold
    sol_res = analyze_symbol("SOLUSDT", drift_threshold=0.10) # SOL $0.10 drift threshold

    results = {
        "timestamp": time.time(),
        "eth": eth_res,
        "sol": sol_res
    }
    with open("eth_sol_aggtrades_microstructure_edge.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\n[OK] Resultados gravados em 'eth_sol_aggtrades_microstructure_edge.json'.")
