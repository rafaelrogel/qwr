"""
=============================================================================
BACKTEST DESK 1 (POLYMARKET BTC 5M) — MICROESTRUTURA TICK-LEVEL CROSS-VENUE
=============================================================================
Analisa todas as 164 operações reais do Desk 1 (Polymarket BTC 5m):
1. Mapeia o timestamp exato de entrada para a vela ativa na Kalshi (KXBTC15M).
2. Consulta o fluxo tick-level nos 60s anteriores à entrada no Polymarket.
3. Calcula o Taker Imbalance e volume institucional/varejo.
4. Avalia a correlação de exaustão nas 52 derrotas reais vs 112 vitórias.
5. Simula o filtro anti-FOMO em múltiplos thresholds.
=============================================================================
"""

import os
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_PATH = os.path.join(BASE_DIR, "live_trading_journal.json")

if not os.path.exists(JOURNAL_PATH):
    print(f"[ERRO] Arquivo {JOURNAL_PATH} não encontrado.")
    sys.exit(1)

with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
    journal = json.load(f)

trades = journal.get("trades", [])
print("\n" + "=" * 78)
print(f"  BACKTEST DESK 1 (POLYMARKET BTC 5M) — MICROESTRUTURA TICK-LEVEL SYNPATH")
print(f"  Total de Operações: {len(trades)} | Win Rate Atual: {journal.get('win_rate', 0)}%")
print("=" * 78)

def get_active_kalshi_btc_ticker(epoch_s: int) -> str:
    # A vela de 15m da Kalshi que está ativa no momento epoch_s fecha no próximo múltiplo de 900s
    end_s = ((epoch_s // 900) + 1) * 900
    end_utc = datetime.fromtimestamp(end_s, tz=timezone.utc)
    end_ny = end_utc.astimezone(ZoneInfo("America/New_York"))
    yy = end_ny.strftime("%y")
    mmm = end_ny.strftime("%b").upper()
    dd = end_ny.strftime("%d")
    hh = end_ny.strftime("%H")
    mm = end_ny.strftime("%M")
    return f"KXBTC15M-{yy}{mmm}{dd}{hh}{mm}-{mm}"

results = []
out_report = os.path.join(BASE_DIR, "synpath_desk1_tick_backtest_report.json")

for idx, t in enumerate(trades):
    ts_str = t.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        entry_s = int(dt.timestamp())
    except Exception:
        entry_s = int(t.get("window_ts", 0)) + 135

    if not entry_s:
        continue

    k_ticker = get_active_kalshi_btc_ticker(entry_s)
    side = str(t.get("target_side") or t.get("side") or "UP").upper()
    target_k_side = "yes" if side == "UP" else "no"
    
    pnl = float(t.get("cycle_pnl", t.get("pnl", 0.0)))
    result_raw = str(t.get("result") or "").upper()
    is_win = ("VIT" in result_raw or pnl > 0)

    min_s = entry_s - 60
    max_s = entry_s
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/trades?ticker={k_ticker}&min_ts={min_s}&max_ts={max_s}&limit=100"
    
    trade_count = 0
    total_vol = 0.0
    aligned_vol = 0.0
    contrary_vol = 0.0
    taker_imbalance = 0.0
    trades_ok = False

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AntigravityDesk1Backtest/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        raw_trades = data.get("trades", [])
        trade_count = len(raw_trades)

        if trade_count > 0:
            trades_ok = True
            total_vol = sum(float(tr.get("count_fp", 1.0)) for tr in raw_trades)
            aligned_vol = sum(
                float(tr.get("count_fp", 1.0))
                for tr in raw_trades
                if tr.get("taker_side", "").lower() == target_k_side
            )
            contrary_vol = total_vol - aligned_vol
            taker_imbalance = (aligned_vol - contrary_vol) / max(total_vol, 1.0)
    except Exception:
        pass

    results.append({
        "cycle": t.get("cycle", idx+1),
        "timestamp": ts_str,
        "entry_s": entry_s,
        "kalshi_ticker": k_ticker,
        "side": side,
        "target_k_side": target_k_side,
        "is_win": is_win,
        "result": result_raw,
        "pnl": pnl,
        "trade_count": trade_count,
        "total_vol": round(total_vol, 1),
        "aligned_vol": round(aligned_vol, 1),
        "contrary_vol": round(contrary_vol, 1),
        "taker_imbalance": round(taker_imbalance, 3),
        "trades_ok": trades_ok
    })

    if (idx + 1) % 25 == 0 or (idx + 1) == len(trades):
        print(f"Progresso: [{idx+1:03d}/{len(trades)}] operações processadas...")
        with open(out_report, "w", encoding="utf-8") as f:
            json.dump({"total_processed": len(results), "trades": results}, f, indent=2, ensure_ascii=False)

    time.sleep(0.04)

print("\n" + "=" * 78)
print("  ANÁLISE ESTATÍSTICA COMPARATIVA DE MICROESTRUTURA — DESK 1 (BTC 5M)")
print("=" * 78)

valid_samples = [r for r in results if r["trades_ok"]]
print(f"Total de trades com dados tick-level Kalshi: {len(valid_samples)} de {len(results)}")

if valid_samples:
    wins = [r for r in valid_samples if r["is_win"]]
    losses = [r for r in valid_samples if not r["is_win"] and r["pnl"] < 0]
    
    print(f"\n[A] DISTRIBUIÇÃO NA AMOSTRA COM DADOS:")
    print(f"    Vitórias Analisadas: {len(wins)} | Derrotas Analisadas: {len(losses)}")
    if (len(wins) + len(losses)) > 0:
        print(f"    Taxa de Acerto na Amostra: {len(wins)/(len(wins)+len(losses))*100:.1f}%")

    ti_wins = [r["taker_imbalance"] for r in wins]
    ti_losses = [r["taker_imbalance"] for r in losses]

    avg_ti_w = sum(ti_wins)/len(ti_wins) if ti_wins else 0.0
    avg_ti_l = sum(ti_losses)/len(ti_losses) if ti_losses else 0.0

    print(f"\n[B] TAKER IMBALANCE (PRESSÃO DE FLUXO NA DIREÇÃO DO TRADE):")
    print(f"    Vitórias:  {avg_ti_w:+.3f}")
    print(f"    Derrotas:  {avg_ti_l:+.3f}")

    print(f"\n[C] SIMULAÇÃO DE THRESHOLDS ANTI-FOMO:")
    for th in [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
        vetoed = [r for r in valid_samples if r["taker_imbalance"] > th and r["total_vol"] >= 50.0]
        p_losses = sum(1 for r in vetoed if not r["is_win"])
        s_wins = sum(1 for r in vetoed if r["is_win"])
        saved_pnl = sum(abs(r["pnl"]) for r in vetoed if not r["is_win"]) - sum(r["pnl"] for r in vetoed if r["is_win"])
        eff_samples = [r for r in valid_samples if r not in vetoed]
        new_w = sum(1 for r in eff_samples if r["is_win"])
        new_wr = (new_w / len(eff_samples) * 100) if eff_samples else 0.0
        print(f"    Threshold > {th:+.2f}: Veta {len(vetoed):2d} trades | Derrotas Evitadas: {p_losses:2d}/{len(losses)} | Vitórias Sacrificadas: {s_wins:2d}/{len(wins)} | Novo WR: {new_wr:.1f}% | Impacto P&L: ${saved_pnl:+.2f}")

print(f"\n[OK] Relatório gravado em: {out_report}\n")
