"""
=============================================================================
BACKTEST QUANTITATIVO: ÚLTIMOS 10 DIAS (BTC 5M POLYMARKET UP/DOWN)
=============================================================================
Testa o impacto de:
1. Filtro de Ruído Deadband (|Delta| >= $15)
2. Filtro de Fluxo Agressivo / Cascata de Liquidações (Taker Volume Imbalance & Spike)
3. Módulo Sweeper (BTC5MScour) aos 255s (|Delta| >= $25)
4. Estratégia Base vs Estratégia com Convicção de Liquidação
=============================================================================
"""

import urllib.request
import json
import time
from datetime import datetime

print("\n" + "=" * 80)
print("[+] BAIXANDO DADOS HISTORICOS DE 1 MINUTO DA BINANCE (ULTIMOS 10 DIAS)...")
print("=" * 80)

now_ms = int(time.time() * 1000)
# 10 dias atrás alinhado em 5 minutos
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
            print(f"  -> Coletados {len(all_1m):,} minutos de negociação...", end="\r")
            time.sleep(0.08)
    except Exception as e:
        print(f"\nErro no download: {e}")
        time.sleep(1)
        break

print(f"\n[OK] Total coletado: {len(all_1m):,} velas de 1 minuto.")

# Indexar velas por timestamp (segundos)
candles_1m = {}
for k in all_1m:
    ts_sec = int(k[0]) // 1000
    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "taker_buy_vol": float(k[9]), # Volume taker comprador
        "taker_sell_vol": float(k[5]) - float(k[9]), # Volume taker vendedor (liquidações / dumps)
        "trades": int(k[8])
    }

# Mapear todas as velas de 5 minutos (300 segundos)
all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])

# Calcular volume médio móvel de 1m para identificar picos anormais de liquidação
volumes = [candles_1m[ts]["volume"] for ts in sorted(candles_1m.keys())]
avg_vol_1m = sum(volumes) / len(volumes) if volumes else 1.0

print(f"[*] Total de ciclos de 5 minutos analisados: {len(all_5m_ts):,}")
print(f"[*] Volume medio por minuto: {avg_vol_1m:.2f} BTC\n")

# Modelos a testar:
# Modelo 1: Benchmark "Cego" (Aposta em qualquer direção na abertura)
# Modelo 2: Momentum Puro (Delta aos 135s >= $15, preço médio $0.52)
# Modelo 3: Momentum + Filtro de Cascata de Liquidações (Volume nos primeiros 2m > 1.8x média E forte desbalanço de takers)
# Modelo 4: Late-Candle Sweeper Puro (Aos 255s se Delta >= $25, compra favorito a $0.88)
# Modelo 5: Híbrido Completo (Nosso Robô: Primária com Filtro de Fluxo + Sweeper)

def simular_cenarios():
    res_base = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stakes": 0.0}
    res_deadband = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stakes": 0.0}
    res_liquidation = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stakes": 0.0}
    res_sweeper = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stakes": 0.0}
    res_hybrid = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stakes": 0.0}

    for w_ts in all_5m_ts:
        c0 = candles_1m.get(w_ts)
        c1 = candles_1m.get(w_ts + 60)
        c2 = candles_1m.get(w_ts + 120)
        c3 = candles_1m.get(w_ts + 180)
        c4 = candles_1m.get(w_ts + 240)

        # Se faltar algum minuto da vela de 5m, pula
        if not (c0 and c1 and c2 and c3 and c4):
            continue

        strike = c0["open"]
        spot_135s = c2["close"] # Fechamento do minuto 2 (180s ou ~135s no meio)
        delta_135s = spot_135s - strike
        final_spot = c4["close"]
        winner = "UP" if final_spot >= strike else "DOWN"

        # Métricas de Fluxo e Liquidações nos primeiros 2 minutos (0s a 120s)
        vol_init = c0["volume"] + c1["volume"]
        taker_buy_init = c0["taker_buy_vol"] + c1["taker_buy_vol"]
        taker_sell_init = c0["taker_sell_vol"] + c1["taker_sell_vol"]
        vol_ratio = vol_init / (2 * avg_vol_1m)
        
        # Desbalanço Taker (Pressão Agressiva / Liquidações Forçadas)
        taker_imbalance = (taker_buy_init - taker_sell_init) / vol_init if vol_init > 0 else 0.0

        # Preço estimado no Polymarket de acordo com o Delta aos 135s
        # Se delta moderado ($15 a $40), cota gira em torno de $0.52 a $0.58
        entry_price_prim = 0.54

        # -------------------------------------------------------------
        # 1. Base Momentum (Sem deadband, qualquer delta)
        # -------------------------------------------------------------
        if abs(delta_135s) >= 1.0:
            side = "UP" if delta_135s > 0 else "DOWN"
            res_base["trades"] += 1
            res_base["stakes"] += 1.0
            if side == winner:
                res_base["wins"] += 1
                res_base["pnl"] += (1.0 / entry_price_prim) - 1.0
            else:
                res_base["losses"] += 1
                res_base["pnl"] -= 1.0

        # -------------------------------------------------------------
        # 2. Deadband Filter (|Delta| >= $15)
        # -------------------------------------------------------------
        if abs(delta_135s) >= 15.0:
            side = "UP" if delta_135s > 0 else "DOWN"
            res_deadband["trades"] += 1
            res_deadband["stakes"] += 1.0
            if side == winner:
                res_deadband["wins"] += 1
                res_deadband["pnl"] += (1.0 / entry_price_prim) - 1.0
            else:
                res_deadband["losses"] += 1
                res_deadband["pnl"] -= 1.0

        # -------------------------------------------------------------
        # 3. Filtro de Liquidações / Fluxo Forte
        # Requer: |Delta| >= $20 E Pico de Volume (> 1.6x) E Taker Imbalance alinhado
        # -------------------------------------------------------------
        is_liq_cascade = (vol_ratio >= 1.5)
        if abs(delta_135s) >= 20.0 and is_liq_cascade:
            # Confirma se o desbalanço de agressão apoia a direção
            if (delta_135s > 0 and taker_imbalance > 0.15) or (delta_135s < 0 and taker_imbalance < -0.15):
                side = "UP" if delta_135s > 0 else "DOWN"
                res_liquidation["trades"] += 1
                res_liquidation["stakes"] += 1.0
                if side == winner:
                    res_liquidation["wins"] += 1
                    res_liquidation["pnl"] += (1.0 / entry_price_prim) - 1.0
                else:
                    res_liquidation["losses"] += 1
                    res_liquidation["pnl"] -= 1.0

        # -------------------------------------------------------------
        # 4. Sweeper aos 255s (Minuto 4)
        # -------------------------------------------------------------
        spot_255s = c4["open"]
        delta_255s = spot_255s - strike
        if abs(delta_255s) >= 25.0:
            side = "UP" if delta_255s > 0 else "DOWN"
            res_sweeper["trades"] += 1
            res_sweeper["stakes"] += 1.0
            # Preço da cota na reta final com delta >= 25 gira em torno de $0.86 a $0.90
            sweeper_entry_price = 0.88
            if side == winner:
                res_sweeper["wins"] += 1
                res_sweeper["pnl"] += (1.0 / sweeper_entry_price) - 1.0
            else:
                res_sweeper["losses"] += 1
                res_sweeper["pnl"] -= 1.0

        # -------------------------------------------------------------
        # 5. Híbrido (Fluxo Forte na Primária + Sweeper se primária não disparar)
        # -------------------------------------------------------------
        traded_hybrid = False
        if abs(delta_135s) >= 20.0 and is_liq_cascade and (
            (delta_135s > 0 and taker_imbalance > 0.15) or (delta_135s < 0 and taker_imbalance < -0.15)
        ):
            side = "UP" if delta_135s > 0 else "DOWN"
            res_hybrid["trades"] += 1
            res_hybrid["stakes"] += 1.0
            traded_hybrid = True
            if side == winner:
                res_hybrid["wins"] += 1
                res_hybrid["pnl"] += (1.0 / entry_price_prim) - 1.0
            else:
                res_hybrid["losses"] += 1
                res_hybrid["pnl"] -= 1.0

        if not traded_hybrid and abs(delta_255s) >= 25.0:
            side = "UP" if delta_255s > 0 else "DOWN"
            res_hybrid["trades"] += 1
            res_hybrid["stakes"] += 1.0
            sweeper_entry_price = 0.88
            if side == winner:
                res_hybrid["wins"] += 1
                res_hybrid["pnl"] += (1.0 / sweeper_entry_price) - 1.0
            else:
                res_hybrid["losses"] += 1
                res_hybrid["pnl"] -= 1.0

    return res_base, res_deadband, res_liquidation, res_sweeper, res_hybrid

b, d, l, s, h = simular_cenarios()

def fmt_row(nome, data):
    trades = data["trades"]
    wins = data["wins"]
    losses = data["losses"]
    wr = (wins / trades * 100) if trades > 0 else 0.0
    pnl = data["pnl"]
    roi = (pnl / data["stakes"] * 100) if data["stakes"] > 0 else 0.0
    print(f"| {nome:<32} | {trades:^8} | {wins:^6} | {losses:^6} | {wr:^8.1f}% | {pnl:^+10.2f} USDC | {roi:^+7.1f}% |")

print("=" * 96)
print(f"| {'ESTRATÉGIA':<32} | {'TRADES':^8} | {'VITS':^6} | {'DERR':^6} | {'WIN RATE':^9} | {'P&L LÍQUIDO':^12} | {'ROI':^8} |")
print("=" * 96)
fmt_row("1. Momentum Sem Filtro (Qualquer Delta)", b)
fmt_row("2. Filtro Deadband (|Delta| >= $15)", d)
fmt_row("3. SINAL LIQUIDAÇÃO (Pico Vol+Taker)", l)
fmt_row("4. SWEEPER FINAL (Delta 255s >= $25)", s)
fmt_row("5. HÍBRIDO (Fluxo Forte + Sweeper)", h)
print("=" * 96)
print("\nNota: Simulação com stake fixo de $1.00 por aposta sobre todas as 2.880 velas de 5m dos últimos 10 dias.")
