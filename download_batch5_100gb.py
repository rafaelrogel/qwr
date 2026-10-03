# -*- coding: utf-8 -*-
"""
================================================================================
AGY QUANT DATA ENGINE - BATCH 5 (100.0 GB INSTITUTIONAL MICROSTRUCTURE & BOOKTICKER)
================================================================================
Downloads up to 98.0 GB of high-frequency order book and macro tick datasets:
1. Binance USD-M Perpetual Futures BookTicker (Millisecond Top-of-Book / Spread / Depth):
   - BTCUSDT (Primary crypto driver - 12 monthly archives, ~49.9 GB)
   - SOLUSDT (High-beta perpetual runner - 12 monthly archives, ~22.2 GB)
   - ETHUSDT (Perpetual driver - selected monthly archives, ~22-25 GB)
2. HistData Macro & Commodities High-Frequency Ticks:
   - SPXUSD (S&P 500 tick quotes for Desk 11 calibration)
   - XAUUSD (Gold spot tick quotes for Desk 9 calibration)
   - WTIUSD / BRENT (Crude oil macro ticks for Desks 4 & 5 calibration)

Strict Ceiling: 98.0 GB (105,226,698,752 bytes).
Leaves ~38.6 GB of safety free space on drive C:.
================================================================================
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# Windows UTF-8 stdout
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = BASE_DIR / "tick_datasets_batch5"
PROGRESS_FILE = BASE_DIR / "batch5_download_progress.json"

MAX_TOTAL_BYTES = int(98.0 * 1024 * 1024 * 1024)  # 98.0 GB
BINANCE_DL_BASE = "https://data.binance.vision"
HISTDATA_GET_URL = "https://www.histdata.com/get.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def get_current_dir_size(directory: Path) -> int:
    """Return total bytes of all files in directory."""
    total = 0
    if not directory.exists():
        return 0
    for root, _, files in os.walk(directory):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def update_progress(current_file: str, status: str, total_bytes: int, files_done: int, speed_mb: float = 0.0):
    """Write progress state to JSON."""
    gb_downloaded = round(total_bytes / (1024 ** 3), 3)
    pct = round((total_bytes / MAX_TOTAL_BYTES) * 100, 2)
    payload = {
        "batch": "BATCH_5_100GB_BOOKTICKER",
        "status": status,
        "timestamp": time.time(),
        "total_downloaded_bytes": total_bytes,
        "total_downloaded_gb": gb_downloaded,
        "max_limit_gb": 98.0,
        "progress_pct": min(100.0, pct),
        "files_downloaded": files_done,
        "speed_mb_s": round(speed_mb, 2),
        "current_file": current_file
    }
    try:
        tmp = PROGRESS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, PROGRESS_FILE)
    except Exception:
        pass


def download_binance_file(s3_key: str, dest_folder: Path, current_total: int) -> int:
    """Download single Binance archive with chunking, size verification, and resume support."""
    filename = s3_key.split("/")[-1]
    dest_path = dest_folder / filename
    part_path = dest_folder / (filename + ".part")

    if dest_path.exists() and dest_path.stat().st_size > 10000:
        return dest_path.stat().st_size

    url = f"{BINANCE_DL_BASE}/{s3_key}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_length = resp.headers.get("Content-Length")
            file_size = int(content_length) if content_length else 0

            if current_total + file_size > MAX_TOTAL_BYTES:
                print(f"  [TETO 98 GB ATINGIDO]: Arquivo {filename} ({file_size/(1024**2):.1f} MB) excederia o teto de segurança.")
                return -1

            downloaded = 0
            with open(part_path, "wb") as f_out:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1 MB chunk
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded += len(chunk)
                    if current_total + downloaded > MAX_TOTAL_BYTES:
                        break

        if current_total + downloaded > MAX_TOTAL_BYTES:
            if part_path.exists():
                part_path.unlink()
            return -1

        os.replace(part_path, dest_path)
        el = max(0.1, time.time() - t0)
        mb = downloaded / (1024 * 1024)
        speed = mb / el
        print(f"  [OK Binance] {filename}: {mb:.1f} MB em {el:.1f}s ({speed:.1f} MB/s)")
        return downloaded
    except Exception as e:
        print(f"  [Falha Binance]: {filename} -> {e}")
        if part_path.exists():
            try:
                part_path.unlink()
            except Exception:
                pass
        return 0


def get_histdata_tick_form(pair: str, year: int, month: int) -> Optional[Dict[str, str]]:
    """Retrieve token and form fields for HistData tick download."""
    page_url = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/{pair.lower()}/{year}/{month}"
    req = urllib.request.Request(page_url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=12)
        html = resp.read().decode("utf-8", errors="ignore")
        tk_m = re.search(r'id=[\x22\x27]tk[\x22\x27]\s+value=[\x22\x27]([^\x22\x27]+)[\x22\x27]', html)
        if not tk_m:
            return None
        return {
            "tk": tk_m.group(1),
            "date": str(year),
            "datemonth": f"{year}{month:02d}",
            "platform": "ASCII",
            "timeframe": "T",
            "fxpair": pair.upper(),
            "referer": page_url
        }
    except Exception:
        return None


def download_histdata_tick(form_data: Dict[str, str], dest_folder: Path, current_total: int) -> int:
    """POST to get.php to download HistData tick zip."""
    pair = form_data["fxpair"]
    datemonth = form_data["datemonth"]
    filename = f"HISTDATA_TICK_{pair}_{datemonth}.zip"
    dest_path = dest_folder / filename

    if dest_path.exists() and dest_path.stat().st_size > 50000:
        return dest_path.stat().st_size

    post_payload = urllib.parse.urlencode({
        "tk": form_data["tk"],
        "date": form_data["date"],
        "datemonth": form_data["datemonth"],
        "platform": form_data["platform"],
        "timeframe": form_data["timeframe"],
        "fxpair": pair
    }).encode("utf-8")

    headers = dict(HEADERS)
    headers["Origin"] = "https://www.histdata.com"
    headers["Referer"] = form_data["referer"]

    req = urllib.request.Request(HISTDATA_GET_URL, data=post_payload, headers=headers)
    try:
        t0 = time.time()
        resp = urllib.request.urlopen(req, timeout=45)
        content = resp.read()
        if len(content) < 5000:
            return 0
        if current_total + len(content) > MAX_TOTAL_BYTES:
            print(f"  [TETO 98 GB]: HistData {filename} excederia limite.")
            return -1

        with open(dest_path, "wb") as f:
            f.write(content)
        el = max(0.1, time.time() - t0)
        mb = len(content) / (1024 * 1024)
        print(f"  [OK HistData] {filename}: {mb:.1f} MB em {el:.1f}s")
        return len(content)
    except Exception as e:
        print(f"  [Falha HistData]: {filename} -> {e}")
        return 0


def build_batch5_manifest() -> List[Dict[str, Any]]:
    """Build prioritize download manifest for Batch 5."""
    manifest = []

    # 1. Binance USD-M Futures BookTicker: BTCUSDT (12 months = ~49.9 GB)
    btc_months = [
        "2023-05", "2023-06", "2023-07", "2023-08", "2023-09", "2023-10",
        "2023-11", "2023-12", "2024-01", "2024-02", "2024-03", "2024-04"
    ]
    for m in btc_months:
        manifest.append({
            "type": "binance_futures_bookticker",
            "symbol": "BTCUSDT",
            "key": f"data/futures/um/monthly/bookTicker/BTCUSDT/BTCUSDT-bookTicker-{m}.zip"
        })

    # 2. Binance USD-M Futures BookTicker: SOLUSDT (12 months = ~22.2 GB)
    sol_months = [
        "2023-05", "2023-06", "2023-07", "2023-08", "2023-09", "2023-10",
        "2023-11", "2023-12", "2024-01", "2024-02", "2024-03", "2024-04"
    ]
    for m in sol_months:
        manifest.append({
            "type": "binance_futures_bookticker",
            "symbol": "SOLUSDT",
            "key": f"data/futures/um/monthly/bookTicker/SOLUSDT/SOLUSDT-bookTicker-{m}.zip"
        })

    # 3. Binance USD-M Futures BookTicker: ETHUSDT (recent high-volume months = ~20-25 GB)
    eth_months = [
        "2023-10", "2023-11", "2023-12", "2024-01", "2024-02", "2024-03", "2023-09", "2023-08"
    ]
    for m in eth_months:
        manifest.append({
            "type": "binance_futures_bookticker",
            "symbol": "ETHUSDT",
            "key": f"data/futures/um/monthly/bookTicker/ETHUSDT/ETHUSDT-bookTicker-{m}.zip"
        })

    # 4. HistData Macro & Commodities: SPXUSD, XAUUSD, WTIUSD
    hist_pairs = [("SPXUSD", 2024), ("XAUUSD", 2024), ("WTIUSD", 2024)]
    for pair, yr in hist_pairs:
        for mo in [1, 2, 3, 4, 5, 6]:
            manifest.append({
                "type": "histdata_tick",
                "pair": pair,
                "year": yr,
                "month": mo
            })

    return manifest


def run_pipeline():
    print("=" * 80)
    print(" [AGY QUANT DATA ENGINE] INICIANDO DOWNLOAD DO LOTE 5 (100.0 GB)")
    print(f" Destino: {TARGET_DIR}")
    print(" Fontes:")
    print("  1. Binance USD-M Futures BookTicker (BTC, SOL, ETH Top-of-Book / Spread em ms)")
    print("  2. HistData Raw Ticks (S&P 500 SPXUSD, Ouro XAUUSD, Petróleo WTIUSD)")
    print(f" Teto Máximo: 98.0 GB (Preservando ~38.6 GB de espaço livre no C:)")
    print("=" * 80)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    bookticker_dir = TARGET_DIR / "binance_futures_bookticker"
    histdata_dir = TARGET_DIR / "histdata_ticks"
    bookticker_dir.mkdir(exist_ok=True)
    histdata_dir.mkdir(exist_ok=True)

    manifest = build_batch5_manifest()
    print(f"[Manifest] Total de {len(manifest)} arquivos programados para download.")

    total_bytes = get_current_dir_size(TARGET_DIR)
    files_done = 0
    t_start = time.time()

    update_progress("INITIALIZING", "RUNNING", total_bytes, files_done)

    for item in manifest:
        current_gb = total_bytes / (1024 ** 3)
        if total_bytes >= MAX_TOTAL_BYTES:
            print(f"\n[ALERTA TETO] Teto máximo de 98.0 GB atingido ({current_gb:.2f} GB). Encerrando lote.")
            break

        itype = item["type"]
        if itype == "binance_futures_bookticker":
            s3_key = item["key"]
            fn = s3_key.split("/")[-1]
            sym_dir = bookticker_dir / item["symbol"]
            sym_dir.mkdir(exist_ok=True)

            print(f"\n[Baixando {files_done+1}/{len(manifest)}] {fn} (Atual: {current_gb:.2f} GB / 98.0 GB)...")
            update_progress(fn, "DOWNLOADING", total_bytes, files_done)

            res = download_binance_file(s3_key, sym_dir, total_bytes)
            if res == -1:
                break
            if res > 0:
                total_bytes = get_current_dir_size(TARGET_DIR)
                files_done += 1
                el_tot = max(1.0, time.time() - t_start)
                speed = (total_bytes / (1024 * 1024)) / el_tot
                update_progress(fn, "RUNNING", total_bytes, files_done, speed)

        elif itype == "histdata_tick":
            pair = item["pair"]
            yr = item["year"]
            mo = item["month"]
            fn_label = f"{pair}_{yr}_{mo:02d}"
            print(f"\n[Baixando {files_done+1}/{len(manifest)}] HistData Tick {fn_label}...")
            update_progress(fn_label, "DOWNLOADING", total_bytes, files_done)

            form = get_histdata_tick_form(pair, yr, mo)
            if form:
                res = download_histdata_tick(form, histdata_dir, total_bytes)
                if res == -1:
                    break
                if res > 0:
                    total_bytes = get_current_dir_size(TARGET_DIR)
                    files_done += 1
                    el_tot = max(1.0, time.time() - t_start)
                    speed = (total_bytes / (1024 * 1024)) / el_tot
                    update_progress(fn_label, "RUNNING", total_bytes, files_done, speed)
            time.sleep(1.0)  # Respeita o rate limit do HistData

    final_gb = round(total_bytes / (1024 ** 3), 2)
    update_progress("FINISHED", "COMPLETED", total_bytes, files_done)
    print("\n" + "=" * 80)
    print(f" [LOTE 5 CONCLUÍDO] Total baixado: {final_gb} GB em {files_done} arquivos!")
    print(f" Diretório: {TARGET_DIR}")
    print("=" * 80)


if __name__ == "__main__":
    run_pipeline()
