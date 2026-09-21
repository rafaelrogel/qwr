"""
=============================================================================
AUDITORIA QUANTITATIVA: BACKTEST EXAUSTIVO DE 60 DIAS DO CÓDIGO ATUAL EM PRODUÇÃO
=============================================================================
Mapeamento 1:1 de live_trader_5m.py:
1. Entrada Primária aos 135s (Deadband $15, Drift Binance, Faixa $0.35-$0.65)
2. Filtro CVD Tick Data (Anti-Bull/Bear Trap aos 135s)
3. SirMartingale Take-Profit aos 170s+ (Venda a mercado se cota >= $0.86)
4. Bonereaper Hedge Inteligente (Apenas se cota oposta <= $0.50)
5. Stop-Loss de Emergência (Se hedge rejeitado > $0.50 e bid >= $0.15, vende cota primária)
6. BTC5MScour Sweeper aos 240s (Modo Agressivo Moderado: |Delta| >= $20, Faixa $0.50-$0.975)
7. Filtro CVD no Sweeper (Bloqueia varredura se houver dump/pump institucional contrária >= $1.5M)
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
import math

print("\n" + "=" * 95)
print("[+] INICIANDO BACKTEST DE 60 DIAS: MOTOR COMPLETO ATUALIZADO (CÓDIGO ATUAL)...")
print("=" * 95)

cache_file = "btc_1m_60d_futures_cache.json"
if not os.path.exists(cache_file):
    print(f"[!] Cache '{cache_file}' não encontrado!")
    sys.exit(1)

with open(cache_file, "r") as f:
    all_1m = json.load(f)

print(f"[OK] Total de velas de 1m carregadas: {len(all_1m):,}.")

candles_1m = {}
for k in all_1m:
    ts_sec = int(k[0]) // 1000
    tot_quote = float(k[7])
    taker_buy_quote = float(k[10])
    taker_sell_quote = tot_quote - taker_buy_quote
    vd_quote = taker_buy_quote - taker_sell_quote # Net CVD em USDT

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

def run_backtest_simulation(
    name: str,
    use_cvd_primary: bool,
    use_cvd_sweeper: bool,
    use_emergency_sl: bool,
    sweeper_cvd_threshold: float = 1_500_000.0
):
    total_cycles = 0
    participated_cycles = 0
    skipped_cycles = 0

    wins = 0
    losses = 0

    primary_trades = 0
    primary_wins = 0
    sirmartingale_tp_trades = 0
    bonereaper_hedge_trades = 0
    emergency_sl_trades = 0
    emergency_sl_rescued = 0.0
    sweeper_trades = 0
    sweeper_wins = 0
    streak_trades = 0
    streak_wins = 0

    cvd_blocks_primary = 0
    cvd_blocks_sweeper = 0
    traps_prevented_by_cvd = 0
    good_trades_filtered = 0

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
        b_drift_135s = delta_135s # Simulação de spot drift Binance

        # CVD acumulado aos 135s (min 0, 1 e 50% de 2)
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
            # Confirmação de Drift Binance
            if (target_side == "UP" and b_drift_135s >= -5.0) or (target_side == "DOWN" and b_drift_135s <= 5.0):
                should_enter_primary = True

        p_up_135 = get_token_price(delta_135s, 135)
        p_down_135 = 1.0 - p_up_135
        entry_price = p_up_135 if target_side == "UP" else p_down_135

        # Filtros de Faixa de Preço Saudável ($0.35 a $0.65)
        if should_enter_primary:
            if is_streak_trade and entry_price > 0.52:
                should_enter_primary = False
            elif entry_price < 0.35 or entry_price > 0.65:
                should_enter_primary = False

        # REGRA 4: Filtro de CVD Tick Data na Entrada Primária
        if should_enter_primary and use_cvd_primary and not is_streak_trade:
            if target_side == "UP" and cvd_135s < 0:
                cvd_blocks_primary += 1
                should_enter_primary = False
                if winner == "DOWN":
                    traps_prevented_by_cvd += 1
                else:
                    good_trades_filtered += 1
            elif target_side == "DOWN" and cvd_135s > 0:
                cvd_blocks_primary += 1
                should_enter_primary = False
                if winner == "UP":
                    traps_prevented_by_cvd += 1
                else:
                    good_trades_filtered += 1

        has_primary = False
        primary_shares = 0.0
        sold_early_tp = False
        sold_early_sl = False
        early_sell_payout = 0.0
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

            # Monitoramento Ativo (minuto 3, ~200s)
            spot_200s = (c3["open"] + c3["close"]) / 2.0
            delta_200s = spot_200s - strike
            p_target_200s = get_token_price(delta_200s if target_side == "UP" else -delta_200s, 200)

            # 1. SirMartingale Take-Profit (>= $0.86)
            min_tp = max(0.86, round(entry_price * 1.30, 3))
            if p_target_200s >= min_tp:
                sold_early_tp = True
                sirmartingale_tp_trades += 1
                cycle_payout += round(primary_shares * p_target_200s, 2)
                has_primary = False
            elif not sold_early_tp:
                # 2. Defesa: Bonereaper Hedge ou Stop-Loss de Emergência
                favored_delta = delta_200s if target_side == "UP" else -delta_200s
                if favored_delta <= -18.0:
                    p_hedge = 1.0 - p_target_200s
                    if p_hedge <= 0.50:
                        hedged = True
                        bonereaper_hedge_trades += 1
                        cycle_stake += 1.00
                        hedge_side = "DOWN" if target_side == "UP" else "UP"
                        hedge_shares = 1.00 / p_hedge
                    elif use_emergency_sl:
                        # Stop-Loss de Emergência: se hedge > $0.50 (EV negativo), vende cota primária se bid >= 0.15
                        best_bid_primary = p_target_200s
                        if best_bid_primary >= 0.15:
                            sold_early_sl = True
                            has_primary = False
                            emergency_sl_trades += 1
                            recovered = round(primary_shares * best_bid_primary, 2)
                            emergency_sl_rescued += recovered
                            cycle_payout += recovered

        # 2. Módulo Sweeper aos 240s (Modo Agressivo Moderado)
        sweeper_executed = False
        sweeper_shares = 0.0
        sweeper_side = None

        if not has_primary and not hedged and not sold_early_tp and not sold_early_sl:
            spot_240s = c4["open"]
            delta_240s = spot_240s - strike
            b_drift_240s = delta_240s

            # CVD acumulado até os 240s (min 0, 1, 2, 3)
            cvd_240s = c0["vd_usd"] + c1["vd_usd"] + c2["vd_usd"] + c3["vd_usd"]

            if abs(delta_240s) >= 20.0:
                sweeper_side = "UP" if delta_240s > 0 else "DOWN"
                sw_token_price = get_token_price(abs(delta_240s), 240)

                should_sweep = (0.50 <= sw_token_price <= 0.975)
                # Confirmacao Binance
                binance_sweep_ok = (sweeper_side == "UP" and b_drift_240s >= 5.0) or (sweeper_side == "DOWN" and b_drift_240s <= -5.0)
                if not binance_sweep_ok:
                    should_sweep = False

                # Validação de CVD no Sweeper: Evita varrer se houver exaustão / dump institucional massivo
                if should_sweep and use_cvd_sweeper:
                    if sweeper_side == "UP" and cvd_240s < -sweeper_cvd_threshold:
                        should_sweep = False
                        cvd_blocks_sweeper += 1
                        if winner == "DOWN":
                            traps_prevented_by_cvd += 1
                        else:
                            good_trades_filtered += 1
                    elif sweeper_side == "DOWN" and cvd_240s > sweeper_cvd_threshold:
                        should_sweep = False
                        cvd_blocks_sweeper += 1
                        if winner == "UP":
                            traps_prevented_by_cvd += 1
                        else:
                            good_trades_filtered += 1

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

        if cycle_pnl >= 0:
            wins += 1
        else:
            losses += 1

        if current_balance > peak_balance:
            peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown:
            max_drawdown = dd

    win_rate = (wins / participated_cycles * 100.0) if participated_cycles > 0 else 0.0
    roi = (total_pnl / total_stake * 100.0) if total_stake > 0 else 0.0
    profitable_days = sum(1 for d in daily_pnl.values() if d > 0)
    losing_days = sum(1 for d in daily_pnl.values() if d < 0)
    breakeven_days = sum(1 for d in daily_pnl.values() if d == 0)

    return {
        "name": name,
        "total_cycles": total_cycles,
        "participated_cycles": participated_cycles,
        "skipped_cycles": skipped_cycles,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "primary_trades": primary_trades,
        "primary_wins": primary_wins,
        "sirmartingale_tp_trades": sirmartingale_tp_trades,
        "bonereaper_hedge_trades": bonereaper_hedge_trades,
        "emergency_sl_trades": emergency_sl_trades,
        "emergency_sl_rescued": emergency_sl_rescued,
        "sweeper_trades": sweeper_trades,
        "sweeper_wins": sweeper_wins,
        "streak_trades": streak_trades,
        "streak_wins": streak_wins,
        "cvd_blocks_primary": cvd_blocks_primary,
        "cvd_blocks_sweeper": cvd_blocks_sweeper,
        "traps_prevented_by_cvd": traps_prevented_by_cvd,
        "good_trades_filtered": good_trades_filtered,
        "total_stake": total_stake,
        "total_payout": total_payout,
        "total_pnl": total_pnl,
        "roi": roi,
        "final_balance": current_balance,
        "max_drawdown": max_drawdown,
        "profitable_days": profitable_days,
        "losing_days": losing_days,
        "breakeven_days": breakeven_days,
        "daily_pnl": daily_pnl
    }

# 1. Baseline Sem CVD e Sem Stop-Loss
res_baseline = run_backtest_simulation(
    name="1. Baseline Sem CVD & Sem SL",
    use_cvd_primary=False,
    use_cvd_sweeper=False,
    use_emergency_sl=False
)

# 2. Código Atual com CVD 1.5M e Stop-Loss Ativo
res_current = run_backtest_simulation(
    name="2. Código Atual (CVD 1.5M + Emergency SL)",
    use_cvd_primary=True,
    use_cvd_sweeper=True,
    use_emergency_sl=True,
    sweeper_cvd_threshold=1_500_000.0
)

# 3. Código Atual com CVD 2.0M e Stop-Loss Ativo
res_conservative = run_backtest_simulation(
    name="3. Código Atual (CVD 2.0M + Emergency SL)",
    use_cvd_primary=True,
    use_cvd_sweeper=True,
    use_emergency_sl=True,
    sweeper_cvd_threshold=2_000_000.0
)

def print_result_card(r):
    print("=" * 95)
    print(f"ESTATÍSTICAS: {r['name'].upper()}")
    print("=" * 95)
    print(f"  Ciclos Analisados:        {r['total_cycles']:,} (60 Dias)")
    print(f"  Ciclos Participados:      {r['participated_cycles']:,} ({r['participated_cycles']/r['total_cycles']*100:.1f}%)")
    print(f"  Ciclos Dispensados:       {r['skipped_cycles']:,}")
    print(f"  Taxa de Acerto Geral:     {r['win_rate']:.2f}% ({r['wins']:,}V / {r['losses']:,}D)")
    print(f"  Volume Total Apostado:    ${r['total_stake']:,.2f} USDC")
    print(f"  Payouts Brutos Recebidos: ${r['total_payout']:,.2f} USDC")
    print(f"  Lucro Líquido (P&L):      ${r['total_pnl']:+,.2f} USDC")
    print(f"  Retorno sobre Volume:     {r['roi']:.2f}%")
    print(f"  Saldo Final (de $21):     ${r['final_balance']:,.2f} USDC")
    print(f"  Drawdown Máximo:          -${r['max_drawdown']:.2f} USDC")
    print(f"  Dias Positivos:           {r['profitable_days']} dias / {r['losing_days']} dias negativos / {r['breakeven_days']} neutros")
    print("-" * 95)
    print("  DESMEMBRAMENTO POR MÓDULO:")
    pw = r['primary_wins'] / max(1, r['primary_trades']) * 100
    print(f"  - Entrada Primária 135s:   {r['primary_trades']:,} trades | {r['primary_wins']:,}V ({pw:.1f}% WR)")
    print(f"  - SirMartingale TP (170s): {r['sirmartingale_tp_trades']:,} vendas antecipadas no lucro (>= $0.86)")
    print(f"  - Bonereaper Hedge:        {r['bonereaper_hedge_trades']:,} hedges executados (cota <= $0.50)")
    print(f"  - Stop-Loss Emergência:    {r['emergency_sl_trades']:,} resgates de capital (Total resgatado: +${r['emergency_sl_rescued']:.2f} USDC)")
    sw = r['sweeper_wins'] / max(1, r['sweeper_trades']) * 100
    print(f"  - Sweeper Agressivo 240s:  {r['sweeper_trades']:,} trades | {r['sweeper_wins']:,}V ({sw:.1f}% WR)")
    stw = r['streak_wins'] / max(1, r['streak_trades']) * 100
    print(f"  - Streak Snapper:          {r['streak_trades']:,} trades | {r['streak_wins']:,}V ({stw:.1f}% WR)")
    print("-" * 95)
    print(f"  PROTEÇÃO CVD TICK DATA:")
    print(f"  - Bloqueios na Primária:   {r['cvd_blocks_primary']:,} entradas bloqueadas (Anti-Bull/Bear Trap)")
    print(f"  - Bloqueios no Sweeper:    {r['cvd_blocks_sweeper']:,} varreduras bloqueadas (Anti-Dump/Pump Final)")
    print(f"  - Armadilhas Fatais Salvas: {r['traps_prevented_by_cvd']:,} perdas reais impedidas pelo CVD")
    print("=" * 95 + "\n")

print_result_card(res_baseline)
print_result_card(res_current)
print_result_card(res_conservative)

# Comparativo Direto
print("\n" + "#" * 95)
print("TABELA COMPARATIVA CONSOLIDADA (60 DIAS DE BITCOIN)")
print("#" * 95)
print(f"{'Métrica':<28} | {'1. Baseline (Sem CVD/SL)':<22} | {'2. Atual (CVD 1.5M + SL)':<24} | {'3. Conservador (2.0M)'}")
print("-" * 95)
print(f"{'Operações Totais':<28} | {res_baseline['participated_cycles']:<22} | {res_current['participated_cycles']:<24} | {res_conservative['participated_cycles']}")
print(f"{'Taxa de Acerto (Win Rate)':<28} | {res_baseline['win_rate']:<22.2f}% | {res_current['win_rate']:<24.2f}% | {res_conservative['win_rate']:.2f}%")
print(f"{'Lucro Líquido (USDC)':<28} | ${res_baseline['total_pnl']:<21.2f} | ${res_current['total_pnl']:<23.2f} | ${res_conservative['total_pnl']:.2f}")
print(f"{'ROI s/ Volume':<28} | {res_baseline['roi']:<22.2f}% | {res_current['roi']:<24.2f}% | {res_conservative['roi']:.2f}%")
print(f"{'Drawdown Máximo':<28} | -${res_baseline['max_drawdown']:<21.2f} | -${res_current['max_drawdown']:<23.2f} | -${res_conservative['max_drawdown']:.2f}")
print(f"{'Saldo Final (de $21)':<28} | ${res_baseline['final_balance']:<21.2f} | ${res_current['final_balance']:<23.2f} | ${res_conservative['final_balance']:.2f}")
print(f"{'Resgate Stop-Loss':<28} | ${res_baseline['emergency_sl_rescued']:<21.2f} | ${res_current['emergency_sl_rescued']:<23.2f} | ${res_conservative['emergency_sl_rescued']:.2f}")
print(f"{'Armadilhas Evitadas':<28} | {res_baseline['traps_prevented_by_cvd']:<22} | {res_current['traps_prevented_by_cvd']:<24} | {res_conservative['traps_prevented_by_cvd']}")
print("#" * 95 + "\n")
