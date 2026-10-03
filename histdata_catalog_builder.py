"""
HistData Catalog Builder
Scrapes all available instruments and years from:
https://www.histdata.com/download-free-forex-data/?/excel/1-minute-bar-quotes
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).parent.resolve()
HISTDATA_DIR = BASE_DIR / "histdata_data"
HISTDATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.histdata.com/download-free-forex-data/?/excel/1-minute-bar-quotes"
PAIR_BASE_URL = "https://www.histdata.com/download-free-forex-historical-data/?/excel/1-minute-bar-quotes"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://www.histdata.com"
}


def classify_pair(pair: str) -> str:
    p = pair.upper()
    if p in ["XAUUSD", "XAGUSD", "WTIUSD", "BCOUSD", "XAUAUD", "XAUCHF", "XAUEUR", "XAUGBP", "AUXAUD"]:
        return "commodities"
    if p in ["SPXUSD", "NSXUSD", "GRXEUR", "UKXGBP", "FRXEUR", "JPXJPY", "HKXHKD", "UDXUSD", "ETXEUR"]:
        return "indices"
    if p in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]:
        return "forex_majors"
    return "forex_crosses"


def get_pair_description(pair: str) -> str:
    p = pair.upper()
    descriptions = {
        "XAUUSD": "Gold vs US Dollar",
        "XAGUSD": "Silver vs US Dollar",
        "WTIUSD": "WTI Light Sweet Crude Oil",
        "BCOUSD": "Brent Crude Oil",
        "SPXUSD": "S&P 500 Stock Index",
        "NSXUSD": "Nasdaq 100 Tech Index",
        "GRXEUR": "DAX 40 German Stock Index",
        "UKXGBP": "FTSE 100 UK Stock Index",
        "FRXEUR": "CAC 40 French Stock Index",
        "JPXJPY": "Nikkei 225 Japanese Stock Index",
        "HKXHKD": "Hang Seng Hong Kong Stock Index",
        "UDXUSD": "US Dollar Index (DXY)",
        "EURUSD": "Euro vs US Dollar",
        "GBPUSD": "British Pound vs US Dollar",
        "USDJPY": "US Dollar vs Japanese Yen",
        "USDCHF": "US Dollar vs Swiss Franc",
        "AUDUSD": "Australian Dollar vs US Dollar",
        "USDCAD": "US Dollar vs Canadian Dollar",
        "NZDUSD": "New Zealand Dollar vs US Dollar",
    }
    return descriptions.get(p, f"{p[:3]}/{p[3:]} Currency Pair" if len(p) == 6 else f"{p} Financial Instrument")


def inspect_single_pair(session: requests.Session, pair: str) -> dict:
    url = f"{PAIR_BASE_URL}/{pair.lower()}"
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        years = []
        for a in soup.find_all("a", href=True):
            m = re.search(rf"/{pair.lower()}/(\d{{4}})$", a["href"], re.IGNORECASE)
            if m:
                years.append(int(m.group(1)))
        years = sorted(list(set(years)))
        # Only years <= 2023 have free tokens
        downloadable_years = [y for y in years if y <= 2023]
        return {
            "pair": pair,
            "category": classify_pair(pair),
            "description": get_pair_description(pair),
            "url": url,
            "all_years": years,
            "downloadable_years": downloadable_years,
            "min_year": min(downloadable_years) if downloadable_years else None,
            "max_year": max(downloadable_years) if downloadable_years else None,
            "total_downloadable_years": len(downloadable_years)
        }
    except Exception as e:
        return {
            "pair": pair,
            "category": classify_pair(pair),
            "description": get_pair_description(pair),
            "url": url,
            "error": str(e),
            "downloadable_years": []
        }


def build_catalog():
    print(">>> Fetching HistData main instruments directory...")
    s = requests.Session()
    r = s.get(BASE_URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    pairs = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"/1-minute-bar-quotes/([A-Z0-9]+)", a["href"])
        if m:
            p = m.group(1).upper()
            if p not in pairs:
                pairs.append(p)

    print(f"Found {len(pairs)} instruments on HistData. Querying available year archives...")

    catalog = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(inspect_single_pair, s, p): p for p in pairs}
        for fut in as_completed(futures):
            res = fut.result()
            catalog.append(res)
            print(f" - {res['pair']:<8} | {res['category']:<14} | Years: {res.get('min_year')} to {res.get('max_year')} ({res.get('total_downloadable_years', 0)} yrs)")

    catalog.sort(key=lambda x: (x["category"], x["pair"]))

    # Save JSON
    json_path = HISTDATA_DIR / "catalog_histdata.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    # Save CSV
    csv_path = HISTDATA_DIR / "catalog_histdata.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("pair,category,description,min_year,max_year,total_years,all_years_csv\n")
        for item in catalog:
            years_str = ";".join(str(y) for y in item.get("downloadable_years", []))
            desc = f'"{item["description"]}"'
            f.write(f'{item["pair"]},{item["category"]},{desc},{item.get("min_year")},{item.get("max_year")},{item.get("total_downloadable_years", 0)},"{years_str}"\n')

    print("\n==========================================")
    print("HISTDATA CATALOG COMPLETED SUCCESSFULLY!")
    print(f"Total Instruments: {len(catalog)}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print("==========================================")


if __name__ == "__main__":
    build_catalog()
