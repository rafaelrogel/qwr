"""
Integration test for Dukascopy datasets & Polymarket bot quantitative feeds.
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from dukascopy_manager import DukascopyManager, load_dukascopy_candles


def run_checks():
    print("=== DUKASCOPY QUANT INTEGRATION TEST ===")
    mgr = DukascopyManager()

    # 1. Verify Catalog
    cat = mgr.get_catalog()
    print(f"[OK] Catalog loaded with {len(cat):,} instruments across all asset classes.")
    assert len(cat) >= 1400, "Catalog should have ~1,499 instruments"

    # 2. Search check
    gold_matches = mgr.search_instruments("gold")
    print(f"[OK] Search 'gold': found {len(gold_matches)} matching instruments.")
    assert any("xauusd" in m["id"] for m in gold_matches), "XAUUSD should be in gold results"

    btc_matches = mgr.search_instruments("bitcoin")
    print(f"[OK] Search 'bitcoin': found {len(btc_matches)} matching instruments.")
    assert any("btcusd" in m["id"] for m in btc_matches), "BTCUSD should be in bitcoin results"

    # 3. Check loaded data if available
    datasets = mgr.list_downloaded_datasets()
    print(f"[OK] Found {len(datasets)} locally downloaded datasets.")

    for d in datasets[:5]:
        print(f" -> Testing loader for: {d['file']}")
        df = mgr.load_candles(d['path'])
        assert not df.empty, f"DataFrame for {d['file']} should not be empty"
        assert all(c in df.columns for c in ["open", "high", "low", "close", "volume"]), "OHLCV columns missing"
        print(f"    Rows: {len(df):,}, Range: {df.index[0]} to {df.index[-1]}, Last Close: ${df['close'].iloc[-1]:,.2f}")

    print("\nALL DUKASCOPY CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_checks()
