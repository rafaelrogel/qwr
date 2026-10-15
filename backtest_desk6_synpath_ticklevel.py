"""
=============================================================================
BACKTEST DESK 6 (KALSHI BTC 15M) COM DADOS TICK-LEVEL DO SYNPATH
=============================================================================
Reconstrói a microestrutura exata no milissegundo de entrada para cada trade
histórico do Desk 6 (KXBTC15M).

Para cada trade no kalshi_trading_journal.json:
1. Converte o timestamp UTC do journal para milissegundos UNIX.
2. Faz fetch do Order Book histórico no exato momento da entrada (`fetch_order_book_at`).
3. Faz fetch de trades tick-level no entorno da entrada (janela de 30s) (`fetch_trades_range`).
4. Extrai métricas reais de microestrutura:
   - Best Ask real (em centavos) vs Preço de Execução registrado
   - Volume total negociado e volume taker buy vs sell no momento da entrada
   - Taker Imbalance (pressão compradora vs vendedora)
   - Slippage real (diferença entre melhor cotação do livro e o fill do bot)
5. Cruza os dados com o resultado real do trade (Vitória vs Derrota) para responder:
   - Existia sinal de exaustão ou fluxo adverso no livro antes das derrotas?
   - O spread ou falta de liquidez no book explicam slippage ou perdas?
   - Um filtro de microestrutura baseado em Taker Imbalance teria evitado derrotas?
=============================================================================
"""

import os
import json
import sys
import time
from datetime import datetime, timezone
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    import synpath
except ImportError:
    print("[ERRO FATAL] Pacote synpath não instalado. Execute: pip install synpath")
    sys.exit(1)

JOURNAL_PATH = os.path.join(BASE_DIR, "kalshi_trading_journal.json")
if not os.path.exists(JOURNAL_PATH):
    print(f"[ERRO] Arquivo {JOURNAL_PATH} não encontrado.")
    sys.exit(1)

with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
    journal = json.load(f)

trades = journal.get("trades", [])
print("\n" + "=" * 78)
print(f"  BACKTEST DESK 6 (KALSHI BTC 15M) — MICROESTRUTURA TICK-LEVEL SYNPATH")
print(f"  Total de Trades Históricos: {len(trades)} | Win Rate Atual: {journal.get('win_rate', 0)}%")
print("=" * 78)

def parse_iso_to_ms(ts_str: str):
    """Converte ISO timestamp string (ex: '2026-10-14T14:43:56.235365+00:00') para ms UNIX."""
    if not ts_str:
        return None
    try:
        # Pega a parte YYYY-MM-DDTHH:MM:SS
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", ts_str)
        if not m:
            return None
        dt = datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            tzinfo=timezone.utc
        )
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

results = []
skipped = 0

for idx, t in enumerate(trades):
    ticker = t.get("ticker", "")
    if not ticker.startswith("KXBTC15M"):
        continue

    ts_str = t.get("timestamp", "")
    entry_ms = parse_iso_to_ms(ts_str)
    if not entry_ms:
        skipped += 1
        continue

    market_id = f"kalshi:{ticker}"
    result_raw = str(t.get("result", "")).upper()
    is_win = ("VIT" in result_raw or "WIN" in result_raw)
    entry_price = t.get("entry_price", 0) # centavos
    pnl = float(t.get("cycle_pnl", 0.0))

    print(f"\n[{idx+1:02d}/{len(trades)}] {ticker} | Entry: {entry_price}c | Result: {t.get('result', '')} | P&L: ${pnl:+.2f}")
    print(f"       Timestamp: {ts_str[:19]} UTC (ms: {entry_ms})")

    # 1. Fetch do Order Book no momento da entrada
    book_ok = False
    best_ask_c = None
    ask_depth_top5 = 0.0
    absence_reason = None

    try:
        snap = synpath.fetch_order_book_at(market_id, as_of_ms=entry_ms)
        if snap.book is not None and snap.book.asks:
            book_ok = True
            best_ask_c = round(snap.book.asks[0].price * 100, 2)
            ask_depth_top5 = sum(l.size for l in snap.book.asks[:5])
            print(f"       [Book @ Entry]: Best Ask: {best_ask_c:.1f}c | Top5 Asks Depth: {ask_depth_top5:,.0f} contracts")
        elif snap.absence_reason:
            absence_reason = snap.absence_reason
            print(f"       [Book]: Dados ausentes ({snap.absence_reason})")
    except Exception as e:
        print(f"       [Book Erro]: {str(e)[:60]}")

    # 2. Fetch de Trades Tick-Level (Janela de 30 segundos: 15s antes a 15s depois)
    trades_ok = False
    trade_count = 0
    total_vol = 0.0
    buy_vol = 0.0
    sell_vol = 0.0
    taker_imbalance = 0.0
    avg_trade_price_c = 0.0

    try:
        # Janela de 30 segundos em torno da entrada
        w_start = entry_ms - 15000
        w_end = entry_ms + 15000
        t_range = synpath.fetch_trades_range(market_id, start_ms=w_start, end_ms=w_end)
        raw_trades = t_range.trades if hasattr(t_range, "trades") else []
        trade_count = len(raw_trades)

        if trade_count > 0:
            trades_ok = True
            total_vol = sum(getattr(tr, "quantity", 1.0) for tr in raw_trades)
            buy_vol = sum(getattr(tr, "quantity", 1.0) for tr in raw_trades if getattr(tr, "side", "").lower() == "buy")
            sell_vol = total_vol - buy_vol
            taker_imbalance = (buy_vol - sell_vol) / max(total_vol, 1.0)

            prices_c = [getattr(tr, "price", 0.0) * 100 for tr in raw_trades if getattr(tr, "price", 0.0) > 0]
            avg_trade_price_c = sum(prices_c) / len(prices_c) if prices_c else 0.0

            print(f"       [Flow @ 30s]: {trade_count} ticks | Vol: {total_vol:,.0f} | Buys: {buy_vol:,.0f} | Sells: {sell_vol:,.0f} | OFI Imbalance: {taker_imbalance:+.2f}")
        else:
            print(f"       [Flow]: 0 ticks na janela imediata de 30s.")
    except Exception as e:
        print(f"       [Flow Erro]: {str(e)[:60]}")

    # Slippage real na execução
    slippage_c = (entry_price - best_ask_c) if best_ask_c is not None else None

    results.append({
        "ticker": ticker,
        "entry_ms": entry_ms,
        "is_win": is_win,
        "entry_price_c": entry_price,
        "pnl": pnl,
        "best_ask_c": best_ask_c,
        "slippage_c": slippage_c,
        "ask_depth_top5": ask_depth_top5,
        "trade_count": trade_count,
        "total_vol": total_vol,
        "buy_vol": buy_vol,
        "sell_vol": sell_vol,
        "taker_imbalance": round(taker_imbalance, 3),
        "avg_trade_price_c": round(avg_trade_price_c, 2),
        "book_ok": book_ok,
        "trades_ok": trades_ok,
        "absence_reason": absence_reason
    })

    # Respeita o rate limit amigável
    time.sleep(0.35)

print("\n" + "=" * 78)
print("  ANÁLISE ESTATÍSTICA COMPARATIVA DE MICROESTRUTURA")
print("=" * 78)

valid_samples = [r for r in results if r["book_ok"] or r["trades_ok"]]
print(f"Total de trades analisados com telemetria Synpath: {len(valid_samples)} de {len(results)}")

if not valid_samples:
    print("Sem amostras suficientes com cobertura de dados.")
    sys.exit(0)

wins = [r for r in valid_samples if r["is_win"]]
losses = [r for r in valid_samples if not r["is_win"]]

print(f"\n[A] DISTRIBUIÇÃO GERAL:")
print(f"    Vitórias Analisadas: {len(wins)} | Derrotas Analisadas: {len(losses)}")
print(f"    Taxa de Acerto na Amostra: {len(wins)/len(valid_samples)*100:.1f}%")

# Análise de Slippage
slip_wins = [r["slippage_c"] for r in wins if r["slippage_c"] is not None]
slip_losses = [r["slippage_c"] for r in losses if r["slippage_c"] is not None]

avg_slip_w = sum(slip_wins)/len(slip_wins) if slip_wins else 0.0
avg_slip_l = sum(slip_losses)/len(slip_losses) if slip_losses else 0.0

print(f"\n[B] SLIPPAGE MÉDIO NA ENTRADA (Preço Pago vs Melhor Ask no Book):")
print(f"    Vitórias:  {avg_slip_w:+.2f}c")
print(f"    Derrotas:  {avg_slip_l:+.2f}c")

# Análise de Taker Imbalance (OFI)
ti_wins = [r["taker_imbalance"] for r in wins if r["trades_ok"]]
ti_losses = [r["taker_imbalance"] for r in losses if r["trades_ok"]]

avg_ti_w = sum(ti_wins)/len(ti_wins) if ti_wins else 0.0
avg_ti_l = sum(ti_losses)/len(ti_losses) if ti_losses else 0.0

print(f"\n[C] TAKER IMBALANCE (PRESSÃO DE FLUXO AGRESSIVO NOS 30s DE ENTRADA):")
print(f"    Vitórias:  {avg_ti_w:+.3f}")
print(f"    Derrotas:  {avg_ti_l:+.3f}")

# Análise de Volume
vol_wins = [r["total_vol"] for r in wins if r["trades_ok"]]
vol_losses = [r["total_vol"] for r in losses if r["trades_ok"]]

avg_vol_w = sum(vol_wins)/len(vol_wins) if vol_wins else 0.0
avg_vol_l = sum(vol_losses)/len(vol_losses) if vol_losses else 0.0

print(f"\n[D] VOLUME MÉDIO NEGOCIADO (CONTRATOS NOS 30s):")
print(f"    Vitórias:  {avg_vol_w:,.0f} contratos")
print(f"    Derrotas:  {avg_vol_l:,.0f} contratos")

# Simulação de Filtro Hipotético: Se tivéssemos vetado quando taker_imbalance < 0 (vendedores dominando)
vetoed_trades = [r for r in valid_samples if r["trades_ok"] and r["taker_imbalance"] < -0.10]
prevented_losses = sum(1 for r in vetoed_trades if not r["is_win"])
sacrificed_wins = sum(1 for r in vetoed_trades if r["is_win"])

print(f"\n[E] SIMULAÇÃO DE GATING COM FLOW REAL SYNPATH:")
print(f"    Critério testado: Vetar se Taker Imbalance < -0.10 (pressão vendedora institucional)")
print(f"    - Derrotas evitadas com sucesso: {prevented_losses}")
print(f"    - Vitórias sacrificadas:         {sacrificed_wins}")
saved_pnl = sum(abs(r["pnl"]) for r in vetoed_trades if not r["is_win"]) - sum(r["pnl"] for r in vetoed_trades if r["is_win"])
print(f"    - Impacto financeiro líquido:    ${saved_pnl:+.2f} USDC")

# Salvar relatório JSON
out_report = os.path.join(BASE_DIR, "synpath_desk6_tick_backtest_report.json")
with open(out_report, "w", encoding="utf-8") as f:
    json.dump({
        "timestamp_analysis": datetime.now(timezone.utc).isoformat(),
        "total_trades": len(results),
        "valid_samples": len(valid_samples),
        "avg_slippage_wins": avg_slip_w,
        "avg_slippage_losses": avg_slip_l,
        "avg_taker_imbalance_wins": avg_ti_w,
        "avg_taker_imbalance_losses": avg_ti_l,
        "gating_simulation": {
            "prevented_losses": prevented_losses,
            "sacrificed_wins": sacrificed_wins,
            "net_pnl_impact": saved_pnl
        },
        "trades_detail": results
    }, f, indent=2, ensure_ascii=False)

print(f"\n[OK] Relatório completo gravado em: {out_report}\n")
