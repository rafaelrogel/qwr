"""
HistData Manager & Quant Interface
Provides direct pandas loading and CLI tools for HistData 1-minute financial datasets.
"""

import os
import sys
import json
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd

BASE_DIR = Path(__file__).parent.resolve()
HISTDATA_DIR = BASE_DIR / "histdata_data"


class HistDataManager:
    """Manager for HistData 1-minute historical datasets."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or HISTDATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_file = self.data_dir / "catalog_histdata.json"

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Return the complete catalog of HistData pairs and years."""
        if not self.catalog_file.exists():
            import histdata_catalog_builder
            histdata_catalog_builder.build_catalog()
        with open(self.catalog_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def search_instruments(self, query: str) -> List[Dict[str, Any]]:
        """Search instruments by symbol, description, or category."""
        q = query.lower()
        cat = self.get_catalog()
        return [
            item for item in cat
            if q in item["pair"].lower() or q in item["description"].lower() or q in item["category"].lower()
        ]

    def list_local_archives(self) -> List[Dict[str, Any]]:
        """List all downloaded zip archives with sizes and pairs."""
        archives = []
        for zip_path in self.data_dir.rglob("*.zip"):
            size_mb = round(zip_path.stat().st_size / (1024 * 1024), 2)
            pair = zip_path.parent.name
            archives.append({
                "pair": pair,
                "file": zip_path.name,
                "path": str(zip_path),
                "size_mb": size_mb,
                "category": zip_path.parent.parent.name
            })
        return sorted(archives, key=lambda x: (x["category"], x["pair"]))

    def load_m1_candles(self, pair: str, year: int, max_rows: Optional[int] = None) -> pd.DataFrame:
        """
        Load 1-minute OHLC bar quotes directly from the downloaded ZIP archive
        without needing manual unpacking.
        Returns DataFrame with clean UTC DatetimeIndex and standard OHLCV columns.
        """
        pair_upper = pair.upper()
        # Find matching zip archive
        target_zip = None
        for z in self.data_dir.rglob(f"*_{pair_upper}_*_{year}.zip"):
            target_zip = z
            break

        if not target_zip or not target_zip.exists():
            raise FileNotFoundError(f"HistData archive not found for {pair_upper} ({year}) in {self.data_dir}")

        with zipfile.ZipFile(target_zip, "r") as zf:
            xlsx_files = [name for name in zf.namelist() if name.endswith(".xlsx")]
            if not xlsx_files:
                raise ValueError(f"No .xlsx file found inside {target_zip.name}")

            with zf.open(xlsx_files[0]) as f:
                # HistData Excel files do not have column headers
                df = pd.read_excel(f, header=None, nrows=max_rows)
                df.columns = ["datetime", "open", "high", "low", "close", "volume"][:len(df.columns)]
                df["datetime"] = pd.to_datetime(df["datetime"])
                df.set_index("datetime", inplace=True)
                df.sort_index(inplace=True)
                return df


def load_histdata_m1(pair: str, year: int, max_rows: Optional[int] = None) -> pd.DataFrame:
    """Convenience helper for quant loading."""
    mgr = HistDataManager()
    return mgr.load_m1_candles(pair, year, max_rows)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HistData Manager & Quant CLI")
    parser.add_argument("--status", action="store_true", help="Show catalog summary and local archives")
    parser.add_argument("--search", type=str, help="Search instruments in catalog")
    parser.add_argument("--load", nargs=2, metavar=("PAIR", "YEAR"), help="Test loading pair and year (e.g. EURUSD 2023)")

    args = parser.parse_args()
    mgr = HistDataManager()

    if args.status or len(sys.argv) == 1:
        cat = mgr.get_catalog()
        archives = mgr.list_local_archives()
        total_size = sum(a["size_mb"] for a in archives)
        print("\n=== HISTDATA 1-MINUTE QUANT ENGINE ===")
        print(f"Catalog Instruments Available: {len(cat):,}")
        print(f"Locally Downloaded Archives: {len(archives):,} ({total_size:.2f} MB)")
        if archives:
            print("\nDownloaded Archives:")
            for a in archives[:25]:
                print(f" - [{a['category'].upper()}] {a['pair']} ({a['file']}) -> {a['size_mb']} MB")
            if len(archives) > 25:
                print(f"   ... and {len(archives) - 25} more archives.")
        print("\nCommands:")
        print("  python histdata_downloader.py --preset core")
        print("  python histdata_downloader.py --pair XAUUSD --years 2021 2022 2023")
        print("  python histdata_manager.py --search gold")
        print("  python histdata_manager.py --load EURUSD 2023")

    elif args.search:
        results = mgr.search_instruments(args.search)
        print(f"\nFound {len(results)} instruments matching '{args.search}':")
        for r in results:
            print(f" - {r['pair']:<8} | {r['category']:<14} | {r['description']} | Years: {r['min_year']}..{r['max_year']}")

    elif args.load:
        p, y = args.load[0], int(args.load[1])
        print(f"\nLoading {p} {y} (first 100 rows)...")
        df = mgr.load_m1_candles(p, y, max_rows=100)
        print(df.head())
        print(f"\nTotal rows loaded: {len(df)}")
