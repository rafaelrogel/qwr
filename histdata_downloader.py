"""
Institutional HistData Bulk Downloader
Automates downloading of 1-minute bar quote archives (.xlsx / .zip)
from https://www.histdata.com/download-free-forex-data/?/excel/1-minute-bar-quotes
"""

import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).parent.resolve()
HISTDATA_DIR = BASE_DIR / "histdata_data"
HISTDATA_DIR.mkdir(parents=True, exist_ok=True)

PAIR_BASE_URL = "https://www.histdata.com/download-free-forex-historical-data/?/excel/1-minute-bar-quotes"
GET_URL = "https://www.histdata.com/get.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://www.histdata.com"
}

# Core assets corresponding to Antigravity Desks & Macro Quantitative Models
CORE_PRESET_CONFIG = {
    # Forex Majors
    "EURUSD": [2021, 2022, 2023],
    "GBPUSD": [2021, 2022, 2023],
    "USDJPY": [2021, 2022, 2023],
    "USDCHF": [2021, 2022, 2023],
    "AUDUSD": [2021, 2022, 2023],
    "USDCAD": [2021, 2022, 2023],
    # Commodities (Gold, Silver, WTI Crude, Brent)
    "XAUUSD": [2020, 2021, 2022, 2023],
    "XAGUSD": [2020, 2021, 2022, 2023],
    "WTIUSD": [2020, 2021, 2022, 2023],
    "BCOUSD": [2020, 2021, 2022, 2023],
    # Stock Indices (S&P 500, Nasdaq 100, DAX 40)
    "SPXUSD": [2020, 2021, 2022, 2023],
    "NSXUSD": [2020, 2021, 2022, 2023],
    "GRXEUR": [2020, 2021, 2022, 2023],
}


def get_category_folder(pair: str) -> Path:
    p = pair.upper()
    if p in ["XAUUSD", "XAGUSD", "WTIUSD", "BCOUSD", "XAUAUD", "XAUCHF", "XAUEUR", "XAUGBP", "AUXAUD"]:
        cat = "commodities"
    elif p in ["SPXUSD", "NSXUSD", "GRXEUR", "UKXGBP", "FRXEUR", "JPXJPY", "HKXHKD", "UDXUSD", "ETXEUR"]:
        cat = "indices"
    elif p in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]:
        cat = "forex"
    else:
        cat = "crosses"
    folder = HISTDATA_DIR / cat / p
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def download_single_archive(session: requests.Session, pair: str, year: int, retries: int = 3) -> Dict[str, Any]:
    """Download single yearly 1-minute XLSX zip archive from HistData."""
    pair_clean = pair.upper()
    folder = get_category_folder(pair_clean)
    filename = f"HISTDATA_XLSX_{pair_clean}_M1_{year}.zip"
    filepath = folder / filename

    if filepath.exists() and filepath.stat().st_size > 100000:
        size_kb = round(filepath.stat().st_size / 1024, 1)
        return {
            "pair": pair_clean,
            "year": year,
            "status": "CACHED",
            "file": str(filepath),
            "size_kb": size_kb
        }

    year_url = f"{PAIR_BASE_URL}/{pair_clean.lower()}/{year}"
    req_headers = dict(HEADERS)
    req_headers["Referer"] = year_url

    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            # 1. Scrape year page to retrieve unique token
            r = session.get(year_url, headers=req_headers, timeout=20)
            if r.status_code != 200:
                time.sleep(1)
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            tk_inp = soup.find("input", {"id": "tk"})
            if not tk_inp or not tk_inp.get("value"):
                return {
                    "pair": pair_clean,
                    "year": year,
                    "status": "NO_TOKEN",
                    "error": "Token not available for this year",
                    "file": None
                }

            token = tk_inp["value"]

            # 2. POST to get.php to trigger file download
            post_data = {
                "tk": token,
                "date": str(year),
                "datemonth": str(year),
                "platform": "XLSX",
                "timeframe": "M1",
                "fxpair": pair_clean
            }

            r_post = session.post(GET_URL, data=post_data, headers=req_headers, timeout=60)
            if r_post.status_code == 200 and len(r_post.content) > 10000:
                with open(filepath, "wb") as f:
                    f.write(r_post.content)

                size_kb = round(filepath.stat().st_size / 1024, 1)
                return {
                    "pair": pair_clean,
                    "year": year,
                    "status": "DOWNLOADED",
                    "file": str(filepath),
                    "size_kb": size_kb
                }

            time.sleep(1)
        except Exception as e:
            if attempt >= retries:
                return {
                    "pair": pair_clean,
                    "year": year,
                    "status": "FAILED",
                    "error": str(e),
                    "file": None
                }
            time.sleep(1.5 * attempt)

    return {
        "pair": pair_clean,
        "year": year,
        "status": "FAILED",
        "error": "Exhausted retries",
        "file": None
    }


def run_batch_download(tasks: List[tuple], max_workers: int = 5) -> List[Dict[str, Any]]:
    """Execute batch downloads concurrently with graceful pacing and live manifest updates."""
    print(f"\n========================================================")
    print(f"HISTDATA BULK DOWNLOAD ENGINE - {len(tasks)} ARCHIVES QUEUED")
    print(f"========================================================")

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    results = []
    manifest_path = HISTDATA_DIR / "download_manifest.json"

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(download_single_archive, session, pair, year): (pair, year)
            for pair, year in tasks
        }

        completed_count = 0
        total_kb = 0

        for fut in as_completed(future_map):
            completed_count += 1
            pair, year = future_map[fut]
            try:
                res = fut.result()
                results.append(res)
                st = res["status"]
                size_kb = res.get("size_kb", 0)
                if size_kb:
                    total_kb += size_kb
                pct = (completed_count / len(tasks)) * 100
                size_str = f"({size_kb} KB)" if size_kb else ""
                print(f"[{completed_count:4d}/{len(tasks)}] ({pct:5.1f}%) {pair:<7} {year} -> [{st}] {size_str} | Total: {total_kb/1024:.1f} MB")
            except Exception as e:
                print(f"[{completed_count:4d}/{len(tasks)}] {pair:<7} {year} -> [ERROR] {e}")

            # Save manifest periodically every 25 archives
            if completed_count % 25 == 0 or completed_count == len(tasks):
                manifest = {
                    "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "totalArchives": len(tasks),
                    "processed": len(results),
                    "successful": len([r for r in results if r["status"] in ("DOWNLOADED", "CACHED")]),
                    "totalSizeMB": round(total_kb / 1024, 2),
                    "archives": results
                }
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2)

    # Final manifest save
    manifest = {
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totalArchives": len(tasks),
        "processed": len(results),
        "successful": len([r for r in results if r["status"] in ("DOWNLOADED", "CACHED")]),
        "totalSizeMB": round(total_kb / 1024, 2),
        "archives": results
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n========================================================")
    print("DOWNLOAD BATCH COMPLETED!")
    print(f"Successful: {manifest['successful']} / {manifest['totalArchives']}")
    print(f"Total Disk Size: {manifest['totalSizeMB']} MB")
    print(f"Manifest: {manifest_path}")
    print("========================================================")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HistData 1-Minute Historical Downloader")
    parser.add_argument("--preset", type=str, default="core", choices=["core", "all"], help="Download preset: core or all")
    parser.add_argument("--pair", type=str, help="Specific instrument (e.g. EURUSD, XAUUSD)")
    parser.add_argument("--years", nargs="+", type=int, help="Specific years (e.g. 2021 2022 2023)")
    parser.add_argument("--status", action="store_true", help="Print download status")

    args = parser.parse_args()

    if args.status:
        archives = list(HISTDATA_DIR.rglob("*.zip"))
        total_size = sum(f.stat().st_size for f in archives) / (1024 * 1024)
        print("\n=== HISTDATA 1-MINUTE ARCHIVES STATUS ===")
        print(f"Total Local Zip Archives: {len(archives)}")
        print(f"Total Size: {total_size:.2f} MB")
        for f in sorted(archives)[:20]:
            print(f" - {f.parent.name}/{f.name} ({f.stat().st_size/1024:.1f} KB)")
        if len(archives) > 20:
            print(f" ... and {len(archives) - 20} more archives.")
        return

    tasks = []
    if args.pair:
        years = args.years or [2021, 2022, 2023]
        for y in years:
            tasks.append((args.pair.upper(), y))
    elif args.preset == "core":
        for pair, years in CORE_PRESET_CONFIG.items():
            for y in years:
                tasks.append((pair, y))
    elif args.preset == "all":
        # Load catalog
        cat_file = HISTDATA_DIR / "catalog_histdata.json"
        if not cat_file.exists():
            import histdata_catalog_builder
            histdata_catalog_builder.build_catalog()
        with open(cat_file, "r", encoding="utf-8") as f:
            cat = json.load(f)
        for item in cat:
            pair = item["pair"]
            for y in item.get("downloadable_years", []):
                tasks.append((pair, y))

    run_batch_download(tasks, max_workers=4)


if __name__ == "__main__":
    main()
