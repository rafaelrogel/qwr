import json

with open("live_trading_journal.json", "r", encoding="utf-8") as f:
    d = json.load(f)

for t in d["trades"]:
    if t["cycle"] == 62:
        t["winner"] = "UP"
        t["winner_source"] = "CHAINLINK_ORACLE"
        t["result"] = "VITORIA (SCOUR SWEEPER)"
        t["scour_payout"] = 1.16
        t["total_payout"] = 1.16
        t["cycle_pnl"] = 0.16
        t["balance"] = 14.27

# Recalcular totais
wins = sum(1 for t in d["trades"] if t.get("cycle_pnl", 0) > 0)
losses = sum(1 for t in d["trades"] if t.get("cycle_pnl", 0) < 0)
d["wins"] = wins
d["losses"] = losses
d["win_rate"] = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
d["total_pnl"] = round(sum(t.get("cycle_pnl", 0) for t in d["trades"]), 2)

with open("live_trading_journal.json", "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2)

print(f"Atualizado! Wins: {wins} | Losses: {losses} | Win Rate: {d['win_rate']}% | P&L: {d['total_pnl']}")
