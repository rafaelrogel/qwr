"""
anti_sweep_shield.py - Ziad Francis-Inspired Pivot & Liquidity Sweep Detection Shield
Operational Anti-Fakeout Defense for Desk 1 (BTC 5m) and Desk 2 (SOL 5m).

Based on Ziad Francis's (@ZiadFrancis) 'BreakOutLiquiditySweep' methodology:
- mark_pivots: Vectorized identification of rolling swing highs and swing lows.
- detect_structure: Distinguishes between a 'Liquidity Sweep' (intra-candle wick that
  breaches a key level to capture retail stop-loss liquidity before rejecting) and a
  'Structural Breakout / Trend Reversal' (confirmed candle body close beyond the level).

Prevents premature Stop-Loss liquidation during transient wicks (e.g., Cycle #152).
"""

import time
import json
import urllib.request
from typing import List, Dict, Tuple, Optional

# In-memory cache for Binance 1m klines: {symbol: (timestamp, klines)}
_KLINE_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
CACHE_TTL_SEC = 2.0


def fetch_binance_1m_klines(symbol: str, limit: int = 10, timeout: float = 2.0) -> List[dict]:
    """
    Fetches the latest 1m candles from Binance with low-latency in-memory caching.
    Returns list of dicts: [{'open_time': ms, 'open': f, 'high': f, 'low': f, 'close': f, 'volume': f}]
    """
    global _KLINE_CACHE
    now = time.time()
    if symbol in _KLINE_CACHE:
        cached_ts, cached_data = _KLINE_CACHE[symbol]
        if now - cached_ts < CACHE_TTL_SEC:
            return cached_data

    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval=1m&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AGY-AntiSweep/2.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            parsed = []
            for k in raw:
                parsed.append({
                    "open_time": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": int(k[6])
                })
            _KLINE_CACHE[symbol] = (now, parsed)
            return parsed
    except Exception as e:
        # Fallback to cache if available even if stale
        if symbol in _KLINE_CACHE:
            return _KLINE_CACHE[symbol][1]
        return []


def mark_pivots_1m(bars: List[dict], window: int = 1) -> List[dict]:
    """
    Identifies swing highs and swing lows across 1m bars using rolling extrema (Ziad's mark_pivots).
    - pivot_high = 1: Bar high >= neighbors
    - pivot_low  = 2: Bar low <= neighbors
    """
    n = len(bars)
    annotated = []
    for i in range(n):
        bar = dict(bars[i])
        bar["is_pivot"] = 0
        left_start = max(0, i - window)
        right_end = min(n, i + window + 1)
        
        neighbor_highs = [bars[j]["high"] for j in range(left_start, right_end)]
        neighbor_lows = [bars[j]["low"] for j in range(left_start, right_end)]
        
        is_ph = (bar["high"] == max(neighbor_highs))
        is_pl = (bar["low"] == min(neighbor_lows))
        
        if is_ph and is_pl:
            bar["is_pivot"] = 3
        elif is_ph:
            bar["is_pivot"] = 1
        elif is_pl:
            bar["is_pivot"] = 2
        
        annotated.append(bar)
    return annotated


def evaluate_anti_sweep_shield(
    symbol: str,
    window_ts: int,
    elapsed: float,
    target_side: str,
    strike: float,
    current_spot: float,
    current_delta: float,
    twap_delta: Optional[float] = None,
    klines_override: Optional[List[dict]] = None
) -> Dict[str, any]:
    """
    Evaluates whether an adverse price move is a transient Liquidity Sweep (fakeout wick)
    or a true Structural Reversal.

    Returns:
    {
        "is_sweep": bool,              # True -> Veto Stop-Loss (Hold position)
        "is_structural_reversal": bool,# True -> Reversal confirmed by candle bodies
        "allow_stop_loss": bool,       # True -> Stop-Loss authorized
        "rejection_ratio": float,      # Upper/lower wick rejection percentage (0.0 to 1.0)
        "reason": str,                 # Context description
        "bars_evaluated": int
    }
    """
    bars = klines_override if klines_override is not None else fetch_binance_1m_klines(symbol, limit=8)
    
    # If no data available, fail-safe: do not block stop-loss
    if not bars or len(bars) < 2:
        return {
            "is_sweep": False,
            "is_structural_reversal": True,
            "allow_stop_loss": True,
            "rejection_ratio": 0.0,
            "reason": "Sem dados de klines para validar estrutura (fail-safe liberado).",
            "bars_evaluated": 0
        }

    # Identify bars belonging to the current 5-minute window
    window_start_ms = window_ts * 1000
    window_end_ms = (window_ts + 300) * 1000

    window_bars = [b for b in bars if b["open_time"] >= window_start_ms and b["open_time"] < window_end_ms]
    
    # If window bars not found (e.g. slight clock skew), use latest 3 bars
    if not window_bars:
        window_bars = bars[-3:]

    # Separate closed bars in this window from current forming bar
    closed_bars = window_bars[:-1] if len(window_bars) > 1 else []
    current_bar = window_bars[-1]

    # Thresholds calibrated per asset
    is_btc = "BTC" in symbol.upper()
    buffer_amt = 8.0 if is_btc else 0.08  # Strike buffer in USD

    # Annotate pivots over recent bars
    pivoted_bars = mark_pivots_1m(bars, window=1)
    recent_ph = [b["high"] for b in pivoted_bars[:-1] if b["is_pivot"] in (1, 3)]
    recent_pl = [b["low"] for b in pivoted_bars[:-1] if b["is_pivot"] in (2, 3)]
    last_pivot_high = recent_ph[-1] if recent_ph else strike
    last_pivot_low = recent_pl[-1] if recent_pl else strike

    # Calculate Current Bar Wick Dynamics
    b_high = current_bar["high"]
    b_low = current_bar["low"]
    b_open = current_bar["open"]
    b_range = max(1.0 if is_btc else 0.01, b_high - b_low)

    is_sweep = False
    is_structural_reversal = False
    reason = ""
    rejection_ratio = 0.0

    if target_side == "DOWN":
        # DOWN wins if spot <= strike.
        # Adverse excursion: spot spiked upward (spot > strike or delta > 0).
        upper_wick = max(0.0, b_high - max(b_open, current_spot))
        rejection_ratio = upper_wick / b_range

        # Check 1: Has ANY completed 1m bar in this 5m window CLOSED above the strike + buffer?
        closed_above = [b for b in closed_bars if b["close"] > (strike + buffer_amt)]
        
        # Check 2: Did current bar spike to sweep stops above strike or recent Pivot High?
        swept_high = (b_high >= strike) or (b_high >= last_pivot_high)
        
        # Check 3: Is price actively rejecting from the peak?
        # A rejection occurs if current spot retreated from the high by >= 25% of bar range,
        # or if the upper wick accounts for >= 35% of the total candle span.
        wick_rejection = (rejection_ratio >= 0.35) or (current_spot <= b_high - (0.25 * b_range))

        # Check 4: TWAP Oracle Defense
        # If TWAP delta is still negative (in favor of DOWN), settlement remains DOWN-favored
        twap_favorable = (twap_delta is not None and twap_delta <= -5.0)

        if not closed_above and swept_high and (wick_rejection or twap_favorable):
            is_sweep = True
            reason = (
                f"Wick Sweep em ${b_high:,.2f} (Strike ${strike:,.2f}, PH ${last_pivot_high:,.2f}). "
                f"Rejeição superior: {rejection_ratio*100:.1f}%. Nenhuma barra 1m fechou acima do strike. "
                f"TWAP Delta: {f'{twap_delta:+.2f}' if twap_delta is not None else 'N/A'}."
            )
        elif closed_above and current_spot > (strike + buffer_amt):
            # A 1m bar actually closed above strike AND spot is continuing above
            is_structural_reversal = True
            reason = (
                f"Rompimento Estrutural Confirmado (BOS): Barra 1m fechou em ${closed_above[-1]['close']:,.2f} "
                f"(> Strike ${strike:,.2f}). Spot atual: ${current_spot:,.2f}."
            )
        elif not closed_above and not swept_high and twap_favorable:
            # Minor spot fluctuation, no breakout, TWAP safe
            is_sweep = True
            reason = f"Ruído transitório intra-vela sem rompimento de strike ou pivô. TWAP Delta seguro: {twap_delta:+.2f}."

    elif target_side == "UP":
        # UP wins if spot >= strike.
        # Adverse excursion: spot dumped downward (spot < strike or delta < 0).
        lower_wick = max(0.0, min(b_open, current_spot) - b_low)
        rejection_ratio = lower_wick / b_range

        # Check 1: Has ANY completed 1m bar in this 5m window CLOSED below the strike - buffer?
        closed_below = [b for b in closed_bars if b["close"] < (strike - buffer_amt)]

        # Check 2: Did current bar dump to sweep stops below strike or recent Pivot Low?
        swept_low = (b_low <= strike) or (b_low <= last_pivot_low)

        # Check 3: Is price actively rejecting upward from the low?
        wick_rejection = (rejection_ratio >= 0.35) or (current_spot >= b_low + (0.25 * b_range))

        # Check 4: TWAP Oracle Defense
        twap_favorable = (twap_delta is not None and twap_delta >= 5.0)

        if not closed_below and swept_low and (wick_rejection or twap_favorable):
            is_sweep = True
            reason = (
                f"Wick Sweep em ${b_low:,.2f} (Strike ${strike:,.2f}, PL ${last_pivot_low:,.2f}). "
                f"Rejeição inferior: {rejection_ratio*100:.1f}%. Nenhuma barra 1m fechou abaixo do strike. "
                f"TWAP Delta: {f'{twap_delta:+.2f}' if twap_delta is not None else 'N/A'}."
            )
        elif closed_below and current_spot < (strike - buffer_amt):
            is_structural_reversal = True
            reason = (
                f"Rompimento Estrutural Confirmado (BOS): Barra 1m fechou em ${closed_below[-1]['close']:,.2f} "
                f"(< Strike ${strike:,.2f}). Spot atual: ${current_spot:,.2f}."
            )
        elif not closed_below and not swept_low and twap_favorable:
            is_sweep = True
            reason = f"Ruído transitório intra-vela sem rompimento de strike ou pivô. TWAP Delta seguro: {twap_delta:+.2f}."

    # If it is a confirmed liquidity sweep, Stop-Loss is vetoed (allow_stop_loss = False)
    allow_stop_loss = not is_sweep if is_sweep else True

    return {
        "is_sweep": is_sweep,
        "is_structural_reversal": is_structural_reversal,
        "allow_stop_loss": allow_stop_loss,
        "rejection_ratio": round(rejection_ratio, 4),
        "reason": reason,
        "bars_evaluated": len(window_bars)
    }
