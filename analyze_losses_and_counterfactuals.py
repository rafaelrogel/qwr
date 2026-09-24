import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_PATH = os.path.join(BASE_DIR, "live_trading_journal.json")

with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

trades = data.get("trades", [])
print(f"Total de trades no journal: {len(trades)}")

losses = []
for idx, t in enumerate(trades):
    pnl = float(t.get("cycle_pnl", 0.0))
    res = str(t.get("result", "")).upper()
    if pnl < 0 or "DERROTA" in res or "LOSS" in res:
        t["index_in_journal"] = idx
        losses.append(t)

print(f"Total de perdas registradas: {len(losses)}")
print("\n" + "="*80)
print("LISTA DE DERROTAS E CASOS DE ESTUDO (incluindo Ciclo 135 e outros)")
print("="*80)

for l in losses:
    c = l.get("cycle_num")
    ts = l.get("timestamp", "")
    dec = l.get("decision", "")
    win = l.get("winner", "")
    res = l.get("result", "")
    strike = float(l.get("strike_K", 0.0) or 0.0)
    spot = float(l.get("final_spot", 0.0) or 0.0)
    delta_final = spot - strike if (strike > 0 and spot > 0) else 0.0
    ep = float(l.get("entry_price", 0.0) or 0.0)
    stake = float(l.get("stake", 1.0) or 1.0)
    pnl = float(l.get("cycle_pnl", 0.0) or 0.0)
    hedged = l.get("hedged", False)
    
    c_str = str(c) if c is not None else "N/A"
    print(f"Ciclo {c_str:>3} | {ts[:19]} | Dec: {dec:4} | Win: {win:4} | Res: {res:15} | Entry: ${ep:.2f} | K: ${strike:,.2f} | Final: ${spot:,.2f} (Diff: ${delta_final:+.2f}) | PnL: ${pnl:+.2f} | Hedged: {hedged}")

print("\n" + "="*80)
print("DETALHAMENTO DO CICLO 135:")
print("="*80)
c135 = [t for t in trades if t.get("cycle_num") == 135 or t.get("cycle_num") == "135"]
if c135:
    print(json.dumps(c135[0], indent=2))
else:
    print("Ciclo 135 não encontrado pelo cycle_num, procurando nos últimos 10 trades:")
    for t in trades[-10:]:
        print(t.get("cycle_num"), t.get("timestamp"), t.get("result"), t.get("cycle_pnl"))
