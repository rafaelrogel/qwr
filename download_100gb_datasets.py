# -*- coding: utf-8 -*-
"""
High-Performance Institutional Tick Data Downloader - BATCH 4 (100 GB)
======================================================================
Downloads up to 100.0 GB of institutional high-frequency tick data:
1. Binance USD-M Perpetual Futures Raw AggTrades (Millisecond Ticks):
   - BTCUSDT (Primary crypto market driver / liquidation cascade trigger)
   - ETHUSDT (Secondary perpetual driver)
   - SOLUSDT (High-beta perpetual driver)
2. Binance Spot Raw AggTrades:
   - POLUSDT / MATICUSDT, NEARUSDT, APTUSDT, SUIUSDT
3. HistData Raw Bid/Ask Tick Quotes:
   - WTIUSD / BRENT (Energy / Crude Oil)
   - XAGUSD (Silver spot - Precious Metals)
   - NSXUSD (Nasdaq 100)

Strict Ceiling: 100.0 GB (107,374,182,400 bytes).
Leaves ~38.2 GB of disk space free on drive C:.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any

# Windows UTF-8 stdout
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = BASE_DIR / "tick_datasets_50gb"
TARGET_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = BASE_DIR / "tick_datasets_progress.json"

MAX_TOTAL_BYTES = 100 * 1024 * 1024 * 1024  # 100.0 GB exatos
BINANCE_S3_BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BINANCE_DL_BASE = "https://data.binance.vision"
HISTDATA_GET_URL = "https://www.histdata.com/get.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
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


def update_progress(current_file: str, status: str, total_bytes: int, files_done: int):
    """Write progress state to JSON."""
    gb_downloaded = round(total_bytes / (1024 ** 3), 3)
    pct = round((total_bytes / MAX_TOTAL_BYTES) * 100, 2)
    payload = {
        "batch": "BATCH_4_100GB",
        "status": status,
        "timestamp": time.time(),
        "total_downloaded_bytes": total_bytes,
        "total_downloaded_gb": gb_downloaded,
        "max_limit_gb": 100.0,
        "progress_pct": min(100.0, pct),
        "files_downloaded": files_done,
        "current_file": current_file
    }
    try:
        tmp = PROGRESS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, PROGRESS_FILE)
    except Exception:
        pass


def get_binance_s3_keys(prefix: str) -> List[str]:
    """Retrieve all monthly zip keys from Binance S3."""
    url = f"{BINANCE_S3_BASE}?prefix={prefix}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        root = ET.fromstring(resp.read())
        keys = [
            elem.text for elem in root.iter("{http://s3.amazonaws.com/doc/2006-03-01/}Key")
            if elem.text and elem.text.endswith(".zip")
        ]
        return sorted(keys, reverse=True)
    except Exception as e:
        print(f"  [Binance S3 Error for {prefix}]: {e}")
        return []


def download_binance_key(key: str, dest_folder: Path, current_total: int) -> int:
    """Download single Binance zip file if within budget."""
    filename = key.split("/")[-1]
    dest_path = dest_folder / filename

    if dest_path.exists() and dest_path.stat().st_size > 100000:
        return dest_path.stat().st_size

    download_url = f"{BINANCE_DL_BASE}/{key}"
    req = urllib.request.Request(download_url, headers=HEADERS)

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        content_len = resp.headers.get("Content-Length")
        if content_len:
            est_size = int(content_len)
            if current_total + est_size > MAX_TOTAL_BYTES:
                print(f"  [TETO 100 GB ATINGIDO]: Arquivo {filename} ({est_size / (1024**2):.1f} MB) excederia limite.")
                return -1

        t0 = time.time()
        downloaded = 0
        part_path = dest_path.with_suffix(".part")
        with open(part_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if current_total + downloaded > MAX_TOTAL_BYTES:
                    print(f"\n  [TETO 100 GB]: Limite exato atingido durante download de {filename}.")
                    break

        if current_total + downloaded > MAX_TOTAL_BYTES:
            try:
                part_path.unlink()
            except OSError:
                pass
            return -1

        os.replace(part_path, dest_path)
        el = max(0.1, time.time() - t0)
        mb = downloaded / (1024 * 1024)
        print(f"  [OK Binance] {filename}: {mb:.1f} MB em {el:.1f}s ({mb/el:.1f} MB/s)")
        return downloaded
    except Exception as e:
        print(f"  [Falha Binance]: {filename} -> {e}")
        return 0


def get_histdata_tick_form(pair: str, year: int, month: int):
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
            print(f"  [TETO 100 GB]: HistData {filename} excederia limite.")
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


def run_pipeline():
    print("=" * 80)
    print(" [AGY QUANT DATA ENGINE] INICIANDO DOWNLOAD INSTITUCIONAL DO LOTE 4 (100.0 GB)")
    print(f" Destino: {TARGET_DIR}")
    print(" Fontes:")
    print("  1. Binance USD-M Futures Raw AggTrades (BTC, ETH, SOL Perpetual Ticks)")
    print("  2. Binance Spot AggTrades (POL/MATIC, NEAR, APT, SUI)")
    print("  3. HistData Raw Ticks (WTI Crude, Silver XAG, Nasdaq NSX)")
    print("=" * 80)

    futures_dir = TARGET_DIR / "binance_futures_aggtrades"
    spot_dir = TARGET_DIR / "binance_aggtrades"
    histdata_dir = TARGET_DIR / "histdata_ticks"
    futures_dir.mkdir(exist_ok=True)
    spot_dir.mkdir(exist_ok=True)
    histdata_dir.mkdir(exist_ok=True)

    total_bytes = get_current_dir_size(TARGET_DIR)
    files_done = 0
    update_progress("INITIALIZING", "RUNNING", total_bytes, files_done)

    # 1. Pipeline Binance USD-M Perpetual Futures (BTC, ETH, SOL)
    futures_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    for sym in futures_symbols:
        sym_dir = futures_dir / sym
        sym_dir.mkdir(exist_ok=True)
        prefix = f"data/futures/um/monthly/aggTrades/{sym}/"
        keys = get_binance_s3_keys(prefix)
        print(f"\n[Binance Futures {sym}] {len(keys)} meses disponíveis. Baixando...")

        for k in keys:
            if total_bytes >= MAX_TOTAL_BYTES:
                print("\n>>> LIMITE INSTITUCIONAL DE 100.0 GB ATINGIDO COM SUCESSO! <<<")
                update_progress("COMPLETE", "FINISHED_100GB_CAP", total_bytes, files_done)
                return

            fname = k.split("/")[-1]
            update_progress(fname, "DOWNLOADING", total_bytes, files_done)
            res = download_binance_key(k, sym_dir, total_bytes)
            if res == -1:
                print("\n>>> LIMITE DE 100.0 GB ATINGIDO! <<<")
                update_progress("COMPLETE", "FINISHED_100GB_CAP", total_bytes, files_done)
                return
            elif res > 0:
                total_bytes += res
                files_done += 1
                gb = total_bytes / (1024 ** 3)
                print(f"      Progresso Total: {gb:.2f} GB / 100.0 GB ({round((gb/100.0)*100, 1)}%)")

    # 2. Pipeline Binance Spot Raw AggTrades (POL/MATIC, NEAR, APT, SUI)
    spot_symbols = ["POLUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT"]
    for sym in spot_symbols:
        sym_dir = spot_dir / sym
        sym_dir.mkdir(exist_ok=True)
        prefix = f"data/spot/monthly/aggTrades/{sym}/"
        keys = get_binance_s3_keys(prefix)
        print(f"\n[Binance Spot {sym}] {len(keys)} meses disponíveis. Baixando...")

        for k in keys:
            if total_bytes >= MAX_TOTAL_BYTES:
                print("\n>>> LIMITE INSTITUCIONAL DE 100.0 GB ATINGIDO COM SUCESSO! <<<")
                update_progress("COMPLETE", "FINISHED_100GB_CAP", total_bytes, files_done)
                return

            fname = k.split("/")[-1]
            update_progress(fname, "DOWNLOADING", total_bytes, files_done)
            res = download_binance_key(k, sym_dir, total_bytes)
            if res == -1:
                print("\n>>> LIMITE DE 100.0 GB ATINGIDO! <<<")
                update_progress("COMPLETE", "FINISHED_100GB_CAP", total_bytes, files_done)
                return
            elif res > 0:
                total_bytes += res
                files_done += 1
                gb = total_bytes / (1024 ** 3)
                print(f"      Progresso Total: {gb:.2f} GB / 100.0 GB ({round((gb/100.0)*100, 1)}%)")

    # 3. Pipeline HistData Raw Tick Data (Silver, WTI, Nasdaq)
    hist_pairs = ["XAGUSD", "WTIUSD", "NSXUSD"]
    years = [2024, 2023, 2022, 2021]
    months = list(range(12, 0, -1))

    for p in hist_pairs:
        p_dir = histdata_dir / p
        p_dir.mkdir(exist_ok=True)
        print(f"\n[HistData Tick {p}] Baixando ticks brutos...")

        for y in years:
            for m in months:
                if total_bytes >= MAX_TOTAL_BYTES:
                    print("\n>>> LIMITE INSTITUCIONAL DE 100.0 GB ATINGIDO! <<<")
                    update_progress("COMPLETE", "FINISHED_100GB_CAP", total_bytes, files_done)
                    return

                form = get_histdata_tick_form(p, y, m)
                if not form:
                    continue

                fname = f"HISTDATA_TICK_{p}_{y}{m:02d}.zip"
                update_progress(fname, "DOWNLOADING", total_bytes, files_done)
                res = download_histdata_tick(form, p_dir, total_bytes)
                if res == -1:
                    print("\n>>> LIMITE DE 100.0 GB ATINGIDO! <<<")
                    update_progress("COMPLETE", "FINISHED_100GB_CAP", total_bytes, files_done)
                    return
                elif res > 0:
                    total_bytes += res
                    files_done += 1
                    gb = total_bytes / (1024 ** 3)
                    print(f"      Progresso Total: {gb:.2f} GB / 100.0 GB ({round((gb/100.0)*100, 1)}%)")

    print("\n" + "=" * 80)
    print(f" PIPELINE LOTE 4 CONCLUÍDO: Total baixado = {total_bytes / (1024**3):.2f} GB em {files_done} arquivos.")
    print("=" * 80)
    update_progress("FINISHED", "FINISHED_ALL", total_bytes, files_done)


if __name__ == "__main__":
    run_pipeline()
