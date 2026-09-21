"""
=============================================================================
BACKTEST QUANTITATIVO: STREAK SNAPPER (MOON DEV INSIGHT 2) - ÚLTIMOS 10 DIAS
=============================================================================
Testa a hipótese estatística:
Após 3 ou 4+ velas consecutivas na mesma direção (ex: UUUU ou DDDD) com
esticamento de preço superior ao ATR horário, a próxima vela reverte?

Período: 10 a 20 de Setembro de 2026 (2.881 ciclos de 5m de BTC/USDT)
=============================================================================
"""

import urllib.request
import json
import time

print("\n" + "=" * 80)
print("[+] BAIXANDO DADOS HISTORICOS DE 5 MINUTOS (ULTIMOS 10 DIAS)...")
print("=" * 80)

now_ms = int(time.time() * 1000)
ten_days_ms = now_ms - (10 * 24 * 3600 * 1000)
start_ms = (ten_days_ms // 300000) * 300000

all_5m = []
curr_start = start_ms

while curr_start < now_ms:
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={curr_start}&limit=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            klines = json.loads(r.read().decode())
            if not klines:
                break
            all_5m.extend(klines)
            curr_start = klines[-1][0] + 300000
            print(f"  -> Coletadas {len(all_5m):,} velas de 5m...", end="\r")
            time.sleep(0.08)
    except Exception as e:
        print(f"\nErro no download: {e}")
        break

print(f"\n[OK] Base pronta: {len(all_5m):,} velas de 5 minutos.")

# Estruturar velas de 5m
candles = []
for k in all_5m:
    open_p = float(k[1])
    high_p = float(k[2])
    low_p = float(k[3])
    close_p = float(k[4])
    tr = max(high_p - low_p, abs(high_p - open_p), abs(low_p - open_p))
    winner = "UP" if close_p >= open_p else "DOWN"
    candles.append({
        "ts": int(k[0]) // 1000,
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": close_p,
        "tr": tr,
        "winner": winner
    })

print(f"[*] Total de velas prontas para analise: {len(candles):,}\n")


def run_streak_snapper_backtest(streak_len: int = 4, min_atr_mult: float = 3.0, entry_price: float = 0.50):
    """
    Simula a estratégia Streak Snapper:
    - streak_len: Quantidade de velas consecutivas na mesma direção (ex: 3 ou 4)
    - min_atr_mult: Multiplicador de esticamento relativo ao ATR horário (12 velas de 5m)
    - entry_price: Preço pago na cota de reversão ($0.50 a $0.52)
    """
    trades = 0
    wins = 0
    losses = 0
    total_pnl = 0.0
    total_spent = 0.0

    # Precisamos de pelo menos 12 velas antes para calcular o ATR horário (1 hora)
    for i in range(12 + streak_len, len(candles)):
        # 1. Calcular ATR de 1 hora (média dos True Ranges das 12 velas anteriores)
        recent_12 = candles[i - streak_len - 12 : i - streak_len]
        hourly_atr = sum(c["tr"] for c in recent_12) / 12.0
        if hourly_atr <= 0:
            continue

        # 2. Verificar se as últimas `streak_len` velas foram na mesma direção
        streak_candles = candles[i - streak_len : i]
        streak_winners = [c["winner"] for c in streak_candles]

        all_up = all(w == "UP" for w in streak_winners)
        all_down = all(w == "DOWN" for w in streak_winners)

        if not (all_up or all_down):
            continue # Sem sequência pura

        # 3. Medir o esticamento acumulado do movimento (|Preço Final - Preço Inicial|)
        start_price = streak_candles[0]["open"]
        end_price = streak_candles[-1]["close"]
        cum_move = abs(end_price - start_price)

        # 4. Filtro de Esticamento (Stretch Condition)
        if cum_move < (min_atr_mult * hourly_atr):
            continue # Movimento pequeno / consolidação, sem esticamento suficiente

        # 5. Entrada na Reversão (Fade)
        # Se a sequência foi UP, aposta DOWN. Se foi DOWN, aposta UP.
        reversal_side = "DOWN" if all_up else "UP"
        actual_winner = candles[i]["winner"]

        trades += 1
        total_spent += 1.0 # Stake fixo de $1.00

        if reversal_side == actual_winner:
            wins += 1
            payout = 1.0 / entry_price
            total_pnl += (payout - 1.0)
        else:
            losses += 1
            total_pnl -= 1.0

    wr = (wins / trades * 100) if trades > 0 else 0.0
    roi = (total_pnl / total_spent * 100) if total_spent > 0 else 0.0
    return {
        "streak": streak_len,
        "atr_mult": min_atr_mult,
        "entry_price": entry_price,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "pnl": total_pnl,
        "roi": roi
    }


print("=" * 100)
print(f"| {'CONFIGURAÇÃO DO STREAK SNAPPER':<40} | {'TRADES':^8} | {'VITS':^6} | {'DERR':^6} | {'WIN RATE':^9} | {'P&L LÍQUIDO':^12} | {'ROI':^7} |")
print("=" * 100)

scenarios = [
    # Fading Cego (Sem filtro de esticamento ATR)
    (3, 0.0, 0.50, "1. Streak 3 Cego (Sem Filtro ATR) @ $0.50"),
    (4, 0.0, 0.50, "2. Streak 4 Cego (Sem Filtro ATR) @ $0.50"),
    (5, 0.0, 0.50, "3. Streak 5 Cego (Sem Filtro ATR) @ $0.50"),
    
    # Fading com Esticamento Leve (1.5x a 2.0x ATR)
    (3, 2.0, 0.50, "4. Streak 3 + Esticamento >= 2.0x ATR @ $0.50"),
    (4, 2.0, 0.50, "5. Streak 4 + Esticamento >= 2.0x ATR @ $0.50"),
    
    # O Setup Oficial do Moon Dev (4+ Streaks com 3.0x ATR)
    (4, 3.0, 0.50, "6. Moon Dev Oficial: Streak 4 + Esticamento >= 3.0x @ $0.50"),
    (4, 3.0, 0.52, "7. Moon Dev Oficial: Streak 4 + Esticamento >= 3.0x @ $0.52"),
    (3, 3.0, 0.50, "8. Streak 3 + Esticamento Extremo >= 3.0x @ $0.50"),
]

for s, atr, p, label in scenarios:
    res = run_streak_snapper_backtest(s, atr, p)
    print(f"| {label:<40} | {res['trades']:^8} | {res['wins']:^6} | {res['losses']:^6} | {res['win_rate']:^8.1f}% | {res['pnl']:^+10.2f} USDC | {res['roi']:^+6.1f}% |")

print("=" * 100)
print("Nota: Simulação com stake fixo de $1.00 por trade nas 2.881 velas de 5m dos últimos 10 dias.")
