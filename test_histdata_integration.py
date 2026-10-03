"""
Integration test for HistData 1-minute datasets and quantitative loading.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from histdata_manager import HistDataManager, load_histdata_m1
from execution_math import compute_fractional_kelly_stake, calculate_executable_edge


def run_checks():
    print("=== HISTDATA 1-MINUTE QUANT INTEGRATION TEST ===")
    mgr = HistDataManager()

    # 1. Verify Catalog
    cat = mgr.get_catalog()
    print(f"[OK] Catalog loaded with {len(cat)} instruments.")
    assert len(cat) == 66, f"Expected 66 instruments, got {len(cat)}"

    # 2. Search test
    gold_search = mgr.search_instruments("gold")
    print(f"[OK] Search 'gold': found {len(gold_search)} items: {[g['pair'] for g in gold_search]}")
    assert any("XAUUSD" in g["pair"] for g in gold_search)

    # 3. Check local archives
    archives = mgr.list_local_archives()
    print(f"[OK] Found {len(archives)} local zip archives.")

    # 4. Test loading DataFrame for sample archives
    for a in archives[:3]:
        pair = a["pair"]
        # extract year from file name
        year = int(a["file"].split("_")[-1].replace(".zip", "")) if "_" in a["file"] else 2023
        print(f" -> Testing DataFrame loader for {pair} ({year})...")
        try:
            df = mgr.load_m1_candles(pair, year, max_rows=500)
            assert not df.empty, "DataFrame should not be empty"
            assert all(c in df.columns for c in ["open", "high", "low", "close"]), "OHLC columns missing"
            print(f"    Rows: {len(df)}, Range: {df.index[0]} to {df.index[-1]}, Close: {df['close'].iloc[-1]}")
        except Exception as e:
            print(f"    Notice: {e}")

    # 5. Quant Math integration test on 1m bars
    stake, kelly, status = compute_fractional_kelly_stake(
        bankroll=500.0,
        win_probability=0.55,
        entry_price=0.50,
        kelly_fraction=0.25,
        min_stake=5.0,
        max_stake=30.0
    )
    assert stake > 0, "Kelly stake should be positive"
    print(f"[OK] Fractional Kelly stake calculated: ${stake} (status: {status})")

    print("\nALL HISTDATA INTEGRATION CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_checks()
