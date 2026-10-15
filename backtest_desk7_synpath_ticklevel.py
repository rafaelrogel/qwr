"""
=============================================================================
BACKTEST DESK 7 (KALSHI GOLD 15M - KXGOLD15M) COM FLUXO TICK-LEVEL DE TRADES
=============================================================================
Analisa todas as 49 operações reais do Desk 7 (Ouro Kalshi):
1. Faz fetch dos trades tick-level no livro da Kalshi nos 60s antes da entrada.
2. Calcula o Taker Imbalance exato (OFI) e volume institucional vs varejo.
3. Avalia se vitórias e derrotas apresentam divergência de fluxo taker (anti-FOMO).
4. Simula o filtro em múltiplos thresholds (+0.30, +0.40, +0.50, +0.60).
=============================================================================
"""

import os
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_PATH = os.path.join(BASE_DIR, "kalshi_gold_15m_journal.json")

if not os.path.exists(JOURNAL_PATH):
    print(f"[ERRO] Arquivo {JOURNAL_PATH} não encontrado.")
    sys.exit(1)

with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
    journal = json.load(f)

trades = journal.get("trades", [])
print("\n" + "=" * 78)
print(f"  BACKTEST DESK 7 (KALSHI GOLD 15M) — MICROESTRUTURA TICK-LEVEL KALSHI/SYNPATH")
print(f"  Total de Operações: {len(trades)} | Win Rate Atual: {journal.get('win_rate', 0)}%")
print("=" * 78)

results = []
out_report = os.path.join(BASE_DIR, "synpath_desk7_tick_backtest_report.json")

for idx, t in enumerate(trades):
    ticker = t.get("ticker", "")
    if not ticker.startswith("KXGOLD15M"):
        continue

    ts_str = t.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        entry_s = int(dt.timestamp())
    except Exception:
        continue

    result_raw = str(t.get("result", "")).upper()
    is_win = ("VIT" in result_raw or "WIN" in result_raw)
    pnl = float(t.get("pnl", t.get("cycle_pnl", 0.0)))
    target_side = str(t.get("side", "YES")).upper()

    print(f"\n[{idx+1:02d}/{len(trades)}] {ticker} | Side: {target_side} | Result: {t.get('result', '')[:25]} | P&L: ${pnl:+.2f}")
    print(f"       Timestamp: {ts_str[:19]} UTC (epoch: {entry_s})")

    # Fetch trades tick-level nos 60s anteriores à entrada
    min_s = entry_s - 60
    max_s = entry_s
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/trades?ticker={ticker}&min_ts={min_s}&max_ts={max_s}&limit=100"
    
    trade_count = 0
    total_vol = 0.0
    aligned_vol = 0.0
    contrary_vol = 0.0
    taker_imbalance = 0.0
    trades_ok = False

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AntigravityDesk7Backtest/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        raw_trades = data.get("trades", [])
        trade_count = len(raw_trades)

        if trade_count > 0:
            trades_ok = True
            total_vol = sum(float(tr.get("count_fp", 1.0)) for tr in raw_trades)
            side_lower = target_side.lower()
            aligned_vol = sum(
                float(tr.get("count_fp", 1.0))
                for tr in raw_trades
                if tr.get("taker_side", "").lower() == side_lower
            )
            contrary_vol = total_vol - aligned_vol
            taker_imbalance = (aligned_vol - contrary_vol) / max(total_vol, 1.0)
            print(f"       [Flow @ 60s]: {trade_count} ticks | Vol: {total_vol:,.0f} | Aligned Takers: {aligned_vol:,.0f} | Contrary: {contrary_vol:,.0f} | Imbalance: {taker_imbalance:+.2f}")
        else:
            print(f"       [Flow]: 0 ticks na janela imediata de 60s.")
    except Exception as e:
        print(f"       [Flow Erro]: {str(e)[:50]}")

    results.append({
        "ticker": ticker,
        "entry_s": entry_s,
        "timestamp": ts_str,
        "is_win": is_win,
        "target_side": target_side,
        "result_label": t.get("result", ""),
        "pnl": pnl,
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
print("  ANÁLISE ESTATÍSTICA COMPARATIVA DE MICROESTRUTURA — OURO (DESK 7)")
print("=" * 78)

valid_samples = [r for r in results if r["trades_ok"]]
print(f"Total de trades analisados com fluxo tick-level: {len(valid_samples)} de {len(results)}")

if valid_samples:
    wins = [r for r in valid_samples if r["is_win"]]
    losses = [r for r in valid_samples if not r["is_win"]]
    print(f"\n[A] DISTRIBUIÇÃO NA AMOSTRA:")
    print(f"    Vitórias Analisadas: {len(wins)} | Derrotas Analisadas: {len(losses)}")
    print(f"    Taxa de Acerto na Amostra: {len(wins)/len(valid_samples)*100:.1f}%")

    ti_wins = [r["taker_imbalance"] for r in wins]
    ti_losses = [r["taker_imbalance"] for r in losses]

    avg_ti_w = sum(ti_wins)/len(ti_wins) if ti_wins else 0.0
    avg_ti_l = sum(ti_losses)/len(ti_losses) if ti_losses else 0.0

    print(f"\n[B] TAKER IMBALANCE (PRESSÃO DE FLUXO NA DIREÇÃO DO TRADE):")
    print(f"    Vitórias:  {avg_ti_w:+.3f}")
    print(f"    Derrotas:  {avg_ti_l:+.3f}")

    print(f"\n[C] SIMULAÇÃO DE THRESHOLDS ANTI-FOMO:")
    for th in [0.20, 0.30, 0.40, 0.50, 0.60, 0.70]:
        vetoed = [r for r in valid_samples if r["taker_imbalance"] > th]
        p_losses = sum(1 for r in vetoed if not r["is_win"])
        s_wins = sum(1 for r in vetoed if r["is_win"])
        saved_pnl = sum(abs(r["pnl"]) for r in vetoed if not r["is_win"]) - sum(r["pnl"] for r in vetoed if r["is_win"])
        new_w = len(wins) - s_wins
        new_total = len(valid_samples) - len(vetoed)
        new_wr = (new_w / new_total * 100) if new_total > 0 else 0.0
        print(f"    Threshold > {th:+.2f}: Veta {len(vetoed):2d} trades | Derrotas Evitadas: {p_losses:2d}/{len(losses)} | Vitórias Sacrificadas: {s_wins:2d}/{len(wins)} | Novo WR: {new_wr:.1f}% | Impacto P&L: ${saved_pnl:+.2f}")

print(f"\n[OK] Relatório final gravado em: {out_report}\n")
