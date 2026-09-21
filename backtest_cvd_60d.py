"""
=============================================================================
AUDITORIA QUANTITATIVA: BACKTEST DE 60 DIAS DO CVD (CUMULATIVE VOLUME DELTA)
=============================================================================
Avalia o impacto real do CVD (Delta de Volume Acumulado de Agressão Tick a Tick)
nos últimos 60 dias (~86.400 velas de 1m / 17.280 ciclos de 5m de BTC):

Compara lado a lado:
1. Engine Sem CVD (Baseline Agressivo Moderado 240s)
2. Engine Com CVD Filter (Confirmação de Agressão Taker & Filtro de Absorção)

Campos oficiais da Binance Klines:
- k[5]: Volume Total Base (BTC)
- k[7]: Volume Total Quote (USDT)
- k[9]: Taker Buy Base Volume (BTC comprado a mercado)
- k[10]: Taker Buy Quote Volume (USDT comprado a mercado)

Delta de Volume (VD) de cada minuto:
- Taker Sell Quote = k[7] - k[10]
- CVD (USDT) = Taker Buy Quote - Taker Sell Quote = (2 * k[10]) - k[7]
=============================================================================
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import urllib.request
import json
import time
from datetime import datetime

print("\n" + "=" * 95)
print("[+] INICIANDO BACKTEST DE 60 DIAS: IMPACTO DO CVD (CUMULATIVE VOLUME DELTA)...")
print("=" * 95)

cache_file = "btc_1m_60d_futures_cache.json"
all_1m = []

if os.path.exists(cache_file):
    print(f"[*] Carregando dados de 60 dias do cache local '{cache_file}'...")
    with open(cache_file, "r") as f:
        all_1m = json.load(f)
    print(f"[OK] {len(all_1m):,} velas carregadas do cache instantaneamente.")
else:
    now_ms = int(time.time() * 1000)
    sixty_days_ms = now_ms - (60 * 24 * 3600 * 1000)
    start_ms = (sixty_days_ms // 300000) * 300000
    curr_start = start_ms

    print("[*] Baixando 60 dias de klines 1m com dados de Taker Buy/Sell (Binance Futures)...")
    batch_count = 0

    while curr_start < now_ms:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&startTime={curr_start}&limit=1500"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                klines = json.loads(r.read().decode())
                if not klines:
                    break
                all_1m.extend(klines)
                curr_start = klines[-1][0] + 60000
                batch_count += 1
                if batch_count % 10 == 0:
                    print(f"    ... {len(all_1m):,} velas de 1m baixadas ({batch_count * 1500} minutos)...")
                time.sleep(0.04)
        except Exception as e:
            # fallback para api spot se fapi falhar
            url_spot = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={curr_start}&limit=1000"
            req_spot = urllib.request.Request(url_spot, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req_spot, timeout=10) as r:
                    klines = json.loads(r.read().decode())
                    if not klines:
                        break
                    all_1m.extend(klines)
                    curr_start = klines[-1][0] + 60000
                    time.sleep(0.04)
            except Exception as e2:
                print(f"[!] Erro no download: {e} | Fallback: {e2}")
                time.sleep(1)
                continue

    with open(cache_file, "w") as f:
        json.dump(all_1m, f)
    print(f"[OK] Total de {len(all_1m):,} velas salvas no cache de 60 dias.")

print(f"[OK] Total de velas de 1m disponíveis: {len(all_1m):,}.")

candles_1m = {}
for k in all_1m:
    ts_sec = int(k[0]) // 1000
    tot_quote = float(k[7])
    taker_buy_quote = float(k[10])
    taker_sell_quote = tot_quote - taker_buy_quote
    vd_quote = taker_buy_quote - taker_sell_quote # Delta de volume líquido em USDT deste minuto

    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "quote_vol": tot_quote,
        "taker_buy_usd": taker_buy_quote,
        "taker_sell_usd": taker_sell_quote,
        "vd_usd": vd_quote,
        "tr": max(float(k[2]) - float(k[3]), abs(float(k[2]) - float(k[1])), abs(float(k[3]) - float(k[1])))
    }

all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])
print(f"[OK] Total de ciclos de 5m disponíveis: {len(all_5m_ts):,} ciclos de 5 minutos.\n")

# Pre-computar histórico de 5m
history_5m = {}
for w_ts in all_5m_ts:
    c0 = candles_1m.get(w_ts)
    c4 = candles_1m.get(w_ts + 240)
    if c0 and c4:
        tr_sum = sum(candles_1m.get(w_ts + i*60, {}).get("tr", 0) for i in range(5))
        history_5m[w_ts] = {
            "open": c0["open"],
            "close": c4["close"],
            "winner": "UP" if c4["close"] >= c0["open"] else "DOWN",
            "tr": tr_sum
        }

def get_token_price(delta_usd: float, elapsed_sec: int) -> float:
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.99, prob))

def run_60d_simulation(use_cvd_filter: bool, cvd_threshold_usd: float = 0.0):
    total_cycles = 0
    participated_cycles = 0
    skipped_cycles = 0

    wins = 0
    losses = 0

    primary_trades = 0
    primary_wins = 0
    sirmartingale_tp_trades = 0
    bonereaper_hedge_trades = 0
    sweeper_trades = 0
    sweeper_wins = 0
    streak_trades = 0
    streak_wins = 0

    cvd_blocks_at_135 = 0
    cvd_blocks_at_240 = 0
    traps_prevented_by_cvd = 0
    good_trades_filtered_by_cvd = 0

    total_stake = 0.0
    total_payout = 0.0
    total_pnl = 0.0

    peak_balance = 21.00
    current_balance = 21.00
    max_drawdown = 0.0
    daily_pnl = {}

    for idx, w_ts in enumerate(all_5m_ts):
        if idx < 16:
            continue

        c0 = candles_1m.get(w_ts)
        c1 = candles_1m.get(w_ts + 60)
        c2 = candles_1m.get(w_ts + 120)
        c3 = candles_1m.get(w_ts + 180)
        c4 = candles_1m.get(w_ts + 240)

        if not (c0 and c1 and c2 and c3 and c4):
            continue

        total_cycles += 1
        day_str = datetime.utcfromtimestamp(w_ts).strftime("%Y-%m-%d")
        if day_str not in daily_pnl:
            daily_pnl[day_str] = 0.0

        strike = c0["open"]
        final_spot = c4["close"]
        winner = "UP" if final_spot >= strike else "DOWN"

        # 1. Avaliação aos 135s (Entrada Primária)
        spot_135s = (c2["open"] + c2["close"]) / 2.0
        delta_135s = spot_135s - strike

        # Cálculo do CVD acumulado nos primeiros 135s (minutos 0, 1 e fração do minuto 2)
        cvd_135s = c0["vd_usd"] + c1["vd_usd"] + (c2["vd_usd"] * 0.5)

        prior_ts = all_5m_ts[idx-12:idx]
        hourly_atr = sum(history_5m[t]["tr"] for t in prior_ts if t in history_5m) / 12.0

        prior_4_ts = all_5m_ts[idx-4:idx]
        prior_4 = [history_5m[t] for t in prior_4_ts if t in history_5m]
        has_streak = False
        streak_reversal = None
        if len(prior_4) == 4:
            dirs = [p["winner"] for p in prior_4]
            if all(d == "UP" for d in dirs):
                cum_move = abs(prior_4[-1]["close"] - prior_4[0]["open"])
                if hourly_atr > 0 and (cum_move / hourly_atr) >= 3.0:
                    has_streak = True
                    streak_reversal = "DOWN"
            elif all(d == "DOWN" for d in dirs):
                cum_move = abs(prior_4[-1]["close"] - prior_4[0]["open"])
                if hourly_atr > 0 and (cum_move / hourly_atr) >= 3.0:
                    has_streak = True
                    streak_reversal = "UP"

        should_enter_primary = False
        target_side = None
        is_streak_trade = False

        if has_streak:
            target_side = streak_reversal
            is_streak_trade = True
            should_enter_primary = True
        elif abs(delta_135s) >= 15.0:
            target_side = "UP" if delta_135s > 0 else "DOWN"
            should_enter_primary = True

        p_up_135 = get_token_price(delta_135s, 135)
        p_down_135 = 1.0 - p_up_135
        entry_price = p_up_135 if target_side == "UP" else p_down_135

        # Filtros de Preço
        if should_enter_primary:
            if is_streak_trade and entry_price > 0.52:
                should_enter_primary = False
            elif entry_price < 0.35 or entry_price > 0.65:
                should_enter_primary = False

        # --- NOVO: FILTRO DE CVD TICK DATA (Anti-Armadilha de Absorção) ---
        if should_enter_primary and use_cvd_filter and not is_streak_trade:
            # Se queremos comprar UP, mas o CVD está negativo (vendedores agredindo mais que compradores)
            if target_side == "UP" and cvd_135s < -cvd_threshold_usd:
                cvd_blocks_at_135 += 1
                should_enter_primary = False
                if winner == "DOWN":
                    traps_prevented_by_cvd += 1
                else:
                    good_trades_filtered_by_cvd += 1
            # Se queremos comprar DOWN, mas o CVD está positivo (compradores agredindo mais)
            elif target_side == "DOWN" and cvd_135s > cvd_threshold_usd:
                cvd_blocks_at_135 += 1
                should_enter_primary = False
                if winner == "UP":
                    traps_prevented_by_cvd += 1
                else:
                    good_trades_filtered_by_cvd += 1

        has_primary = False
        primary_shares = 0.0
        sold_early_tp = False
        hedged = False
        hedge_shares = 0.0
        hedge_side = None

        cycle_stake = 0.0
        cycle_payout = 0.0

        if should_enter_primary:
            has_primary = True
            primary_trades += 1
            cycle_stake += 1.00
            primary_shares = 1.00 / entry_price
            if is_streak_trade:
                streak_trades += 1

            # Monitoramento Minuto 3 (200s)
            spot_200s = (c3["open"] + c3["close"]) / 2.0
            delta_200s = spot_200s - strike
            p_target_200s = get_token_price(delta_200s if target_side == "UP" else -delta_200s, 200)

            # SirMartingale TP
            if p_target_200s >= 0.86:
                sold_early_tp = True
                sirmartingale_tp_trades += 1
                cycle_payout += round(primary_shares * 0.86, 2)
                has_primary = False
            elif not sold_early_tp:
                favored_delta = delta_200s if target_side == "UP" else -delta_200s
                if favored_delta <= -18.0:
                    p_hedge = 1.0 - p_target_200s
                    if p_hedge <= 0.50:
                        hedged = True
                        bonereaper_hedge_trades += 1
                        cycle_stake += 1.00
                        hedge_side = "DOWN" if target_side == "UP" else "UP"
                        hedge_shares = 1.00 / p_hedge

        # 2. Módulo Sweeper aos 240s (Modo Agressivo Moderado)
        sweeper_executed = False
        sweeper_shares = 0.0
        sweeper_side = None

        if not has_primary and not hedged:
            spot_240s = c4["open"]
            delta_240s = spot_240s - strike
            
            # CVD acumulado até os 240s (minutos 0, 1, 2, 3)
            cvd_240s = c0["vd_usd"] + c1["vd_usd"] + c2["vd_usd"] + c3["vd_usd"]

            if abs(delta_240s) >= 20.0:
                sweeper_side = "UP" if delta_240s > 0 else "DOWN"
                sw_token_price = get_token_price(abs(delta_240s), 240)

                should_sweep = (0.50 <= sw_token_price <= 0.975)

                # Validação de CVD no Sweeper: Evitar varrer se houver divergência massiva contra
                if should_sweep and use_cvd_filter:
                    # Se delta está UP, mas CVD é violentamente negativo (divergência extrema de exaustão)
                    if sweeper_side == "UP" and cvd_240s < -2_000_000: # -$2M CVD contra
                        should_sweep = False
                        cvd_blocks_at_240 += 1
                    elif sweeper_side == "DOWN" and cvd_240s > 2_000_000: # +$2M CVD contra
                        should_sweep = False
                        cvd_blocks_at_240 += 1

                if should_sweep:
                    sweeper_executed = True
                    sweeper_trades += 1
                    cycle_stake += 1.00
                    sweeper_shares = 1.00 / sw_token_price

        if cycle_stake == 0.0:
            skipped_cycles += 1
            continue

        participated_cycles += 1

        if has_primary:
            if target_side == winner:
                cycle_payout += round(primary_shares * 1.00, 2)
                primary_wins += 1
                if is_streak_trade:
                    streak_wins += 1

        if hedged:
            if hedge_side == winner:
                cycle_payout += round(hedge_shares * 1.00, 2)

        if sweeper_executed:
            if sweeper_side == winner:
                cycle_payout += round(sweeper_shares * 1.00, 2)
                sweeper_wins += 1

        cycle_pnl = round(cycle_payout - cycle_stake, 2)
        total_stake += cycle_stake
        total_payout += cycle_payout
        total_pnl += cycle_pnl
        current_balance += cycle_pnl
        daily_pnl[day_str] += cycle_pnl

        if current_balance > peak_balance:
            peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown:
            max_drawdown = dd

        if cycle_pnl >= 0:
            wins += 1
        else:
            losses += 1

    overall_wr = (wins / participated_cycles * 100) if participated_cycles > 0 else 0.0
    overall_roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0.0

    return {
        "total_cycles": total_cycles,
        "participated": participated_cycles,
        "skipped": skipped_cycles,
        "wins": wins,
        "losses": losses,
        "win_rate": overall_wr,
        "total_stake": total_stake,
        "total_payout": total_payout,
        "total_pnl": total_pnl,
        "roi": overall_roi,
        "max_drawdown": max_drawdown,
        "daily_pnl": daily_pnl,
        "primary_trades": primary_trades,
        "primary_wins": primary_wins,
        "primary_wr": (primary_wins / primary_trades * 100) if primary_trades > 0 else 0,
        "sirmartingale_tp": sirmartingale_tp_trades,
        "bonereaper_hedge": bonereaper_hedge_trades,
        "sweeper_trades": sweeper_trades,
        "sweeper_wins": sweeper_wins,
        "sweeper_wr": (sweeper_wins / sweeper_trades * 100) if sweeper_trades > 0 else 0,
        "cvd_blocks_135": cvd_blocks_at_135,
        "cvd_blocks_240": cvd_blocks_at_240,
        "traps_prevented": traps_prevented_by_cvd,
        "good_trades_filtered": good_trades_filtered_by_cvd,
    }

# Simulação 1: Sem Filtro CVD (Baseline 60 Dias)
print("[*] Executando Simulação 1: Baseline SEM CVD (60 Dias / 17.280 ciclos)...")
res_no_cvd = run_60d_simulation(use_cvd_filter=False)

# Simulação 2: COM Filtro CVD Alinhado
print("[*] Executando Simulação 2: COM Filtro CVD Tick Data (60 Dias / 17.280 ciclos)...")
res_with_cvd = run_60d_simulation(use_cvd_filter=True, cvd_threshold_usd=0.0)

print("\n" + "=" * 95)
print("[*] RELATÓRIO QUANTITATIVO DEFINITIVO: 60 DIAS (SEM CVD VS COM CVD)")
print("=" * 95)
print(f"{'MÉTRICA QUANTITATIVA (60 DIAS)':<38} | {'SEM CVD (ATUAL)':<24} | {'COM CVD TICK DATA':<24}")
print("-" * 95)
print(f"{'Ciclos de 5m Analisados':<38} | {res_no_cvd['total_cycles']:,} velas            | {res_with_cvd['total_cycles']:,} velas")
print(f"{'Ciclos Operados':<38} | {res_no_cvd['participated']:,} ({res_no_cvd['participated']/res_no_cvd['total_cycles']*100:.1f}%)       | {res_with_cvd['participated']:,} ({res_with_cvd['participated']/res_with_cvd['total_cycles']*100:.1f}%)")
print(f"{'Ciclos Filtrados (Preservou)':<38} | {res_no_cvd['skipped']:,} ({res_no_cvd['skipped']/res_no_cvd['total_cycles']*100:.1f}%)       | {res_with_cvd['skipped']:,} ({res_with_cvd['skipped']/res_with_cvd['total_cycles']*100:.1f}%)")
print(f"{'Taxa de Acerto Global':<38} | {res_no_cvd['win_rate']:.1f}% ({res_no_cvd['wins']}V / {res_no_cvd['losses']}D)       | {res_with_cvd['win_rate']:.1f}% ({res_with_cvd['wins']}V / {res_with_cvd['losses']}D)")
print(f"{'Volume Total Apostado':<38} | ${res_no_cvd['total_stake']:,.2f} USDC            | ${res_with_cvd['total_stake']:,.2f} USDC")
print(f"{'Payouts Resgatados':<38} | ${res_no_cvd['total_payout']:,.2f} USDC            | ${res_with_cvd['total_payout']:,.2f} USDC")
print(f"{'LUCRO LÍQUIDO (P&L)':<38} | {res_no_cvd['total_pnl']:+,.2f} USDC            | {res_with_cvd['total_pnl']:+,.2f} USDC")
print(f"{'Retorno s/ Volume (ROI)':<38} | {res_no_cvd['roi']:+.2f}%                  | {res_with_cvd['roi']:+.2f}%")
print(f"{'Retorno s/ Banca Base ($21)':<38} | {(res_no_cvd['total_pnl']/21*100):+.1f}%                 | {(res_with_cvd['total_pnl']/21*100):+.1f}%")
print(f"{'Drawdown Máximo':<38} | ${res_no_cvd['max_drawdown']:.2f} USDC             | ${res_with_cvd['max_drawdown']:.2f} USDC")
print("-" * 95)
print(f"{'Entrada Primária (135s)':<38} | {res_no_cvd['primary_trades']} trades (WR: {res_no_cvd['primary_wr']:.1f}%)   | {res_with_cvd['primary_trades']} trades (WR: {res_with_cvd['primary_wr']:.1f}%)")
print(f"{'Entrada Sweeper (240s)':<38} | {res_no_cvd['sweeper_trades']} trades (WR: {res_no_cvd['sweeper_wr']:.1f}%) | {res_with_cvd['sweeper_trades']} trades (WR: {res_with_cvd['sweeper_wr']:.1f}%)")
print("-" * 95)
print(f"{'Filtros Acionados pelo CVD':<38} | {'N/A':<24} | {res_with_cvd['cvd_blocks_135'] + res_with_cvd['cvd_blocks_240']} bloqueios")
print(f"{' - Armadilhas Evitadas pelo CVD':<38} | {'N/A':<24} | {res_with_cvd['traps_prevented']} armadilhas evitadas!")
print(f"{' - Trades Positivos Descartados':<38} | {'N/A':<24} | {res_with_cvd['good_trades_filtered']} trades")
print("=" * 95)

# Salvar resultados
with open("backtest_cvd_60d_results.json", "w") as f:
    json.dump({"sem_cvd": res_no_cvd, "com_cvd": res_with_cvd}, f, indent=2)
print("[OK] Resultados salvos em 'backtest_cvd_60d_results.json'.\n")
