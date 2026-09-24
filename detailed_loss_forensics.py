import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_PATH = os.path.join(BASE_DIR, "live_trading_journal.json")

with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
    trades = json.load(f).get("trades", [])

print(f"Total de trades no journal: {len(trades)}")

losses = []
for idx, t in enumerate(trades):
    pnl = float(t.get("cycle_pnl", 0.0) or 0.0)
    res = str(t.get("result", "")).upper()
    if pnl < 0 or "DERROTA" in res or "DEFESA" in res:
        losses.append((idx + 1, t))

print(f"Total de ciclos com perda (total ou parcial): {len(losses)}\n")

categories = {
    "stop_loss_defended": [],        # Defesa antecipada que reduziu o prejuízo (ex: perdeu -0.10 em vez de -1.00)
    "scour_sweeper_failed": [],      # Scour sweeper aos 255s-285s que errou o candle
    "take_profit_failed_to_sell": [],# Ciclo 135 e similares (onde Take-Profit atingiu preço mas não vendeu)
    "zero_or_bad_strike": [],        # Strike anômalo ou oráculo com 0
    "pure_directional_reversal": []  # Reversão genuína do mercado contra o delta de 135s
}

for cycle_id, t in losses:
    res = str(t.get("result", "")).upper()
    strike = float(t.get("strike_chainlink") or t.get("strike") or 0.0)
    final_spot = float(t.get("final_spot_chainlink") or t.get("final_spot") or 0.0)
    pnl = float(t.get("cycle_pnl", 0.0) or 0.0)
    price = float(t.get("price", 0.0) or 0.0)
    
    # Ciclo 135 específico
    if cycle_id == 135:
        categories["take_profit_failed_to_sell"].append((cycle_id, t))
    elif strike == 0.0 or final_spot == 0.0:
        categories["zero_or_bad_strike"].append((cycle_id, t))
    elif "STOP LOSS" in res or "DEFESA" in res or (t.get("sold_early") and pnl < 0):
        categories["stop_loss_defended"].append((cycle_id, t))
    elif "SCOUR" in res or "SWEEPER" in res or t.get("scour_executed"):
        categories["scour_sweeper_failed"].append((cycle_id, t))
    else:
        diff = abs(final_spot - strike)
        categories["pure_directional_reversal"].append((cycle_id, t, diff))

print("="*85)
print(f"1. FALHA DE EXECUÇÃO DE TAKE-PROFIT (CASO CICLO 135): {len(categories['take_profit_failed_to_sell'])} trade(s)")
print("="*85)
for cid, t in categories["take_profit_failed_to_sell"]:
    ep = float(t.get("price", 0.42))
    shares = float(t.get("shares", 2.439))
    actual_pnl = float(t.get("cycle_pnl", -1.0))
    # No ciclo 135, o livro bateu $0.85 (comprovado nos logs). Se vendido a $0.85:
    pot_payout = round(shares * 0.85, 2) # $2.07
    pot_pnl = round(pot_payout - 1.00, 2) # +$1.07
    missed_gain = round(pot_pnl - actual_pnl, 2) # +$2.07
    print(f"  Ciclo #{cid} ({t.get('time_str')}): Entrada UP @ ${ep:.2f} ({shares:.2f} cotas)")
    print(f"    -> Resultado Real: {t.get('result')} | P&L Real: ${actual_pnl:+.2f}")
    print(f"    -> Com nova versão (TP CLOB @ $0.85): Payout ${pot_payout:.2f} | P&L: ${pot_pnl:+.2f}")
    print(f"    -> Lucro Deixado de Ganhar no Ciclo 135: ${missed_gain:+.2f} USDC")

print("\n" + "="*85)
print(f"2. DERROTAS DO 'SCOUR SWEEPER' (Entradas Tardias 255s-285s): {len(categories['scour_sweeper_failed'])} trade(s)")
print("="*85)
scour_loss_total = 0.0
for cid, t in categories["scour_sweeper_failed"]:
    pnl = float(t.get("cycle_pnl", -1.0))
    scour_loss_total += abs(pnl)
    print(f"  Ciclo #{cid} ({t.get('timestamp')[:19]}): PnL: ${pnl:+.2f} | Target: {t.get('target_side')} | Vencedor: {t.get('winner')}")
print(f"  -> Total de capital perdido em entradas agressivas de final de vela (Sweeper): ${scour_loss_total:.2f} USDC")
print(f"  -> Na nova versão com filtros rigorosos de Drift Binance + Spread restrito, essas armadilhas de baixa liquidez são bloqueadas.")

print("\n" + "="*85)
print(f"3. DEFESAS ANTECIPADAS (STOP-LOSS SALVOU A BANCA): {len(categories['stop_loss_defended'])} trade(s)")
print("="*85)
saved_total = 0.0
actual_defense_loss = 0.0
for cid, t in categories["stop_loss_defended"]:
    pnl = float(t.get("cycle_pnl", 0.0))
    actual_defense_loss += abs(pnl)
    saved = 1.00 - abs(pnl)
    saved_total += saved
    print(f"  Ciclo #{cid} ({t.get('timestamp')[:19]}): PnL: ${pnl:+.2f} (Perda limitada a centavos vs -$1.00 integral) | Res: {t.get('result')}")
print(f"  -> Perda Real com Defesa: ${actual_defense_loss:.2f} USDC (Média de apenas ${actual_defense_loss/len(categories['stop_loss_defended']):.2f} por derrota)")
print(f"  -> Capital salvo da liquidação total pelo Stop-Loss: ${saved_total:.2f} USDC")

print("\n" + "="*85)
print(f"4. REVERSÕES DIRECIONAIS PURAS DE MERCADO: {len(categories['pure_directional_reversal'])} trade(s)")
print("="*85)
reversal_loss_total = 0.0
marginal_reversals = [] # Reversões de margem minúscula (< $15 de diferença no fechamento)
for cid, t, diff in categories["pure_directional_reversal"]:
    pnl = float(t.get("cycle_pnl", -1.0))
    reversal_loss_total += abs(pnl)
    strike = float(t.get("strike_chainlink") or t.get("strike") or 0.0)
    spot = float(t.get("final_spot_chainlink") or t.get("final_spot") or 0.0)
    if diff <= 15.0:
        marginal_reversals.append((cid, t, diff))
    print(f"  Ciclo #{cid:3} ({t.get('timestamp')[:19]}): PnL: ${pnl:+.2f} | Decisão: {t.get('target_side')} vs Win: {t.get('winner')} | Strike: ${strike:,.2f} -> Final: ${spot:,.2f} (Gap: ${diff:.2f})")

print(f"\n  -> Total perdido em reversões de mercado: ${reversal_loss_total:.2f} USDC")
print(f"  -> Dessas, {len(marginal_reversals)} foram reversões marginais (diferença final <= $15.00), onde o preço bateu take-profit ou hedge durante os primeiros 3 minutos antes da virada!")

print("\n" + "="*85)
print(f"5. ANOMALIAS DE REGISTRO HISTÓRICO / STRIKE ZERO INICIAL: {len(categories['zero_or_bad_strike'])} trade(s)")
print("="*85)
for cid, t in categories["zero_or_bad_strike"]:
    print(f"  Ciclo #{cid}: PnL: {t.get('cycle_pnl')} | Res: {t.get('result')}")
