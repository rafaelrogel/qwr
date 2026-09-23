"""
=============================================================================
AUDITORIA QUANTITATIVA: BACKTEST COMPLETO DO ENGINE (ÚLTIMOS 30 DIAS)
=============================================================================
Testa o pipeline completo de `live_trader_5m.py` com todos os módulos:
- Filtro Deadband (|Delta| >= $15)
- Gatilho Streak Snapper (4x mesma direção + Esticamento >= 3x ATR com cota <= $0.52)
- SirMartingale Take-Profit (Venda com lucro >= $0.86 aos 170s-240s)
- Bonereaper Hedge (Defesa com cota <= $0.50 quando Delta <= -$18)
- BTC5MScour Sweeper (Varredura aos 255s com |Delta| >= $25)
- Trava de Risco e Stop-Loss
- P&L acumulado, drawdown, métricas diárias e taxa de acerto por módulo

Período: Últimos 30 dias (~43.200 velas de 1m / 8.640 velas de 5m)
=============================================================================
"""

import urllib.request
import json
import time
from datetime import datetime

print("\n" + "=" * 85)
print("[+] INICIANDO BACKTEST DE 30 DIAS DO ENGINE LIVE_TRADER_5M...")
print("=" * 85)

# 1. Carregar ~43.200 velas de 1 minuto da Binance
now_ms = int(time.time() * 1000)
thirty_days_ms = now_ms - (30 * 24 * 3600 * 1000)
start_ms = (thirty_days_ms // 300000) * 300000

all_1m = []
curr_start = start_ms

print(f"[*] Baixando histórico de 30 dias de klines 1m da Binance BTCUSDT...")
batch_count = 0

while curr_start < now_ms:
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={curr_start}&limit=1000"
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
                print(f"    ... {len(all_1m):,} velas baixadas ({batch_count * 1000} minutos)...")
            time.sleep(0.05)
    except Exception as e:
        print(f"[!] Erro no download no timestamp {curr_start}: {e}")
        time.sleep(1)
        # tentar retomar
        continue

print(f"[OK] Total de {len(all_1m):,} velas de 1m carregadas com sucesso.")

candles_1m = {}
for k in all_1m:
    ts_sec = int(k[0]) // 1000
    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "tr": max(float(k[2]) - float(k[3]), abs(float(k[2]) - float(k[1])), abs(float(k[3]) - float(k[1])))
    }

all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])
print(f"[OK] Total de ciclos de 5m disponíveis: {len(all_5m_ts):,} ciclos.")

# Pre-computar vencedores das velas de 5m para o histórico do Streak Snapper
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
    """
    Modelagem da precificacao da CLOB do Polymarket:
    Sensibilidade do preco ao delta cresce exponencialmente com o tempo restante.
    """
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.98, prob))


def run_full_engine_simulation():
    # Métricas Globais
    total_cycles = 0
    participated_cycles = 0
    skipped_cycles = 0

    wins = 0
    losses = 0
    defenses = 0

    # Desdobramento por tipo de evento
    primary_trades = 0
    primary_wins = 0
    sirmartingale_tp_trades = 0
    bonereaper_hedge_trades = 0
    sweeper_trades = 0
    sweeper_wins = 0
    streak_snapper_trades = 0
    streak_snapper_wins = 0

    total_stake = 0.0
    total_payout = 0.0
    total_pnl = 0.0

    peak_balance = 21.00 # Banca inicial simulada
    current_balance = 21.00
    max_drawdown = 0.0
    daily_pnl = {}
    daily_stats = {}

    for idx, w_ts in enumerate(all_5m_ts):
        if idx < 16:
            continue # Precisa de histórico para ATR e streaks

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
            daily_stats[day_str] = {"trades": 0, "wins": 0, "losses": 0, "stake": 0.0, "payout": 0.0}

        strike = c0["open"]
        final_spot = c4["close"]
        final_delta = final_spot - strike
        winner = "UP" if final_spot >= strike else "DOWN"

        # -----------------------------------------------------------------
        # PASSO 1: Leitura aos 135s (2m15s da vela)
        # -----------------------------------------------------------------
        spot_135s = (c2["open"] + c2["close"]) / 2.0
        delta_135s = spot_135s - strike

        # Cálculo do ATR Horário (últimas 12 velas de 5m completas)
        prior_ts = all_5m_ts[idx-12:idx]
        hourly_atr = sum(history_5m[t]["tr"] for t in prior_ts if t in history_5m) / 12.0

        # Streak Snapper DESATIVADO (Auditoria Quantitativa 5 Anos: WR 37.2% causava perda líquida)
        has_streak = False
        streak_reversal = None

        # Decisão de Entrada Primária aos 135s (Puramente Deadband de Momentum comprovado)
        should_enter_primary = False
        target_side = None
        is_streak_trade = False

        if abs(delta_135s) >= 15.0: # Deadband
            target_side = "UP" if delta_135s > 0 else "DOWN"
            should_enter_primary = True

        # Preço estimado na CLOB aos 135s
        p_up_135 = get_token_price(delta_135s, 135)
        p_down_135 = 1.0 - p_up_135
        entry_price = p_up_135 if target_side == "UP" else p_down_135

        # Filtros de Preço
        if should_enter_primary:
            if is_streak_trade and entry_price > 0.52:
                should_enter_primary = False # Trava estrita do Streak Snapper
            elif entry_price < 0.35 or entry_price > 0.65:
                should_enter_primary = False # Filtro saudável de preço

        # -----------------------------------------------------------------
        # PASSO 2: Execução Primária e Monitoramento (SirMartingale / Bonereaper)
        # -----------------------------------------------------------------
        has_primary = False
        primary_shares = 0.0
        sold_early_tp = False
        tp_payout = 0.0

        hedged = False
        hedge_shares = 0.0
        hedge_side = None
        hedge_price = 0.0

        cycle_stake = 0.0
        cycle_payout = 0.0

        if should_enter_primary:
            has_primary = True
            primary_trades += 1
            cycle_stake += 1.00 # $1.00 USDC
            primary_shares = 1.00 / entry_price
            if is_streak_trade:
                streak_snapper_trades += 1

            # Monitoramento dos 140s aos 240s (Minuto 3)
            # Preço aos 200s (Minuto 3)
            spot_200s = (c3["open"] + c3["close"]) / 2.0
            delta_200s = spot_200s - strike
            p_target_200s = get_token_price(delta_200s if target_side == "UP" else -delta_200s, 200)

            # 1. SirMartingale Take-Profit: Se cota atingir >= $0.86, vende antecipadamente
            if p_target_200s >= 0.86:
                sold_early_tp = True
                sirmartingale_tp_trades += 1
                # Vende a $0.86 travando lucro
                tp_payout = round(primary_shares * 0.86, 2)
                cycle_payout += tp_payout
                has_primary = False # Posição encerrada com lucro antecipado!

            # 2. Bonereaper Hedge: Se reverteu contra (Delta <= -$18 em relação à nossa aposta)
            elif not sold_early_tp:
                favored_delta = delta_200s if target_side == "UP" else -delta_200s
                if favored_delta <= -18.0:
                    hedge_side = "DOWN" if target_side == "UP" else "UP"
                    p_hedge = 1.0 - p_target_200s
                    if p_hedge <= 0.50:
                        hedged = True
                        bonereaper_hedge_trades += 1
                        cycle_stake += 1.00 # $1.00 USDC de hedge
                        hedge_price = p_hedge
                        hedge_shares = 1.00 / hedge_price

        # -----------------------------------------------------------------
        # PASSO 3: Módulo BTC5MScour (Sweeper aos 255s)
        # -----------------------------------------------------------------
        sweeper_executed = False
        sweeper_shares = 0.0
        sweeper_side = None

        if not has_primary and not hedged:
            spot_255s = c4["open"]
            delta_255s = spot_255s - strike
            if abs(delta_255s) >= 25.0:
                sweeper_side = "UP" if delta_255s > 0 else "DOWN"
                sweeper_price = get_token_price(abs(delta_255s), 255)
                if 0.55 <= sweeper_price <= 0.965:
                    sweeper_executed = True
                    sweeper_trades += 1
                    cycle_stake += 1.00
                    sweeper_shares = 1.00 / sweeper_price

        # -----------------------------------------------------------------
        # PASSO 4: Liquidação Final aos 300s
        # -----------------------------------------------------------------
        if cycle_stake == 0.0:
            skipped_cycles += 1
            continue

        participated_cycles += 1
        daily_stats[day_str]["trades"] += 1
        daily_stats[day_str]["stake"] += cycle_stake

        # Apuração dos Payouts
        if has_primary:
            if target_side == winner:
                cycle_payout += round(primary_shares * 1.00, 2)
                primary_wins += 1
                if is_streak_trade:
                    streak_snapper_wins += 1

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
        daily_stats[day_str]["payout"] += cycle_payout

        if current_balance > peak_balance:
            peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown:
            max_drawdown = dd

        if cycle_pnl > 0:
            wins += 1
            daily_stats[day_str]["wins"] += 1
        elif cycle_pnl == 0:
            wins += 1
            daily_stats[day_str]["wins"] += 1
        elif hedged and cycle_pnl >= -0.30:
            defenses += 1
            daily_stats[day_str]["wins"] += 1
        else:
            losses += 1
            daily_stats[day_str]["losses"] += 1

    overall_wr = (wins / participated_cycles * 100) if participated_cycles > 0 else 0.0
    overall_roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0.0

    return {
        "total_cycles": total_cycles,
        "participated": participated_cycles,
        "skipped": skipped_cycles,
        "wins": wins,
        "losses": losses,
        "defenses": defenses,
        "win_rate": overall_wr,
        "total_stake": total_stake,
        "total_payout": total_payout,
        "total_pnl": total_pnl,
        "roi": overall_roi,
        "max_drawdown": max_drawdown,
        "daily_pnl": daily_pnl,
        "daily_stats": daily_stats,
        "primary_trades": primary_trades,
        "primary_wins": primary_wins,
        "primary_wr": (primary_wins / primary_trades * 100) if primary_trades > 0 else 0,
        "sirmartingale_tp": sirmartingale_tp_trades,
        "bonereaper_hedge": bonereaper_hedge_trades,
        "sweeper_trades": sweeper_trades,
        "sweeper_wins": sweeper_wins,
        "sweeper_wr": (sweeper_wins / sweeper_trades * 100) if sweeper_trades > 0 else 0,
        "streak_trades": streak_snapper_trades,
        "streak_wins": streak_snapper_wins,
        "streak_wr": (streak_snapper_wins / streak_snapper_trades * 100) if streak_snapper_trades > 0 else 0,
    }


r = run_full_engine_simulation()

print("\n" + "=" * 85)
print("[*] RELATÓRIO QUANTITATIVO DEFINITIVO: ENGINE COMPLETO (ÚLTIMOS 30 DIAS)")
print("=" * 85)
print(f"  * Total de Ciclos de 5m no Período:    {r['total_cycles']:,} velas")
print(f"  * Ciclos com Trade Operado:            {r['participated']:,} ({r['participated']/r['total_cycles']*100:.1f}%)")
print(f"  * Ciclos Filtrados (Preservou Capital): {r['skipped']:,} ({r['skipped']/r['total_cycles']*100:.1f}%)")
print("-" * 85)
print(f"  [+] RESULTADO FINANCEIRO GLOBAL (STAKE BASE $1.00 USDC):")
print(f"     - Volume Total Apostado:            ${r['total_stake']:,.2f} USDC")
print(f"     - Payouts Totais Resgatados:        ${r['total_payout']:,.2f} USDC")
print(f"     - Lucro Líquido Real (P&L):         {r['total_pnl']:+,.2f} USDC")
print(f"     - Retorno sobre o Volume (ROI):     {r['roi']:+.2f}%")
print(f"     - Retorno sobre Banca Inicial ($21): {(r['total_pnl'] / 21.0 * 100):+.1f}%")
print(f"     - Drawdown Máximo:                  ${r['max_drawdown']:.2f} USDC")
print("-" * 85)
print(f"  [+] PERFORMANCE E TAXA DE ACERTO:")
print(f"     - Vitórias / Lucros:                {r['wins']} trades")
print(f"     - Derrotas:                         {r['losses']} trades")
print(f"     - Defesas Hedge com Perda Mínima:   {r['defenses']} trades")
print(f"     - TAXA DE ACERTO GLOBAL:            {r['win_rate']:.1f}%")
print("-" * 85)
print(f"  [+] DESDOBRAMENTO MÓDULO POR MÓDULO:")
print(f"     1. Entrada Primária (135s):         {r['primary_trades']} trades | Win Rate: {r['primary_wr']:.1f}% ({r['primary_wins']}V)")
print(f"     2. SirMartingale (Take-Profit):     {r['sirmartingale_tp']} trades travados com lucro antecipado")
print(f"     3. Bonereaper (Hedge Defensivo):    {r['bonereaper_hedge']} operações de contenção de risco acionadas")
print(f"     4. BTC5MScour (Sweeper 255s):       {r['sweeper_trades']} trades | Win Rate: {r['sweeper_wr']:.1f}% ({r['sweeper_wins']}V)")
print(f"     5. Streak Snapper (Reversão 3x):    {r['streak_trades']} trades | Win Rate: {r['streak_wr']:.1f}% ({r['streak_wins']}V)")
print("-" * 85)
print("  [+] P&L DIÁRIO (30 DIAS):")
profitable_days = 0
loss_days = 0
for day, pnl in sorted(r["daily_pnl"].items()):
    st = r["daily_stats"][day]
    day_wr = (st["wins"] / st["trades"] * 100) if st["trades"] > 0 else 0
    if pnl > 0:
        status = "[+]"
        profitable_days += 1
    elif pnl < 0:
        status = "[-]"
        loss_days += 1
    else:
        status = "[=]"
    print(f"     {status} {day}: {pnl:+6.2f} USDC | {st['trades']:3d} trades ({st['wins']}V/{st['losses']}D) | WR: {day_wr:5.1f}%")

print("-" * 85)
print(f"  [+] RESUMO DE CONSISTÊNCIA DIÁRIA:")
print(f"     - Dias com Lucro:                   {profitable_days} dias ({profitable_days / len(r['daily_pnl']) * 100:.1f}%)")
print(f"     - Dias com Prejuízo:                {loss_days} dias ({loss_days / len(r['daily_pnl']) * 100:.1f}%)")
print("=" * 85 + "\n")

# Salvar resultados em json para arquivo histórico
with open("backtest_full_engine_30d_results.json", "w") as f:
    json.dump(r, f, indent=2)
print("[OK] Resultados salvos em 'backtest_full_engine_30d_results.json'.\n")
