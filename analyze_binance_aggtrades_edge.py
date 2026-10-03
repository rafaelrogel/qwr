# -*- coding: utf-8 -*-
"""
Script de Analise Quantitativa Forense de Microestrutura:
Processa amostras de alta frequencia dos 50 GB de Binance AggTrades (2020-2026)
para extrair estatisticas de Order Flow Imbalance (OFI), CVD e Predicao de Velas de 5 Minutos.
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
DATA_DIR = BASE_DIR / "tick_datasets_50gb" / "binance_aggtrades" / "BTCUSDT"

def analyze_sample_months(sample_zips):
    print("=" * 70)
    print(" [ANALISE QUANTITATIVA TICK DATA] Processando amostras de AggTrades...")
    print("=" * 70)

    # Agregadores de 5 minutos (300 segundos)
    # window_ts -> {buy_vol, sell_vol, buy_count, sell_count, open, high, low, close, first_ts, last_ts, trades_at_135}
    windows = defaultdict(lambda: {
        "buy_vol": 0.0, "sell_vol": 0.0,
        "buy_vol_135": 0.0, "sell_vol_135": 0.0,
        "open": None, "high": -1e9, "low": 1e9, "close": None,
        "close_135": None,
        "whale_buys": 0, "whale_sells": 0
    })

    total_trades_inspected = 0
    t0 = time.time()

    for zp in sample_zips:
        if not zp.exists():
            continue
        print(f"Lendo arquivo: {zp.name} ({zp.stat().st_size / (1024**2):.1f} MB)...")
        with zipfile.ZipFile(zp, "r") as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
                for row in reader:
                    # Formato: agg_trade_id, price, qty, first_id, last_id, timestamp_ms, is_buyer_maker, is_best_match
                    if not row or len(row) < 7:
                        continue
                    try:
                        price = float(row[1])
                        qty = float(row[2])
                        ts_ms = int(row[5])
                        is_buyer_maker = (row[6].lower() == "true")
                    except (ValueError, IndexError):
                        continue

                    total_trades_inspected += 1
                    ts_sec = ts_ms / 1_000_000.0 if ts_ms > 1e14 else ts_ms / 1000.0
                    w_ts = int(ts_sec // 300) * 300
                    elapsed = ts_sec - w_ts

                    w = windows[w_ts]
                    if w["open"] is None:
                        w["open"] = price
                    if price > w["high"]:
                        w["high"] = price
                    if price < w["low"]:
                        w["low"] = price
                    w["close"] = price

                    # Agressor: se is_buyer_maker == False -> Buyer e taker (agressao de compra)
                    is_buyer_taker = not is_buyer_maker
                    if is_buyer_taker:
                        w["buy_vol"] += qty
                        if elapsed <= 135.0:
                            w["buy_vol_135"] += qty
                        if qty >= 2.0:
                            w["whale_buys"] += 1
                    else:
                        w["sell_vol"] += qty
                        if elapsed <= 135.0:
                            w["sell_vol_135"] += qty
                        if qty >= 2.0:
                            w["whale_sells"] += 1

                    if elapsed <= 135.0:
                        w["close_135"] = price

                    # Amostragem para teste rapido (1.5 milhao de trades por arquivo e suficiente para significancia)
                    if total_trades_inspected >= 3000000:
                        break
        if total_trades_inspected >= 3000000:
            break

    el = time.time() - t0
    print(f"Total de trades analisados: {total_trades_inspected:,} em {el:.2f}s ({total_trades_inspected/el:,.0f} trades/s)")

    # Analise estatistica das velas de 5 minutos
    completed_windows = [
        w for w in windows.values()
        if w["open"] is not None and w["close"] is not None and w["close_135"] is not None and (w["buy_vol_135"] + w["sell_vol_135"]) > 0
    ]
    print(f"Total de velas completas de 5 minutos: {len(completed_windows)}")

    # 1. Teste de Agressor Imbalance aos 135s prevendo fecho da vela
    # Imbalance aos 135s = (buy_vol_135 - sell_vol_135) / (buy_vol_135 + sell_vol_135)
    imbalance_predictions = []
    drift_predictions = []
    concordant_both = []

    for w in completed_windows:
        tot_vol_135 = w["buy_vol_135"] + w["sell_vol_135"]
        if tot_vol_135 <= 0:
            continue
        ofi_135 = (w["buy_vol_135"] - w["sell_vol_135"]) / tot_vol_135
        drift_135 = w["close_135"] - w["open"]
        final_candle_dir = "UP" if w["close"] >= w["open"] else "DOWN"

        # Predicao por OFI (Order Flow Imbalance > 0.15)
        ofi_pred = "UP" if ofi_135 >= 0.15 else ("DOWN" if ofi_135 <= -0.15 else "NEUTRAL")
        # Predicao por Preco (Drift aos 135s)
        drift_pred = "UP" if drift_135 >= 15.0 else ("DOWN" if drift_135 <= -15.0 else "NEUTRAL")

        ofi_correct = (ofi_pred == final_candle_dir) if ofi_pred != "NEUTRAL" else None
        drift_correct = (drift_pred == final_candle_dir) if drift_pred != "NEUTRAL" else None

        if ofi_correct is not None:
            imbalance_predictions.append(ofi_correct)
        if drift_correct is not None:
            drift_predictions.append(drift_correct)
        if ofi_pred != "NEUTRAL" and ofi_pred == drift_pred:
            concordant_both.append(ofi_pred == final_candle_dir)

    wr_ofi = (sum(imbalance_predictions) / len(imbalance_predictions) * 100) if imbalance_predictions else 0.0
    wr_drift = (sum(drift_predictions) / len(drift_predictions) * 100) if drift_predictions else 0.0
    wr_concordant = (sum(concordant_both) / len(concordant_both) * 100) if concordant_both else 0.0

    divergent_cases = []
    whale_drift_cases = []

    for w in completed_windows:
        tot_vol_135 = w["buy_vol_135"] + w["sell_vol_135"]
        if tot_vol_135 <= 0:
            continue
        ofi_135 = (w["buy_vol_135"] - w["sell_vol_135"]) / tot_vol_135
        drift_135 = w["close_135"] - w["open"]
        final_candle_dir = "UP" if w["close"] >= w["open"] else "DOWN"

        # Predicao por OFI (Order Flow Imbalance > 0.15)
        ofi_pred = "UP" if ofi_135 >= 0.15 else ("DOWN" if ofi_135 <= -0.15 else "NEUTRAL")
        # Predicao por Preco (Drift aos 135s)
        drift_pred = "UP" if drift_135 >= 15.0 else ("DOWN" if drift_135 <= -15.0 else "NEUTRAL")

        # Casos Divergentes: Preço rompe para um lado, mas fluxo institucional agressivo está do lado oposto!
        if drift_pred != "NEUTRAL" and ofi_pred != "NEUTRAL" and drift_pred != ofi_pred:
            # Quem vence? O Preço ou o Fluxo?
            divergent_cases.append({
                "price_won": (drift_pred == final_candle_dir),
                "flow_won": (ofi_pred == final_candle_dir)
            })

    print("\n--- RESULTADOS EMPÍRICOS DA MICROESTRUTURA DE 5 MINUTOS ---")
    print(f"1. Apenas Preço aos 135s (|Drift| >= $15): Win Rate = {wr_drift:.2f}% (N = {len(drift_predictions)})")
    print(f"2. Apenas Order Flow Imbalance aos 135s (|OFI| >= 15%): Win Rate = {wr_ofi:.2f}% (N = {len(imbalance_predictions)})")
    print(f"3. Convergência DUPLA (Preço + Order Flow Imbalance aos 135s): Win Rate = {wr_concordant:.2f}% (N = {len(concordant_both)})")

    if divergent_cases:
        flow_win_pct = sum(1 for d in divergent_cases if d["flow_won"]) / len(divergent_cases) * 100
        price_win_pct = sum(1 for d in divergent_cases if d["price_won"]) / len(divergent_cases) * 100
        print(f"4. DIVERGÊNCIA TÓXICA (Preço aponta para um lado, mas OFI aponta para o oposto! N={len(divergent_cases)}):")
        print(f"   -> Win Rate do Preço despenca para: {price_win_pct:.2f}% (Whipsaw / Fakeout!)")
        print(f"   -> O Fluxo Oposto (Absorção Passiva) reverte a vela em {flow_win_pct:.2f}% dos casos!")

    edge_lift = wr_concordant - wr_drift
    results = {
        "total_trades_analyzed": total_trades_inspected,
        "completed_5m_candles": len(completed_windows),
        "wr_price_drift_alone_pct": round(wr_drift, 2),
        "wr_ofi_alone_pct": round(wr_ofi, 2),
        "wr_concordant_price_and_ofi_pct": round(wr_concordant, 2),
        "divergent_cases_count": len(divergent_cases),
        "divergent_price_win_pct": round(price_win_pct, 2) if divergent_cases else 0.0,
        "divergent_flow_win_pct": round(flow_win_pct, 2) if divergent_cases else 0.0,
        "edge_lift_pct": round(edge_lift, 2),
        "sample_files": [zp.name for zp in sample_zips]
    }

    with open("binance_aggtrades_microstructure_edge.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results

if __name__ == "__main__":
    # Pega os 3 arquivos mais recentes de 2026
    zips = sorted(list(DATA_DIR.glob("BTCUSDT-aggTrades-2026-*.zip")), reverse=True)[:3]
    analyze_sample_months(zips)
