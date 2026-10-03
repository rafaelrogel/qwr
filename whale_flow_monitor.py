"""
=============================================================================
WHALE LIQUIDITY SPIKE MONITOR (POLARIS WHALE RADAR)
=============================================================================
Monitor em tempo real de grandes ordens (Whales) na CLOB da Polymarket.
Inspirado na arquitetura de ent0n29/polybot e AutoPilotPM.

Detecta:
1. Ordens de grande porte (>= $250 USD / Mega-Whales >= $1,000 USD)
2. Viés direcional institucional em BTC 5m, SOL 5m, ETH 5m e Macro
3. Rastreamento e ranqueamento de carteiras institucionais com maior volume
4. Exporta alertas em tempo real para whale_flow_state.json e Dashboard Web
=============================================================================
"""

import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from risk_gate import atomic_write_json, safe_read_json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "whale_flow_state.json")
JOURNAL_PATH = os.path.join(BASE_DIR, "whale_flow_journal.json")

WHALE_MIN_USD = float(os.getenv("WHALE_MIN_USD", "200.0"))        # $200.00 USD
MEGA_WHALE_USD = float(os.getenv("MEGA_WHALE_USD", "1000.0"))    # $1,000.00 USD
POLL_INTERVAL_SEC = int(os.getenv("WHALE_POLL_INTERVAL", "6"))    # Varredura a cada 6s
MAX_RECENT_TRADES = 50

HEADERS = {"User-Agent": "AntigravityWhaleRadar/1.0"}


def load_journal() -> Dict[str, Any]:
    default_data = {
        "engine": "Whale Liquidity Spike Monitor",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_whale_trades_detected": 0,
        "total_whale_volume_usd": 0.0,
        "tracked_wallets": {},
        "trades": []
    }
    return safe_read_json(JOURNAL_PATH, default_data)


def save_journal(data: Dict[str, Any]):
    atomic_write_json(JOURNAL_PATH, data)


def categorize_market(title: str) -> str:
    tl = title.lower()
    if "bitcoin" in tl or "btc" in tl:
        return "BTC_5M" if "up or down" in tl or "5m" in tl or "15m" in tl else "BTC_MACRO"
    elif "solana" in tl or "sol" in tl:
        return "SOL_5M" if "up or down" in tl or "5m" in tl else "SOL_MACRO"
    elif "ethereum" in tl or "eth" in tl:
        return "ETH_5M" if "up or down" in tl or "5m" in tl else "ETH_MACRO"
    elif any(k in tl for k in ["presidential", "election", "senate", "trump", "harris", "biden", "vance"]):
        return "POLITICS"
    elif any(k in tl for k in ["fed", "cpi", "rate", "inflation", "gdp"]):
        return "MACRO_FINANCE"
    elif any(k in tl for k in ["temperature", "weather", "hurricane"]):
        return "WEATHER"
    return "OTHER"


def determine_directional_bias(side: str, outcome: str) -> str:
    s = str(side).upper()
    o = str(outcome).upper()
    if s == "BUY":
        if "YES" in o or "UP" in o:
            return "BULLISH"
        elif "NO" in o or "DOWN" in o:
            return "BEARISH"
    elif s == "SELL":
        if "YES" in o or "UP" in o:
            return "BEARISH"
        elif "NO" in o or "DOWN" in o:
            return "BULLISH"
    return "NEUTRAL"


def fetch_latest_trades() -> List[Dict[str, Any]]:
    url = "https://data-api.polymarket.com/trades?limit=50"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Whale Monitor] Erro ao buscar trades: {e}")
        return []


def run_whale_monitor_loop():
    print("=" * 75)
    print("🐳 [WHALE LIQUIDITY SPIKE MONITOR] INICIANDO MONITORAMENTO CLOB")
    print(f"Gatilho Whale: >= ${WHALE_MIN_USD:.2f} | Mega-Whale: >= ${MEGA_WHALE_USD:.2f} | Intervalo: {POLL_INTERVAL_SEC}s")
    print("=" * 75)

    journal = load_journal()
    seen_trade_ids: Set[str] = set()

    # Inicializa IDs já registrados no diário
    for t in journal.get("trades", []):
        tid = t.get("trade_id") or f"{t.get('wallet')}_{t.get('timestamp')}_{t.get('usd_volume')}"
        seen_trade_ids.add(tid)

    while True:
        try:
            trades = fetch_latest_trades()
            new_whales = 0
            now_utc = datetime.now(timezone.utc).isoformat()

            for t in reversed(trades): # Processa dos mais antigos para os mais recentes
                size = float(t.get("size") or 0.0)
                price = float(t.get("price") or 0.0)
                usd_vol = round(size * price, 2)

                if usd_vol < WHALE_MIN_USD:
                    continue

                ts = t.get("timestamp")
                wallet = t.get("proxyWallet") or t.get("makerAddress") or "unknown"
                tx_hash = t.get("transactionHash") or ""
                trade_id = tx_hash or f"{wallet}_{ts}_{usd_vol}_{size}"

                if trade_id in seen_trade_ids:
                    continue

                seen_trade_ids.add(trade_id)
                new_whales += 1

                title = t.get("title", "Unknown Market")
                outcome = t.get("outcome", "")
                side = t.get("side", "BUY")
                category = categorize_market(title)
                bias = determine_directional_bias(side, outcome)

                is_mega = (usd_vol >= MEGA_WHALE_USD)
                badge = "🚨 [MEGA-WHALE SPIKE]" if is_mega else "🐳 [WHALE FLOW]"

                print(f"{badge} {side} ${usd_vol:,.2f} USD @ ${price:.3f} | {outcome} ({bias}) | {category} | {title[:45]}... | Carteira: {wallet[:10]}...")

                entry = {
                    "trade_id": trade_id,
                    "timestamp": ts or now_utc,
                    "wallet": wallet,
                    "title": title,
                    "category": category,
                    "outcome": outcome,
                    "side": side,
                    "price": price,
                    "size": size,
                    "usd_volume": usd_vol,
                    "bias": bias,
                    "is_mega_whale": is_mega,
                    "detected_at": now_utc
                }

                journal["trades"].insert(0, entry)
                if len(journal["trades"]) > 500:
                    journal["trades"].pop()

                journal["total_whale_trades_detected"] += 1
                journal["total_whale_volume_usd"] = round(journal["total_whale_volume_usd"] + usd_vol, 2)

                # Estatísticas por Carteira
                w_stats = journal["tracked_wallets"].setdefault(wallet, {
                    "total_trades": 0,
                    "total_usd_volume": 0.0,
                    "bullish_count": 0,
                    "bearish_count": 0,
                    "last_seen": now_utc
                })
                w_stats["total_trades"] += 1
                w_stats["total_usd_volume"] = round(w_stats["total_usd_volume"] + usd_vol, 2)
                if bias == "BULLISH":
                    w_stats["bullish_count"] += 1
                elif bias == "BEARISH":
                    w_stats["bearish_count"] += 1
                w_stats["last_seen"] = now_utc

            if new_whales > 0:
                save_journal(journal)

            # Atualiza Estado para o Dashboard Web
            recent_trades = journal.get("trades", [])[:MAX_RECENT_TRADES]
            btc_5m_trades = [t for t in recent_trades if t.get("category") == "BTC_5M"]
            btc_bullish_vol = sum(t["usd_volume"] for t in btc_5m_trades if t.get("bias") == "BULLISH")
            btc_bearish_vol = sum(t["usd_volume"] for t in btc_5m_trades if t.get("bias") == "BEARISH")

            top_wallets = sorted(
                [{"wallet": k, **v} for k, v in journal.get("tracked_wallets", {}).items()],
                key=lambda x: x["total_usd_volume"],
                reverse=True
            )[:15]

            state = {
                "engine": "Whale Liquidity Spike Monitor",
                "active": True,
                "last_poll_utc": now_utc,
                "poll_interval_sec": POLL_INTERVAL_SEC,
                "min_whale_usd": WHALE_MIN_USD,
                "mega_whale_usd": MEGA_WHALE_USD,
                "total_whales_detected": journal.get("total_whale_trades_detected", 0),
                "total_volume_usd": journal.get("total_whale_volume_usd", 0.0),
                "btc_5m_sentiment": {
                    "bullish_volume_usd": round(btc_bullish_vol, 2),
                    "bearish_volume_usd": round(btc_bearish_vol, 2),
                    "net_flow_bias": "BULLISH" if btc_bullish_vol > btc_bearish_vol else ("BEARISH" if btc_bearish_vol > btc_bullish_vol else "NEUTRAL")
                },
                "latest_alert": recent_trades[0] if recent_trades else None,
                "top_whale_wallets": top_wallets,
                "recent_whale_trades": recent_trades[:20]
            }
            atomic_write_json(STATE_PATH, state)

        except Exception as e:
            print(f"[Whale Monitor Loop Erro]: {e}")

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    run_whale_monitor_loop()
