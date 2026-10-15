"""
=============================================================================
BACKTEST DESK 3B (POLYMARKET BTC 15M) — MICROESTRUTURA TICK-LEVEL SYNPATH/CROSS-VENUE
=============================================================================
Analisa todas as 64 operações reais do Desk 3B (Polymarket BTC 15m):
1. Mapeia cada janela para o contrato espelho de alta densidade na Kalshi (KXBTC15M).
2. Faz fetch do fluxo tick-level institucional/varejo nos 60s antes da entrada.
3. Calcula o Taker Imbalance exato (OFI) e volume transacionado.
4. Avalia a correlação de exaustão/FOMO entre vitórias e derrotas.
5. Simula o impacto financeiro de filtros anti-FOMO no histórico do Desk 3B.
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
JOURNAL_PATH = os.path.join(BASE_DIR, "desk3b_btc15m_live_journal.json")

if not os.path.exists(JOURNAL_PATH):
    print(f"[ERRO] Arquivo {JOURNAL_PATH} não encontrado.")
    sys.exit(1)

with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
    journal = json.load(f)

trades = journal.get("trades", [])
print("\n" + "=" * 78)
print(f"  BACKTEST DESK 3B (POLYMARKET BTC 15M) — MICROESTRUTURA TICK-LEVEL SYNPATH")
print(f"  Total de Operações: {len(trades)} | PnL Total Atual: ${journal.get('total_pnl', 0):+.2f} USDC")
print("=" * 78)

def window_ts_to_kalshi_ticker(w_ts: int) -> str:
    dt_utc = datetime.fromtimestamp(w_ts, tz=timezone.utc)
    end_utc = dt_utc + timedelta(seconds=900)
    end_et = end_utc.astimezone(ZoneInfo("America/New_York"))
    yy = end_et.strftime("%y")
    mmm = end_et.strftime("%b").upper()
    dd = end_et.strftime("%d")
    hh = end_et.strftime("%H")
    mm = end_et.strftime("%M")
    return f"KXBTC15M-{yy}{mmm}{dd}{hh}{mm}-{mm}"

results = []
out_report = os.path.join(BASE_DIR, "synpath_desk3b_tick_backtest_report.json")

for idx, t in enumerate(trades):
    w_ts = t.get("window_ts")
    if not w_ts:
        continue

    k_ticker = window_ts_to_kalshi_ticker(w_ts)
    side = t.get("side", "UP").upper()
    target_k_side = "yes" if side == "UP" else "no"
    
    ts_str = t.get("timestamp", "").replace(" UTC", "")
    try:
        dt = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        entry_s = int(dt.timestamp())
    except Exception:
        entry_s = w_ts + 500

    pnl = float(t.get("pnl", 0.0))
    is_win = (pnl > 0.0)
    outcome = t.get("outcome", "UNKNOWN")

    print(f"\n[{idx+1:02d}/{len(trades)}] Poly Window: {w_ts} | Kalshi: {k_ticker} | Side: {side} | Res: {outcome} | P&L: ${pnl:+.2f}")
    print(f"       Timestamp: {ts_str} UTC (epoch: {entry_s})")

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
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AntigravityDesk3BBacktest/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
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
            print(f"       [Flow @ 60s]: {trade_count} ticks | Vol: {total_vol:,.0f} | Aligned Takers: {aligned_vol:,.0f} | Contrary: {contrary_vol:,.0f} | Imbalance: {taker_imbalance:+.2f}")
        else:
            print(f"       [Flow]: 0 ticks na janela de 60s (livro calmo / fora de horário).")
    except Exception as e:
        print(f"       [Flow Erro]: {str(e)[:50]}")

    results.append({
        "window_ts": w_ts,
        "kalshi_ticker": k_ticker,
        "entry_s": entry_s,
        "timestamp": ts_str,
        "side": side,
        "target_k_side": target_k_side,
        "is_win": is_win,
        "outcome": outcome,
        "pnl": pnl,
        "delta_at_entry": t.get("delta_at_entry", 0.0),
        "trade_count": trade_count,
        "total_vol": round(total_vol, 1),
        "aligned_vol": round(aligned_vol, 1),
        "contrary_vol": round(contrary_vol, 1),
        "taker_imbalance": round(taker_imbalance, 3),
        "trades_ok": trades_ok
    })

    with open(out_report, "w", encoding="utf-8") as f:
        json.dump({"total_processed": len(results), "trades": results}, f, indent=2, ensure_ascii=False)

    time.sleep(0.08)

print("\n" + "=" * 78)
print("  ANÁLISE ESTATÍSTICA COMPARATIVA DE MICROESTRUTURA — DESK 3B (POLY BTC 15M)")
print("=" * 78)

valid_samples = [r for r in results if r["trades_ok"]]
print(f"Total de trades analisados com fluxo tick-level: {len(valid_samples)} de {len(results)}")

if valid_samples:
    wins = [r for r in valid_samples if r["is_win"]]
    losses = [r for r in valid_samples if not r["is_win"] and r["pnl"] < 0]
    voids = [r for r in valid_samples if r["pnl"] == 0]
    
    print(f"\n[A] DISTRIBUIÇÃO NA AMOSTRA COM DADOS:")
    print(f"    Vitórias Analisadas: {len(wins)} | Derrotas Analisadas: {len(losses)} | Breakeven/Void: {len(voids)}")
    if (len(wins) + len(losses)) > 0:
        print(f"    Taxa de Acerto Efetiva: {len(wins)/(len(wins)+len(losses))*100:.1f}%")

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
        p_losses = sum(1 for r in vetoed if r["pnl"] < 0)
        s_wins = sum(1 for r in vetoed if r["is_win"])
        saved_pnl = sum(abs(r["pnl"]) for r in vetoed if r["pnl"] < 0) - sum(r["pnl"] for r in vetoed if r["is_win"])
        eff_samples = [r for r in valid_samples if r not in vetoed and r["pnl"] != 0]
        new_w = sum(1 for r in eff_samples if r["is_win"])
        new_wr = (new_w / len(eff_samples) * 100) if eff_samples else 0.0
        print(f"    Threshold > {th:+.2f}: Veta {len(vetoed):2d} trades | Derrotas Evitadas: {p_losses:2d}/{len(losses)} | Vitórias Sacrificadas: {s_wins:2d}/{len(wins)} | Novo WR: {new_wr:.1f}% | Impacto P&L: ${saved_pnl:+.2f}")

print(f"\n[OK] Relatório gravado em: {out_report}\n")
