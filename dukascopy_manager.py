"""
Dukascopy Historical Data Manager & Python Interface.
Seamlessly integrates Dukascopy tick, 5m, 15m, 1h, and daily data with Polymarket bot desks.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd

BASE_DIR = Path(__file__).parent.resolve()
DUKASCOPY_DIR = BASE_DIR / "dukascopy_data"
ENGINE_DIR = BASE_DIR / "dukascopy_engine"


class DukascopyManager:
    """Manager for Dukascopy historical datasets and downloads."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DUKASCOPY_DIR
        self.engine_dir = ENGINE_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_file = self.data_dir / "catalog_instruments.json"

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Return the complete catalog of Dukascopy instruments."""
        if not self.catalog_file.exists():
            self.export_catalog()
        with open(self.catalog_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def search_instruments(self, query: str) -> List[Dict[str, Any]]:
        """Search instruments by symbol, name, or description."""
        q = query.lower()
        cat = self.get_catalog()
        return [
            item for item in cat
            if q in item["id"].lower() or q in item["name"].lower() or q in item["description"].lower()
        ]

    def export_catalog(self) -> None:
        """Run the catalog exporter script."""
        script = self.engine_dir / "export_catalog.js"
        subprocess.run(["node", str(script)], cwd=str(self.engine_dir), check=True)

    def run_bulk_download(self, preset: str = "core") -> None:
        """Run the automated institutional bulk downloader."""
        script = self.engine_dir / "bulk_downloader.js"
        subprocess.run(["node", str(script), f"--preset={preset}"], cwd=str(self.engine_dir), check=True)

    def download_instrument(
        self,
        instrument: str,
        timeframe: str = "m5",
        date_from: str = "2026-08-01",
        date_to: str = "2026-09-26",
        output_format: str = "csv"
    ) -> Path:
        """Download custom instrument and timeframe via npx / node."""
        cmd = [
            "npx", "--yes", "dukascopy-node",
            "-i", instrument.lower(),
            "-from", date_from,
            "-to", date_to,
            "-t", timeframe,
            "-f", output_format,
            "--volumes",
            "-dir", str(self.data_dir / "custom")
        ]
        (self.data_dir / "custom").mkdir(parents=True, exist_ok=True)
        subprocess.run(cmd, cwd=str(BASE_DIR), check=True)
        print(f"Custom download complete for {instrument} ({timeframe}) from {date_from} to {date_to}")
        return self.data_dir / "custom"

    def list_downloaded_datasets(self) -> List[Dict[str, Any]]:
        """List all CSV datasets present in dukascopy_data."""
        datasets = []
        for csv_file in self.data_dir.rglob("*.csv"):
            if "catalog" in csv_file.name:
                continue
            meta_file = csv_file.parent / f"{csv_file.stem}_meta.json"
            meta = {}
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    pass

            size_kb = round(csv_file.stat().st_size / 1024, 1)
            datasets.append({
                "file": csv_file.name,
                "path": str(csv_file),
                "category": csv_file.parent.name,
                "size_kb": size_kb,
                "meta": meta
            })
        return datasets

    def load_candles(self, file_path_or_symbol: str, timeframe: Optional[str] = None) -> pd.DataFrame:
        """
        Load historical candles into a clean pandas DataFrame.
        Automatically parses datetime_utc and sets as DatetimeIndex.
        """
        target_path = None
        if os.path.exists(file_path_or_symbol):
            target_path = Path(file_path_or_symbol)
        else:
            # Search by symbol and timeframe
            symbol_lower = file_path_or_symbol.lower()
            tf_lower = (timeframe or "").lower()
            for f in self.data_dir.rglob("*.csv"):
                fname_lower = f.name.lower()
                if symbol_lower in fname_lower:
                    if not tf_lower or f"_{tf_lower}_" in fname_lower:
                        target_path = f
                        break

        if not target_path or not target_path.exists():
            raise FileNotFoundError(f"Dataset not found for '{file_path_or_symbol}' (timeframe: {timeframe})")

        df = pd.read_csv(target_path)
        if "datetime_utc" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime_utc"])
        elif "timestamp" in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)
        return df


def load_dukascopy_candles(symbol: str, timeframe: str = "m5") -> pd.DataFrame:
    """Convenience helper for quick quant loading."""
    mgr = DukascopyManager()
    return mgr.load_candles(symbol, timeframe)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dukascopy Historical Data CLI")
    parser.add_argument("--status", action="store_true", help="Show downloaded datasets and catalog summary")
    parser.add_argument("--search", type=str, help="Search instruments catalog")
    parser.add_argument("--download-core", action="store_true", help="Download all core institutional datasets")
    parser.add_argument("--download-instrument", type=str, help="Download specific instrument (e.g. btcusd, xauusd)")
    parser.add_argument("--timeframe", type=str, default="m5", help="Timeframe (d1, h1, m15, m5, m1)")
    parser.add_argument("--from-date", type=str, default="2026-08-01", help="From date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=str, default="2026-09-26", help="To date (YYYY-MM-DD)")

    args = parser.parse_args()
    mgr = DukascopyManager()

    if args.status or len(sys.argv) == 1:
        cat = mgr.get_catalog()
        datasets = mgr.list_downloaded_datasets()
        print("\n=== DUKASCOPY HISTORICAL DATA ENGINE ===")
        print(f"Catalog Instruments Available: {len(cat):,}")
        print(f"Datasets Downloaded Locally: {len(datasets):,}")
        if datasets:
            print("\nDownloaded Datasets:")
            for d in datasets:
                print(f" - [{d['category'].upper()}] {d['file']} ({d['size_kb']} KB)")
        print("\nUsage:")
        print("  python dukascopy_manager.py --download-core")
        print("  python dukascopy_manager.py --search bitcoin")
        print("  python dukascopy_manager.py --download-instrument btcusd --timeframe m5 --from-date 2026-08-01")

    elif args.search:
        results = mgr.search_instruments(args.search)
        print(f"\nFound {len(results)} instruments matching '{args.search}':")
        for r in results[:20]:
            print(f" - {r['id']} | {r['name']} | {r['description']} | Category: {r['category']}")

    elif args.download_core:
        mgr.run_bulk_download(preset="core")

    elif args.download_instrument:
        mgr.download_instrument(
            instrument=args.download_instrument,
            timeframe=args.timeframe,
            date_from=args.from_date,
            date_to=args.to_date
        )
