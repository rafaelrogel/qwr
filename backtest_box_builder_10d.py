"""
=============================================================================
BACKTEST: BOX BUILDER (ARBITRAGEM DE CAIXA EM BTC 5M - ÚLTIMOS 10 DIAS)
=============================================================================
Analisa todas as 2.881 velas de 5m (10 a 20 de setembro) para testar:
1. Com que frequência o Bitcoin oscila para AMBOS os lados nos primeiros 120s?
2. Quantas vezes conseguimos fechar a caixa completa (UP + DOWN <= $0.92 ou $0.94)?
3. Qual é o impacto do "Risco de Perna Única" (Legging Risk) quando o mercado anda em tendência e só preenche um dos lados?
=============================================================================
"""

import urllib.request
import json
import time

print("\n" + "=" * 80)
print("[+] BAIXANDO BASE DE DADOS DE 1M DA BINANCE (ULTIMOS 10 DIAS)...")
print("=" * 80)

now_ms = int(time.time() * 1000)
ten_days_ms = now_ms - (10 * 24 * 3600 * 1000)
start_ms = (ten_days_ms // 300000) * 300000

all_1m = []
curr_start = start_ms

while curr_start < now_ms:
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={curr_start}&limit=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            klines = json.loads(r.read().decode())
            if not klines:
                break
            all_1m.extend(klines)
            curr_start = klines[-1][0] + 60000
            print(f"  -> Coletando dados: {len(all_1m):,} minutos...", end="\r")
            time.sleep(0.08)
    except Exception as e:
        print(f"\nErro no download: {e}")
        break

print(f"\n[OK] Base pronta: {len(all_1m):,} velas de 1 minuto.")

candles_1m = {}
for k in all_1m:
    ts_sec = int(k[0]) // 1000
    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5])
    }

all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])
print(f"[*] Total de ciclos de 5 minutos avaliados: {len(all_5m_ts):,}\n")


def delta_to_price(delta_usd: float) -> tuple:
    """
    Modela o preco teorico do livro de ofertas no Polymarket no inicio da vela (0 a 120s):
    - Em Delta = 0: preco = $0.50 / $0.50
    - Cada $10 de delta desloca a probabilidade em aprox 0.05 (sensibilidade empírica da CLOB)
    """
    prob_up = 0.50 + (delta_usd / 200.0)
    prob_up = max(0.05, min(0.95, prob_up))
    prob_down = 1.0 - prob_up
    return prob_up, prob_down


def test_box_builder(bid_price: float = 0.46, exit_unhedged: bool = True):
    """
    bid_price: Preço limite em cada lado (ex: $0.46 cada -> Par custa $0.92, lucro garantido de $0.08)
    exit_unhedged: Se True, corta a perna solitária aos 120s se a outra não preencher. Se False, segura até o fechamento.
    """
    both_filled = 0
    up_only_filled = 0
    down_only_filled = 0
    neither_filled = 0

    total_pnl = 0.0
    total_spent = 0.0

    pair_cost = bid_price * 2.0
    guaranteed_payout = 1.00
    guaranteed_profit = guaranteed_payout - pair_cost

    for w_ts in all_5m_ts:
        c0 = candles_1m.get(w_ts)
        c1 = candles_1m.get(w_ts + 60)
        c2 = candles_1m.get(w_ts + 120)
        c3 = candles_1m.get(w_ts + 180)
        c4 = candles_1m.get(w_ts + 240)

        if not (c0 and c1 and c2 and c3 and c4):
            continue

        strike = c0["open"]
        final_spot = c4["close"]
        winner = "UP" if final_spot >= strike else "DOWN"

        # Excursão máxima e mínima nos primeiros 2 minutos (0s a 120s)
        high_2m = max(c0["high"], c1["high"])
        low_2m = min(c0["low"], c1["low"])

        max_delta_pos = high_2m - strike
        max_delta_neg = low_2m - strike

        # Para comprar UP a bid_price (ex: $0.46), o BTC precisa ter caído o suficiente
        # Para comprar DOWN a bid_price (ex: $0.46), o BTC precisa ter subido o suficiente
        # Na CLOB de 5m, para a cota de UP atingir $0.46, o BTC precisa atingir Delta <= -$8.0
        # Para a cota de DOWN atingir $0.46, o BTC precisa atingir Delta >= +$8.0
        delta_threshold = (0.50 - bid_price) * 200.0 # Ex: (0.50 - 0.46)*200 = $8.0

        up_filled = (max_delta_neg <= -delta_threshold)
        down_filled = (max_delta_pos >= delta_threshold)

        if up_filled and down_filled:
            # SUCESSO ABSOLUTO: Ambos preenchidos! Caixa travada!
            both_filled += 1
            total_spent += pair_cost
            total_pnl += guaranteed_profit

        elif up_filled and not down_filled:
            # Perna solitária: Comprou UP mas não comprou DOWN
            up_only_filled += 1
            total_spent += bid_price
            if exit_unhedged:
                # Vende no mercado aos 120s com base no preço do spot aos 120s
                spot_120s = c1["close"]
                p_up_120, _ = delta_to_price(spot_120s - strike)
                # Paga spread/slippage de $0.02 na saída
                exit_price = max(0.05, p_up_120 - 0.02)
                total_pnl += (exit_price - bid_price)
            else:
                # Segura até o final
                payout = 1.0 if winner == "UP" else 0.0
                total_pnl += (payout - bid_price)

        elif down_filled and not up_filled:
            # Perna solitária: Comprou DOWN mas não comprou UP
            down_only_filled += 1
            total_spent += bid_price
            if exit_unhedged:
                spot_120s = c1["close"]
                _, p_down_120 = delta_to_price(spot_120s - strike)
                exit_price = max(0.05, p_down_120 - 0.02)
                total_pnl += (exit_price - bid_price)
            else:
                payout = 1.0 if winner == "DOWN" else 0.0
                total_pnl += (payout - bid_price)

        else:
            # Nenhum preenchido (mercado ficou parado com delta < $8)
            neither_filled += 1

    total_ops = both_filled + up_only_filled + down_only_filled
    roi = (total_pnl / total_spent * 100) if total_spent > 0 else 0.0
    both_pct = (both_filled / total_ops * 100) if total_ops > 0 else 0.0
    single_pct = ((up_only_filled + down_only_filled) / total_ops * 100) if total_ops > 0 else 0.0

    return {
        "bid": bid_price,
        "exit_unhedged": exit_unhedged,
        "both_filled": both_filled,
        "both_pct": both_pct,
        "single_filled": up_only_filled + down_only_filled,
        "single_pct": single_pct,
        "neither": neither_filled,
        "total_ops": total_ops,
        "pnl": total_pnl,
        "spent": total_spent,
        "roi": roi
    }

print("=" * 96)
print("TESTANDO DIFERENTES CONFIGURAÇÕES DO BOX BUILDER (ÚLTIMOS 10 DIAS)")
print("=" * 96)

configs = [
    (0.47, True, "Bid $0.47 cada (Par $0.94 -> Lucro +$0.06) | Stop aos 120s"),
    (0.47, False, "Bid $0.47 cada (Par $0.94 -> Lucro +$0.06) | Hold ate o fim"),
    (0.46, True, "Bid $0.46 cada (Par $0.92 -> Lucro +$0.08) | Stop aos 120s"),
    (0.46, False, "Bid $0.46 cada (Par $0.92 -> Lucro +$0.08) | Hold ate o fim"),
    (0.45, True, "Bid $0.45 cada (Par $0.90 -> Lucro +$0.10) | Stop aos 120s"),
    (0.45, False, "Bid $0.45 cada (Par $0.90 -> Lucro +$0.10) | Hold ate o fim"),
]

print(f"| {'CONFIGURAÇÃO':<44} | {'PAR FECHADO':^13} | {'PERNA ÚNICA':^13} | {'P&L LÍQUIDO':^12} | {'ROI':^7} |")
print("=" * 96)

for bid, ext, desc in configs:
    r = test_box_builder(bid, ext)
    desc_short = desc[:44]
    both_str = f"{r['both_filled']} ({r['both_pct']:.1f}%)"
    single_str = f"{r['single_filled']} ({r['single_pct']:.1f}%)"
    pnl_str = f"{r['pnl']:+.2f} USDC"
    roi_str = f"{r['roi']:+.1f}%"
    print(f"| {desc_short:<44} | {both_str:^13} | {single_str:^13} | {pnl_str:^12} | {roi_str:^7} |")

print("=" * 96)
