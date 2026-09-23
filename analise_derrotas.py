import json
import sys
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

with open('live_trading_journal.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

trades = data.get('trades', [])
print(f"Total trades no diário: {len(trades)}")
print(f"Saldo atual no cabeçalho: ${data.get('current_balance', 'N/A')} USDC")
print(f"Vitórias globais: {data.get('wins', 0)} | Derrotas: {data.get('losses', 0)} (WR: {data.get('win_rate', 0)}%)")

recent = []
for t in trades:
    ts_str = t.get('timestamp', '')
    if ts_str:
        try:
            dt = datetime.fromisoformat(ts_str.replace('Z', ''))
            recent.append((dt, t))
        except Exception:
            pass

recent.sort(key=lambda x: x[0])

# Pegar as operações mais recentes (últimas 25)
print("\n" + "="*110)
print("ÚLTIMAS OPERAÇÕES REGISTRADAS NO DIÁRIO:")
print("="*110)

cutoff = datetime(2026, 9, 22, 18, 0, 0)
ultimas_16h = [x for x in recent if x[0] >= cutoff]
if len(ultimas_16h) == 0:
    ultimas_16h = recent[-15:]

vitorias = 0
derrotas = 0
pnl_periodo = 0.0

for dt, t in ultimas_16h:
    cycle = t.get('cycle', '')
    res = t.get('result', '')
    side = t.get('target_side', '')
    winner = t.get('winner', '')
    pnl = float(t.get('cycle_pnl', 0.0) or 0.0)
    strike = float(t.get('strike_chainlink', t.get('strike', 0)) or 0)
    final = float(t.get('final_spot_chainlink', t.get('final_spot', 0)) or 0)
    price = float(t.get('price', 0) or 0)
    src = t.get('winner_source', '')
    tp = t.get('sold_early', False)
    diff = final - strike
    pnl_periodo += pnl
    if "VITORIA" in res.upper():
        vitorias += 1
    else:
        derrotas += 1

    time_str = dt.strftime("%d/%m %H:%M:%S")
    status_icon = "🟢" if "VITORIA" in res.upper() else "🔴"
    print(f"{status_icon} Ciclo #{cycle:<3} | {time_str} | Side: {side:<4} | Vencedor: {winner:<4} | {res:<12} | P&L: {pnl:+5.2f} | K: {strike:.2f} -> F: {final:.2f} (d={diff:+6.2f}) | Preço: ${price:.3f} | TP: {tp} | Fonte: {src}")

print("="*110)
print(f"RESUMO DO PERÍODO SELECIONADO:")
print(f"Total de Trades: {len(ultimas_16h)} | Vitórias: {vitorias} | Derrotas: {derrotas} | Win Rate: {(vitorias/len(ultimas_16h)*100):.1f}%")
print(f"P&L no Período: {pnl_periodo:+.2f} USDC")
print("="*110)

# Análise profunda das derrotas
print("\n" + "="*110)
print("ANÁLISE DETALHADA DE CADA DERROTA NO PERÍODO:")
print("="*110)
for dt, t in ultimas_16h:
    res = t.get('result', '')
    if "DERROTA" in res.upper() or float(t.get('cycle_pnl', 0)) < 0:
        cycle = t.get('cycle', '')
        side = t.get('target_side', '')
        winner = t.get('winner', '')
        pnl = float(t.get('cycle_pnl', 0.0) or 0.0)
        strike = float(t.get('strike_chainlink', t.get('strike', 0)) or 0)
        final = float(t.get('final_spot_chainlink', t.get('final_spot', 0)) or 0)
        price = float(t.get('price', 0) or 0)
        src = t.get('winner_source', '')
        tp = t.get('sold_early', False)
        diff = final - strike
        
        print(f"\n[❌ DERROTA CICLO #{cycle}] {dt.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"   - Aposta enviada: {side} a ${price:.3f}")
        print(f"   - Strike inicial: ${strike:,.2f}")
        print(f"   - Fechamento:     ${final:,.2f} (Delta final: ${diff:+,.2f})")
        print(f"   - Vencedor oficial: {winner} (Fonte: {src})")
        print(f"   - Take-Profit acionado: {tp}")
        print(f"   - P&L do Ciclo: {pnl:+.2f} USDC")
        
        # Diagnóstico
        if abs(diff) < 5.0:
            diag = "MARGEM MILIMÉTRICA (<$5): O preço fechou quase colado no strike. Variação pura de microestrutura / arredondamento."
        elif (side == "UP" and diff < 0) or (side == "DOWN" and diff > 0):
            diag = f"REVERSÃO TOTAL: O mercado virou contra a aposta na segunda metade da vela (delta foi {diff:+,.2f})."
        elif (side == winner) and ("OFFICIAL" in src or pnl < 0):
            diag = "DIVERGÊNCIA ORÁCULO vs RESOLUÇÃO POLYMARKET: O fechamento local Chainlink sugeria vitória, mas a API oficial da Polymarket resolveu contra."
        else:
            diag = "VOLATILIDADE CONTRÁRIA: Movimento adverso no fechamento."
        print(f"   - Diagnóstico: {diag}")
