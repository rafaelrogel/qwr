"""
=============================================================================
BACKTEST COMPARATIVO 5 ANOS: PARÂMETROS ATUAIS vs OTIMIZADOS
=============================================================================
Roda ambas configurações sobre o mesmo dataset de 5 anos e compara side-by-side.
Cache: btc_1m_5y_cache.json (458 MB, já baixado)
=============================================================================
"""

import json
import time
import os
import sys
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "btc_1m_5y_cache.json")

INITIAL_BALANCE = 21.00

# ===================== CONFIGURAÇÕES =====================
CONFIGS = {
    "ATUAL": {
        "label": "1. Atual (Live Baseline)",
        "DEADBAND": 15.0,
        "PRIMARY_MIN_PRICE": 0.35,
        "PRIMARY_MAX_PRICE": 0.65,
        "STREAK_ENABLED": True,
        "STREAK_MAX_PRICE": 0.52,
        "TP_THRESHOLD": 0.86,
        "HEDGE_DELTA": -18.0,
        "HEDGE_MAX_PRICE": 0.45,
        "BASE_STAKE": 1.00,
        "STAKE_INCREMENT": 0.50,
        "PROFIT_STEP": 10.00,
        "MAX_STAKE": 5.00,
    },
    "SEM_STREAK": {
        "label": "2. Sem Streak (Desativa Snapper 37% WR)",
        "DEADBAND": 15.0,
        "PRIMARY_MIN_PRICE": 0.35,
        "PRIMARY_MAX_PRICE": 0.65,
        "STREAK_ENABLED": False,
        "STREAK_MAX_PRICE": 0.52,
        "TP_THRESHOLD": 0.86,
        "HEDGE_DELTA": -18.0,
        "HEDGE_MAX_PRICE": 0.45,
        "BASE_STAKE": 1.00,
        "STAKE_INCREMENT": 0.50,
        "PROFIT_STEP": 10.00,
        "MAX_STAKE": 5.00,
    },
    "HEDGE_ATIVO_TP82": {
        "label": "3. Sem Streak + TP 0.82 + Hedge -12",
        "DEADBAND": 15.0,
        "PRIMARY_MIN_PRICE": 0.35,
        "PRIMARY_MAX_PRICE": 0.65,
        "STREAK_ENABLED": False,
        "STREAK_MAX_PRICE": 0.52,
        "TP_THRESHOLD": 0.82,           # Venda antecipada mais fácil
        "HEDGE_DELTA": -12.0,           # Hedge aciona com reversão menor
        "HEDGE_MAX_PRICE": 0.50,
        "BASE_STAKE": 1.00,
        "STAKE_INCREMENT": 0.50,
        "PROFIT_STEP": 10.00,
        "MAX_STAKE": 5.00,
    },
    "DEADBAND_20_PRICE72": {
        "label": "4. Deadband 20.0 + Max Price 0.72",
        "DEADBAND": 20.0,
        "PRIMARY_MIN_PRICE": 0.35,
        "PRIMARY_MAX_PRICE": 0.72,       # Permite entrada com Delta >= 20
        "STREAK_ENABLED": False,
        "STREAK_MAX_PRICE": 0.52,
        "TP_THRESHOLD": 0.86,
        "HEDGE_DELTA": -14.0,
        "HEDGE_MAX_PRICE": 0.50,
        "BASE_STAKE": 1.00,
        "STAKE_INCREMENT": 0.50,
        "PROFIT_STEP": 10.00,
        "MAX_STAKE": 5.00,
    },
    "CONSERVADOR_SAFE": {
        "label": "5. Otimizado Seguro (Cap $3.00, +$0.25/+$20)",
        "DEADBAND": 15.0,
        "PRIMARY_MIN_PRICE": 0.35,
        "PRIMARY_MAX_PRICE": 0.65,
        "STREAK_ENABLED": False,
        "STREAK_MAX_PRICE": 0.52,
        "TP_THRESHOLD": 0.82,
        "HEDGE_DELTA": -12.0,
        "HEDGE_MAX_PRICE": 0.50,
        "BASE_STAKE": 1.00,
        "STAKE_INCREMENT": 0.25,        # Crescimento de stake mais suave
        "PROFIT_STEP": 20.00,
        "MAX_STAKE": 3.00,              # Cap conservador de risco
    },
}

print("\n" + "=" * 90)
print("  BACKTEST COMPARATIVO 5 ANOS: ATUAL vs OTIMIZADO")
print("=" * 90)

# ===================== CARREGAR CACHE =====================
print(f"\n[*] Carregando cache: {CACHE_FILE}...")
with open(CACHE_FILE, "r", encoding="utf-8") as f:
    raw_klines = json.load(f)
print(f"[OK] {len(raw_klines):,} velas de 1m carregadas.\n")

# Indexar
print("[*] Indexando velas...")
candles_1m = {}
for k in raw_klines:
    ts_sec = int(k[0]) // 1000
    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "tr": max(float(k[2]) - float(k[3]), abs(float(k[2]) - float(k[1])), abs(float(k[3]) - float(k[1])))
    }
del raw_klines  # Liberar memória

all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])
print(f"[OK] {len(all_5m_ts):,} janelas de 5m.\n")

# Pre-computar histórico 5m
print("[*] Pré-computando histórico 5m...")
history_5m = {}
for w_ts in all_5m_ts:
    c0 = candles_1m.get(w_ts)
    c4 = candles_1m.get(w_ts + 240)
    if c0 and c4:
        tr_sum = sum(candles_1m.get(w_ts + i * 60, {}).get("tr", 0) for i in range(5))
        history_5m[w_ts] = {
            "open": c0["open"],
            "close": c4["close"],
            "winner": "UP" if c4["close"] >= c0["open"] else "DOWN",
            "tr": tr_sum
        }
print(f"[OK] {len(history_5m):,} velas pré-computadas.\n")


def get_token_price(delta_usd, elapsed_sec):
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.98, prob))


def get_stake(total_pnl, cfg):
    if total_pnl <= 0:
        return cfg["BASE_STAKE"]
    increments = int(total_pnl // cfg["PROFIT_STEP"])
    return min(round(cfg["BASE_STAKE"] + increments * cfg["STAKE_INCREMENT"], 2), cfg["MAX_STAKE"])


def run_simulation(cfg):
    """Roda simulação completa com uma configuração específica"""
    total_cycles = 0
    participated = 0
    skipped = 0
    wins = 0
    losses = 0
    defenses = 0

    primary_trades = 0
    primary_wins = 0
    primary_losses = 0
    tp_trades = 0
    hedge_trades = 0
    hedge_wins = 0
    streak_trades = 0
    streak_wins = 0

    total_stake = 0.0
    total_payout = 0.0
    total_pnl = 0.0

    current_balance = INITIAL_BALANCE
    peak_balance = INITIAL_BALANCE
    max_drawdown = 0.0
    min_balance = INITIAL_BALANCE

    yearly_pnl = {}
    monthly_pnl = {}
    daily_pnl = {}
    quarterly_pnl = {}

    # Tracking por tipo de trade para análise
    deadband_trades = 0
    deadband_wins = 0
    tp_saved_losses = 0  # Trades que teriam sido derrota mas TP salvou

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
        month_str = datetime.utcfromtimestamp(w_ts).strftime("%Y-%m")
        year_str = datetime.utcfromtimestamp(w_ts).strftime("%Y")
        quarter_str = f"{year_str}-Q{(int(datetime.utcfromtimestamp(w_ts).strftime('%m'))-1)//3+1}"

        if day_str not in daily_pnl:
            daily_pnl[day_str] = 0.0
        if month_str not in monthly_pnl:
            monthly_pnl[month_str] = 0.0
        if year_str not in yearly_pnl:
            yearly_pnl[year_str] = 0.0
        if quarter_str not in quarterly_pnl:
            quarterly_pnl[quarter_str] = 0.0

        strike = c0["open"]
        final_spot = c4["close"]
        winner = "UP" if final_spot >= strike else "DOWN"

        stake_size = get_stake(total_pnl, cfg)

        # 135s
        spot_135s = (c2["open"] + c2["close"]) / 2.0
        delta_135s = spot_135s - strike

        # ATR
        prior_ts = all_5m_ts[max(0, idx - 12):idx]
        hourly_atr_vals = [history_5m[t]["tr"] for t in prior_ts if t in history_5m]
        hourly_atr = sum(hourly_atr_vals) / len(hourly_atr_vals) if hourly_atr_vals else 1.0

        # Streak
        has_streak = False
        streak_reversal = None
        if cfg["STREAK_ENABLED"]:
            prior_4_ts = all_5m_ts[max(0, idx - 4):idx]
            prior_4 = [history_5m[t] for t in prior_4_ts if t in history_5m]
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

        # Decisão
        should_enter = False
        target_side = None
        is_streak = False

        if has_streak:
            target_side = streak_reversal
            is_streak = True
            should_enter = True
        elif abs(delta_135s) >= cfg["DEADBAND"]:
            target_side = "UP" if delta_135s > 0 else "DOWN"
            should_enter = True

        # Preço CLOB
        p_up = get_token_price(delta_135s, 135)
        p_down = 1.0 - p_up
        entry_price = p_up if target_side == "UP" else p_down

        # Filtros
        if should_enter:
            if is_streak and entry_price > cfg["STREAK_MAX_PRICE"]:
                should_enter = False
            elif entry_price < cfg["PRIMARY_MIN_PRICE"] or entry_price > cfg["PRIMARY_MAX_PRICE"]:
                should_enter = False

        # Execução
        has_primary = False
        primary_shares = 0.0
        sold_early = False
        hedged = False
        hedge_shares = 0.0
        hedge_side = None
        cycle_stake = 0.0
        cycle_payout = 0.0

        if should_enter:
            has_primary = True
            primary_trades += 1
            cycle_stake += stake_size
            primary_shares = stake_size / entry_price
            if is_streak:
                streak_trades += 1
            else:
                deadband_trades += 1

            # 200s
            spot_200s = (c3["open"] + c3["close"]) / 2.0
            delta_200s = spot_200s - strike
            p_target_200s = get_token_price(
                delta_200s if target_side == "UP" else -delta_200s, 200
            )

            # TP
            if p_target_200s >= cfg["TP_THRESHOLD"]:
                sold_early = True
                tp_trades += 1
                tp_payout = round(primary_shares * 0.86, 2)
                cycle_payout += tp_payout
                has_primary = False
                # Check se teria sido derrota
                if target_side != winner:
                    tp_saved_losses += 1

            # Hedge
            elif not sold_early:
                favored_delta = delta_200s if target_side == "UP" else -delta_200s
                if favored_delta <= cfg["HEDGE_DELTA"]:
                    hedge_side = "DOWN" if target_side == "UP" else "UP"
                    p_hedge = 1.0 - p_target_200s
                    if p_hedge <= cfg["HEDGE_MAX_PRICE"]:
                        hedged = True
                        hedge_trades += 1
                        cycle_stake += stake_size
                        hedge_shares = stake_size / p_hedge

        if cycle_stake == 0.0:
            skipped += 1
            continue

        participated += 1

        # Liquidação
        if has_primary:
            if target_side == winner:
                cycle_payout += round(primary_shares * 1.00, 2)
                primary_wins += 1
                if is_streak:
                    streak_wins += 1
                else:
                    deadband_wins += 1
            else:
                primary_losses += 1

        if hedged:
            if hedge_side == winner:
                cycle_payout += round(hedge_shares * 1.00, 2)
                hedge_wins += 1

        cycle_pnl = round(cycle_payout - cycle_stake, 2)
        total_stake += cycle_stake
        total_payout += cycle_payout
        total_pnl += cycle_pnl
        current_balance += cycle_pnl

        daily_pnl[day_str] += cycle_pnl
        monthly_pnl[month_str] += cycle_pnl
        yearly_pnl[year_str] += cycle_pnl
        quarterly_pnl[quarter_str] += cycle_pnl

        if current_balance > peak_balance:
            peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown:
            max_drawdown = dd
        if current_balance < min_balance:
            min_balance = current_balance

        if cycle_pnl > 0:
            wins += 1
        elif cycle_pnl == 0:
            wins += 1
        elif hedged and cycle_pnl >= -0.30:
            defenses += 1
        else:
            losses += 1

    wr = (wins / participated * 100) if participated > 0 else 0
    roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0
    profitable_days = sum(1 for v in daily_pnl.values() if v > 0)
    loss_days = sum(1 for v in daily_pnl.values() if v < 0)
    trading_days = sum(1 for v in daily_pnl.values() if v != 0)
    profitable_months = sum(1 for v in monthly_pnl.values() if v > 0)
    loss_months = sum(1 for v in monthly_pnl.values() if v < 0)
    profitable_quarters = sum(1 for v in quarterly_pnl.values() if v > 0)

    best_day = max(daily_pnl.items(), key=lambda x: x[1])
    worst_day = min(daily_pnl.items(), key=lambda x: x[1])
    best_month = max(monthly_pnl.items(), key=lambda x: x[1])
    worst_month = min(monthly_pnl.items(), key=lambda x: x[1])

    # Sharpe
    daily_returns = [v for v in daily_pnl.values() if v != 0]
    if daily_returns:
        avg_d = sum(daily_returns) / len(daily_returns)
        std_d = (sum((x - avg_d) ** 2 for x in daily_returns) / len(daily_returns)) ** 0.5
        sharpe = avg_d / std_d if std_d > 0 else 0
    else:
        avg_d = std_d = sharpe = 0

    # Win/Loss streaks
    max_win_str = max_loss_str = curr_w = curr_l = 0
    for day in sorted(daily_pnl.keys()):
        v = daily_pnl[day]
        if v > 0:
            curr_w += 1; curr_l = 0; max_win_str = max(max_win_str, curr_w)
        elif v < 0:
            curr_l += 1; curr_w = 0; max_loss_str = max(max_loss_str, curr_l)

    # Avg profit per win, avg loss per loss
    avg_profit_per_win = (total_payout - total_stake + abs(total_pnl)) / max(wins, 1) if total_pnl > 0 else 0
    
    return {
        "total_cycles": total_cycles,
        "participated": participated,
        "skipped": skipped,
        "wins": wins, "losses": losses, "defenses": defenses,
        "win_rate": round(wr, 2),
        "total_stake": round(total_stake, 2),
        "total_payout": round(total_payout, 2),
        "total_pnl": round(total_pnl, 2),
        "roi": round(roi, 2),
        "final_balance": round(current_balance, 2),
        "peak_balance": round(peak_balance, 2),
        "min_balance": round(min_balance, 2),
        "max_drawdown": round(max_drawdown, 2),
        "final_stake": get_stake(total_pnl, cfg),
        "primary_trades": primary_trades,
        "primary_wins": primary_wins,
        "primary_losses": primary_losses,
        "primary_wr": round((primary_wins / primary_trades * 100) if primary_trades > 0 else 0, 1),
        "tp_trades": tp_trades,
        "tp_saved_losses": tp_saved_losses,
        "hedge_trades": hedge_trades,
        "hedge_wins": hedge_wins,
        "streak_trades": streak_trades,
        "streak_wins": streak_wins,
        "streak_wr": round((streak_wins / streak_trades * 100) if streak_trades > 0 else 0, 1),
        "deadband_trades": deadband_trades,
        "deadband_wins": deadband_wins,
        "deadband_wr": round((deadband_wins / deadband_trades * 100) if deadband_trades > 0 else 0, 1),
        "yearly_pnl": {k: round(v, 2) for k, v in sorted(yearly_pnl.items())},
        "quarterly_pnl": {k: round(v, 2) for k, v in sorted(quarterly_pnl.items())},
        "profitable_days": profitable_days,
        "loss_days": loss_days,
        "trading_days": trading_days,
        "profitable_months": profitable_months,
        "loss_months": loss_months,
        "profitable_quarters": profitable_quarters,
        "best_day": best_day,
        "worst_day": worst_day,
        "best_month": best_month,
        "worst_month": worst_month,
        "sharpe": round(sharpe, 4),
        "max_win_streak": max_win_str,
        "max_loss_streak": max_loss_str,
    }


# ===================== RODAR AMBAS SIMULAÇÕES =====================
results = {}
for name, cfg in CONFIGS.items():
    print(f"[*] Rodando simulação: {cfg['label']}...")
    t0 = time.time()
    results[name] = run_simulation(cfg)
    elapsed = time.time() - t0
    r = results[name]
    print(f"    -> {r['participated']:,} trades | P&L: {r['total_pnl']:+,.2f} | WR: {r['win_rate']:.1f}% | {elapsed:.1f}s\n")


# ===================== RELATÓRIO COMPARATIVO COMPLETO =====================
baseline_key = "ATUAL"
base = results[baseline_key]

print("\n" + "=" * 115)
print("  📊 RELATÓRIO COMPARATIVO: MATRIZ DE OTIMIZAÇÃO (5 ANOS DE DADOS REAIS)")
print("=" * 115)

print("\n  [1] TABELA GERAL COMPARATIVA:")
hdr = f"  │ {'Estratégia':<36} │ {'Trades':>7} │ {'WinRate':>7} │ {'P&L ($)':>12} │ {'ROI (%)':>8} │ {'MaxDD ($)':>9} │ {'Sharpe':>7} │ {'Saldo ($)':>12} │"
print("  ┌" + "─"*38 + "┬" + "─"*9 + "┬" + "─"*9 + "┬" + "─"*14 + "┬" + "─"*10 + "┬" + "─"*11 + "┬" + "─"*9 + "┬" + "─"*14 + "┐")
print(hdr)
print("  ├" + "─"*38 + "┼" + "─"*9 + "┼" + "─"*9 + "┼" + "─"*14 + "┼" + "─"*10 + "┼" + "─"*11 + "┼" + "─"*9 + "┼" + "─"*14 + "┤")

for k, cfg in CONFIGS.items():
    r = results[k]
    lbl = cfg["label"]
    row = f"  │ {lbl:<36} │ {r['participated']:>7,} │ {r['win_rate']:>6.1f}% │ {r['total_pnl']:>+11,.2f} │ {r['roi']:>+7.2f}% │ ${r['max_drawdown']:>8,.2f} │ {r['sharpe']:>7.4f} │ ${r['final_balance']:>11,.2f} │"
    print(row)
print("  └" + "─"*38 + "┴" + "─"*9 + "┴" + "─"*9 + "┴" + "─"*14 + "┴" + "─"*10 + "┴" + "─"*11 + "┴" + "─"*9 + "┴" + "─"*14 + "┘")

print("\n  [2] DETALHAMENTO DE MÓDULOS POR ESTRATÉGIA:")
print("  ┌" + "─"*38 + "┬" + "─"*12 + "┬" + "─"*12 + "┬" + "─"*12 + "┬" + "─"*12 + "┬" + "─"*14 + "┐")
print(f"  │ {'Estratégia':<36} │ {'Deadband WR':>10} │ {'Streak WR':>10} │ {'TP Acionados':>10} │ {'TP Salvou':>10} │ {'Hedges Feitos':>12} │")
print("  ├" + "─"*38 + "┼" + "─"*12 + "┼" + "─"*12 + "┼" + "─"*12 + "┼" + "─"*12 + "┼" + "─"*14 + "┤")
for k, cfg in CONFIGS.items():
    r = results[k]
    stk_wr_str = f"{r['streak_wr']:.1f}%" if r['streak_trades'] > 0 else "N/A"
    print(f"  │ {cfg['label']:<36} │ {r['deadband_wr']:>9.1f}% │ {stk_wr_str:>10} │ {r['tp_trades']:>10,} │ {r['tp_saved_losses']:>10,} │ {r['hedge_trades']:>12,} │")
print("  └" + "─"*38 + "┴" + "─"*12 + "┴" + "─"*12 + "┴" + "─"*12 + "┴" + "─"*12 + "┴" + "─"*14 + "┘")

print("\n  [3] P&L ANUAL DETALHADO:")
all_years = sorted(list(base["yearly_pnl"].keys()))
y_hdr = f"  │ {'Ano':<6} │" + "".join([f" {k[:16]:>17} │" for k in CONFIGS.keys()])
print("  ┌" + "─"*8 + "┬" + "─"*19 * len(CONFIGS) + "┐")
print(y_hdr)
print("  ├" + "─"*8 + "┼" + "─"*19 * len(CONFIGS) + "┤")
for yr in all_years:
    row = f"  │ {yr:<6} │"
    for k in CONFIGS.keys():
        val = results[k]["yearly_pnl"].get(yr, 0.0)
        row += f" {val:>+16,.2f} │"
    print(row)
print("  └" + "─"*8 + "┴" + "─"*19 * len(CONFIGS) + "┘")

print("\n" + "=" * 115)
print("  🏆 ANÁLISE DE IMPACTO E CONCLUSÕES")
print("=" * 115)

for k, cfg in CONFIGS.items():
    if k == baseline_key:
        continue
    r = results[k]
    diff_pnl = r["total_pnl"] - base["total_pnl"]
    diff_wr = r["win_rate"] - base["win_rate"]
    diff_dd = r["max_drawdown"] - base["max_drawdown"]
    diff_sharpe = r["sharpe"] - base["sharpe"]
    print(f"\n  ▶ {cfg['label']}:")
    print(f"     P&L Total:     ${r['total_pnl']:>+11,.2f}  (Diferença vs Atual: {diff_pnl:+,.2f} USDC)")
    print(f"     Win Rate:      {r['win_rate']:>6.1f}%      (Diferença vs Atual: {diff_wr:+.1f}pp)")
    print(f"     Max Drawdown:  ${r['max_drawdown']:>8,.2f}      (Diferença vs Atual: {diff_dd:+,.2f} USDC)")
    print(f"     Sharpe Diário: {r['sharpe']:>7.4f}      (Diferença vs Atual: {diff_sharpe:+.4f})")
    print(f"     Saldo Final:   ${r['final_balance']:>11,.2f}")

print("\n" + "=" * 115 + "\n")

# Salvar resultados completos
with open(os.path.join(BASE_DIR, "backtest_5y_comparativo.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
print("[OK] Resultados salvos em 'backtest_5y_comparativo.json'.\n")
