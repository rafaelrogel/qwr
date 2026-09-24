"""
=============================================================================
BACKTEST HISTÓRICO 5 ANOS: ENGINE BTC5M UP-OR-DOWN + ANÁLISE JEV (TypeSafe)
=============================================================================
- Dados: Binance BTCUSDT klines 1m (últimos 5 anos ≈ 2.6M velas)
- Engine: Réplica fiel do live_trader_5m.py (Deadband, Streak, TP, Hedge, Sweeper)
- Stake Progressivo: Começa em $1.00, +$0.50 a cada +$10 de lucro acumulado
- Banca Inicial: $21.00 USDC
- Análise Final: Jev (TypeSafe AI) para avaliação probabilística
=============================================================================
"""

import urllib.request
import json
import time
import os
import sys
import ssl
from datetime import datetime, timezone

# Garante UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "btc_1m_5y_cache.json")
RESULTS_FILE = os.path.join(BASE_DIR, "backtest_5y_results.json")

# ===================== JEV / TYPESAFE CONFIG =====================
from dotenv import load_dotenv; load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

# ===================== PARÂMETROS DO ENGINE =====================
INITIAL_BALANCE = 21.00
BASE_STAKE = 1.00
STAKE_INCREMENT = 0.50       # +$0.50 de stake
PROFIT_STEP = 10.00          # a cada +$10 de lucro acumulado
DEADBAND = 15.0
PRIMARY_MIN_PRICE = 0.35
PRIMARY_MAX_PRICE = 0.65     # Audit: <= 0.62 ideal, 0.65 margem
STREAK_MAX_PRICE = 0.52
TP_THRESHOLD = 0.86
HEDGE_DELTA = -18.0
HEDGE_MAX_PRICE = 0.50
SWEEPER_DELTA = 25.0
SWEEPER_MIN_PRICE = 0.55
SWEEPER_MAX_PRICE = 0.965

print("\n" + "=" * 90)
print("  BACKTEST HISTÓRICO 5 ANOS: BTC5M UP-OR-DOWN ENGINE")
print("  Banca Inicial: $21.00 | Stake Progressivo: +$0.50 a cada +$10 lucro")
print("=" * 90)

# ===================== DOWNLOAD DE DADOS =====================
def download_binance_klines_5y():
    """Baixa ~2.6 milhões de velas de 1 minuto da Binance (5 anos)"""

    # Checar cache
    if os.path.exists(CACHE_FILE):
        print(f"\n[*] Cache encontrado: {CACHE_FILE}")
        fsize_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
        print(f"    Tamanho: {fsize_mb:.1f} MB")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"    Velas carregadas do cache: {len(data):,}")
        if len(data) > 2_000_000:
            print(f"[OK] Cache válido com {len(data):,} velas de 1m.")
            return data
        else:
            print(f"[!] Cache incompleto ({len(data):,} velas). Re-baixando...")

    now_ms = int(time.time() * 1000)
    five_years_ms = 5 * 365 * 24 * 3600 * 1000
    start_ms = now_ms - five_years_ms
    start_ms = (start_ms // 60000) * 60000  # Alinhar ao minuto

    all_klines = []
    curr_start = start_ms
    batch_count = 0
    total_expected = five_years_ms // 60000  # ~2.628.000

    print(f"\n[*] Baixando ~{total_expected:,} velas de 1m da Binance BTCUSDT (5 anos)...")
    print(f"    De: {datetime.utcfromtimestamp(start_ms/1000).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"    Até: {datetime.utcfromtimestamp(now_ms/1000).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"    Estimativa: ~{total_expected // 1000 + 1} batches de 1000 velas\n")

    ctx = ssl.create_default_context()

    while curr_start < now_ms:
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={curr_start}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        retries = 0
        while retries < 5:
            try:
                with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                    klines = json.loads(r.read().decode())
                    if not klines:
                        curr_start = now_ms  # fim
                        break
                    all_klines.extend(klines)
                    curr_start = klines[-1][0] + 60000
                    batch_count += 1
                    if batch_count % 50 == 0:
                        pct = len(all_klines) / total_expected * 100
                        print(f"    [{pct:5.1f}%] {len(all_klines):>10,} velas baixadas ({batch_count:,} batches)...")
                    time.sleep(0.02)  # Rate limit
                    break
            except Exception as e:
                retries += 1
                if retries < 5:
                    wait = min(2 ** retries, 10)
                    time.sleep(wait)
                else:
                    print(f"    [ERRO] Falha após 5 tentativas em ts={curr_start}: {e}")
                    curr_start += 1000 * 60000  # Pular 1000 minutos
                    break

    print(f"\n[OK] Download completo: {len(all_klines):,} velas de 1m.")

    # Salvar cache
    print(f"[*] Salvando cache em {CACHE_FILE}...")
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_klines, f)
    fsize_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
    print(f"[OK] Cache salvo ({fsize_mb:.1f} MB).\n")

    return all_klines


# ===================== PRECIFICAÇÃO CLOB SIMULADA =====================
def get_token_price(delta_usd: float, elapsed_sec: int) -> float:
    """Modelo de precificação da CLOB Polymarket"""
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.98, prob))


# ===================== CÁLCULO DO STAKE PROGRESSIVO =====================
def get_current_stake(total_pnl: float) -> float:
    """Calcula stake baseado no lucro acumulado: $1.00 base + $0.50 a cada +$10"""
    if total_pnl <= 0:
        return BASE_STAKE
    increments = int(total_pnl // PROFIT_STEP)
    return round(BASE_STAKE + increments * STAKE_INCREMENT, 2)


# ===================== ENGINE DE SIMULAÇÃO =====================
def run_5y_simulation(all_klines_raw):
    """Executa simulação completa do engine sobre 5 anos de dados"""

    # Converter para dict indexado por timestamp (segundos)
    print("[*] Processando e indexando velas de 1 minuto...")
    candles_1m = {}
    for k in all_klines_raw:
        ts_sec = int(k[0]) // 1000
        candles_1m[ts_sec] = {
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "tr": max(
                float(k[2]) - float(k[3]),
                abs(float(k[2]) - float(k[1])),
                abs(float(k[3]) - float(k[1]))
            )
        }

    all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])
    print(f"[OK] {len(all_5m_ts):,} janelas de 5 minutos disponíveis.\n")

    # Pre-computar histórico 5m
    print("[*] Pré-computando histórico de velas 5m...")
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
    print(f"[OK] {len(history_5m):,} velas de 5m pré-computadas.\n")

    # Métricas Globais
    total_cycles = 0
    participated_cycles = 0
    skipped_cycles = 0
    wins = 0
    losses = 0
    defenses = 0

    # Módulos
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

    current_balance = INITIAL_BALANCE
    peak_balance = INITIAL_BALANCE
    max_drawdown = 0.0

    # Tracking por período
    monthly_pnl = {}
    yearly_pnl = {}
    daily_pnl = {}
    daily_stats = {}

    # Tracking de stakes
    stake_history = []
    balance_milestones = []

    print("[*] Iniciando simulação do engine sobre 5 anos...\n")
    sim_start = time.time()
    report_interval = len(all_5m_ts) // 20  # Report a cada 5%

    for idx, w_ts in enumerate(all_5m_ts):
        if idx < 16:
            continue

        # Progress
        if report_interval > 0 and idx % report_interval == 0 and idx > 0:
            pct = idx / len(all_5m_ts) * 100
            elapsed = time.time() - sim_start
            dt_str = datetime.utcfromtimestamp(w_ts).strftime("%Y-%m-%d")
            cur_stake = get_current_stake(total_pnl)
            print(f"    [{pct:5.1f}%] {dt_str} | Saldo: ${current_balance:,.2f} | P&L: {total_pnl:+,.2f} | Stake: ${cur_stake:.2f} | Trades: {participated_cycles:,} | {elapsed:.0f}s")

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

        if day_str not in daily_pnl:
            daily_pnl[day_str] = 0.0
            daily_stats[day_str] = {"trades": 0, "wins": 0, "losses": 0, "stake": 0.0, "payout": 0.0}
        if month_str not in monthly_pnl:
            monthly_pnl[month_str] = 0.0
        if year_str not in yearly_pnl:
            yearly_pnl[year_str] = 0.0

        strike = c0["open"]
        final_spot = c4["close"]
        final_delta = final_spot - strike
        winner = "UP" if final_spot >= strike else "DOWN"

        # Stake progressivo
        current_stake_multiplier = get_current_stake(total_pnl)

        # PASSO 1: Leitura aos 135s
        spot_135s = (c2["open"] + c2["close"]) / 2.0
        delta_135s = spot_135s - strike

        # ATR Horário
        prior_ts = all_5m_ts[max(0, idx - 12):idx]
        hourly_atr_vals = [history_5m[t]["tr"] for t in prior_ts if t in history_5m]
        hourly_atr = sum(hourly_atr_vals) / len(hourly_atr_vals) if hourly_atr_vals else 1.0

        # Streak Snapper
        prior_4_ts = all_5m_ts[max(0, idx - 4):idx]
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

        # Decisão de Entrada
        should_enter_primary = False
        target_side = None
        is_streak_trade = False

        if has_streak:
            target_side = streak_reversal
            is_streak_trade = True
            should_enter_primary = True
        elif abs(delta_135s) >= DEADBAND:
            target_side = "UP" if delta_135s > 0 else "DOWN"
            should_enter_primary = True

        # Preço CLOB
        p_up_135 = get_token_price(delta_135s, 135)
        p_down_135 = 1.0 - p_up_135
        entry_price = p_up_135 if target_side == "UP" else p_down_135

        # Filtros de Preço
        if should_enter_primary:
            if is_streak_trade and entry_price > STREAK_MAX_PRICE:
                should_enter_primary = False
            elif entry_price < PRIMARY_MIN_PRICE or entry_price > PRIMARY_MAX_PRICE:
                should_enter_primary = False

        # Verificar se temos saldo suficiente
        if should_enter_primary and current_balance < current_stake_multiplier:
            should_enter_primary = False  # Sem saldo

        # PASSO 2: Execução e Monitoramento
        has_primary = False
        primary_shares = 0.0
        sold_early_tp = False
        tp_payout = 0.0
        hedged = False
        hedge_shares = 0.0
        hedge_side = None
        cycle_stake = 0.0
        cycle_payout = 0.0

        if should_enter_primary:
            has_primary = True
            primary_trades += 1
            cycle_stake += current_stake_multiplier
            primary_shares = current_stake_multiplier / entry_price
            if is_streak_trade:
                streak_snapper_trades += 1

            # Preço aos 200s
            spot_200s = (c3["open"] + c3["close"]) / 2.0
            delta_200s = spot_200s - strike
            p_target_200s = get_token_price(
                delta_200s if target_side == "UP" else -delta_200s, 200
            )

            # SirMartingale TP
            if p_target_200s >= TP_THRESHOLD:
                sold_early_tp = True
                sirmartingale_tp_trades += 1
                tp_payout = round(primary_shares * 0.86, 2)
                cycle_payout += tp_payout
                has_primary = False

            # Bonereaper Hedge
            elif not sold_early_tp:
                favored_delta = delta_200s if target_side == "UP" else -delta_200s
                if favored_delta <= HEDGE_DELTA:
                    hedge_side = "DOWN" if target_side == "UP" else "UP"
                    p_hedge = 1.0 - p_target_200s
                    if p_hedge <= HEDGE_MAX_PRICE:
                        hedged = True
                        bonereaper_hedge_trades += 1
                        hedge_stake = current_stake_multiplier
                        if current_balance >= cycle_stake + hedge_stake:
                            cycle_stake += hedge_stake
                            hedge_shares = hedge_stake / p_hedge

        # PASSO 3: Sweeper
        sweeper_executed = False
        sweeper_shares = 0.0
        sweeper_side = None

        if not has_primary and not hedged and not sold_early_tp:
            spot_255s = c4["open"]
            delta_255s = spot_255s - strike
            if abs(delta_255s) >= SWEEPER_DELTA:
                sweeper_side = "UP" if delta_255s > 0 else "DOWN"
                sweeper_price = get_token_price(abs(delta_255s), 255)
                if SWEEPER_MIN_PRICE <= sweeper_price <= SWEEPER_MAX_PRICE:
                    if current_balance >= current_stake_multiplier:
                        sweeper_executed = True
                        sweeper_trades += 1
                        cycle_stake += current_stake_multiplier
                        sweeper_shares = current_stake_multiplier / sweeper_price

        # PASSO 4: Liquidação
        if cycle_stake == 0.0:
            skipped_cycles += 1
            continue

        participated_cycles += 1
        daily_stats[day_str]["trades"] += 1
        daily_stats[day_str]["stake"] += cycle_stake

        # Apuração
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
        monthly_pnl[month_str] += cycle_pnl
        yearly_pnl[year_str] += cycle_pnl
        daily_stats[day_str]["payout"] += cycle_payout

        # Drawdown
        if current_balance > peak_balance:
            peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown:
            max_drawdown = dd

        # Win/Loss
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

        # Milestones
        if current_balance > 0 and int(current_balance) % 50 == 0:
            if not balance_milestones or balance_milestones[-1]["balance"] != int(current_balance):
                balance_milestones.append({
                    "date": day_str,
                    "balance": round(current_balance, 2),
                    "pnl": round(total_pnl, 2),
                    "trades": participated_cycles,
                    "stake": current_stake_multiplier
                })

    sim_elapsed = time.time() - sim_start
    overall_wr = (wins / participated_cycles * 100) if participated_cycles > 0 else 0.0
    overall_roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0.0

    # Dias lucrativos vs prejuízo
    profitable_days = sum(1 for v in daily_pnl.values() if v > 0)
    loss_days = sum(1 for v in daily_pnl.values() if v < 0)
    neutral_days = sum(1 for v in daily_pnl.values() if v == 0)

    # Melhor e pior dia
    best_day = max(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ("N/A", 0)
    worst_day = min(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ("N/A", 0)

    # Melhor e pior mês
    best_month = max(monthly_pnl.items(), key=lambda x: x[1]) if monthly_pnl else ("N/A", 0)
    worst_month = min(monthly_pnl.items(), key=lambda x: x[1]) if monthly_pnl else ("N/A", 0)

    final_stake = get_current_stake(total_pnl)

    results = {
        "simulation_time_seconds": round(sim_elapsed, 1),
        "period": "5 anos",
        "initial_balance": INITIAL_BALANCE,
        "final_balance": round(current_balance, 2),
        "total_cycles": total_cycles,
        "participated": participated_cycles,
        "skipped": skipped_cycles,
        "wins": wins,
        "losses": losses,
        "defenses": defenses,
        "win_rate": round(overall_wr, 2),
        "total_stake": round(total_stake, 2),
        "total_payout": round(total_payout, 2),
        "total_pnl": round(total_pnl, 2),
        "roi": round(overall_roi, 2),
        "max_drawdown": round(max_drawdown, 2),
        "peak_balance": round(peak_balance, 2),
        "final_stake_size": final_stake,
        "profitable_days": profitable_days,
        "loss_days": loss_days,
        "neutral_days": neutral_days,
        "total_days": len(daily_pnl),
        "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2)},
        "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2)},
        "best_month": {"month": best_month[0], "pnl": round(best_month[1], 2)},
        "worst_month": {"month": worst_month[0], "pnl": round(worst_month[1], 2)},
        "yearly_pnl": {k: round(v, 2) for k, v in sorted(yearly_pnl.items())},
        "monthly_pnl": {k: round(v, 2) for k, v in sorted(monthly_pnl.items())},
        "primary_trades": primary_trades,
        "primary_wins": primary_wins,
        "primary_wr": round((primary_wins / primary_trades * 100) if primary_trades > 0 else 0, 1),
        "sirmartingale_tp": sirmartingale_tp_trades,
        "bonereaper_hedge": bonereaper_hedge_trades,
        "sweeper_trades": sweeper_trades,
        "sweeper_wins": sweeper_wins,
        "sweeper_wr": round((sweeper_wins / sweeper_trades * 100) if sweeper_trades > 0 else 0, 1),
        "streak_trades": streak_snapper_trades,
        "streak_wins": streak_snapper_wins,
        "streak_wr": round((streak_snapper_wins / streak_snapper_trades * 100) if streak_snapper_trades > 0 else 0, 1),
        "balance_milestones": balance_milestones[:20],  # Top 20
    }

    return results


# ===================== ANÁLISE JEV (TypeSafe AI) =====================
def run_jev_analysis(results: dict):
    """Envia os resultados para o Jev/TypeSafe para análise probabilística"""
    print("\n" + "=" * 90)
    print("  [JEV] ANÁLISE PROBABILÍSTICA VIA TYPESAFE AI")
    print("=" * 90)

    # Preparar estado para o Jev
    state = {
        "strategy": "BTC 5-Minute Up-or-Down Binary Options Engine",
        "backtest_period": "5 years",
        "initial_capital": results["initial_balance"],
        "final_capital": results["final_balance"],
        "total_pnl": results["total_pnl"],
        "roi_percent": results["roi"],
        "win_rate_percent": results["win_rate"],
        "total_trades": results["participated"],
        "max_drawdown": results["max_drawdown"],
        "peak_balance": results["peak_balance"],
        "profitable_days_ratio": f"{results['profitable_days']}/{results['total_days']}",
        "stake_progression": f"${BASE_STAKE} base, +${STAKE_INCREMENT} per +${PROFIT_STEP} profit",
        "final_stake_size": results["final_stake_size"],
        "yearly_performance": results["yearly_pnl"],
        "best_day_pnl": results["best_day"]["pnl"],
        "worst_day_pnl": results["worst_day"]["pnl"],
        "modules": {
            "primary_entry": {"trades": results["primary_trades"], "win_rate": results["primary_wr"]},
            "take_profit": {"trades": results["sirmartingale_tp"]},
            "hedge": {"trades": results["bonereaper_hedge"]},
            "sweeper": {"trades": results["sweeper_trades"], "win_rate": results["sweeper_wr"]},
            "streak_snapper": {"trades": results["streak_trades"], "win_rate": results["streak_wr"]}
        }
    }

    # Perguntas para o Jev
    questions = {
        "strategy_viability": {
            "type": "choice",
            "instructions": "Based on these 5-year backtest results, evaluate the overall viability of this trading strategy for real money deployment.",
            "options": {
                "highly_viable": "Highly viable - strong consistent returns with manageable risk",
                "viable_with_caveats": "Viable with caveats - profitable but has notable risks",
                "marginal": "Marginal - barely profitable, high risk of loss in live conditions",
                "not_viable": "Not viable - expected to lose money in live trading"
            }
        },
        "risk_level": {
            "type": "score",
            "instructions": "Rate the overall risk level of this strategy from 1 (very low risk) to 5 (very high risk), considering drawdown, win rate, and consistency.",
            "levels": ["Very Low Risk", "Low Risk", "Moderate Risk", "High Risk", "Very High Risk"]
        },
        "overfitting_concern": {
            "type": "noul",
            "instructions": "Is there a significant concern that this strategy is overfit to historical data and would underperform in live trading? Consider the 5-year sample size, win rate consistency, and strategy complexity."
        },
        "stake_scaling_appropriate": {
            "type": "noul",
            "instructions": "Is the progressive stake scaling (+$0.50 per +$10 profit) appropriate and sustainable for this strategy's risk profile?"
        },
        "recommendation": {
            "type": "choice",
            "instructions": "What is your primary recommendation for the trader?",
            "options": {
                "scale_up": "Scale up capital allocation - strategy shows strong edge",
                "maintain": "Maintain current approach - strategy is working well",
                "reduce_risk": "Reduce risk parameters - strategy is too aggressive",
                "paper_trade": "Switch to paper trading - need more validation",
                "stop": "Stop trading - strategy does not have a real edge"
            }
        }
    }

    payload = json.dumps({
        "model": JEV_MODEL,
        "state": json.dumps(state),
        "questions": questions
    }).encode("utf-8")

    req = urllib.request.Request(
        JEV_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {JEV_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "PolyMarketBot/1.0"
        },
        method="POST"
    )

    try:
        print("[*] Enviando dados para Jev/TypeSafe AI...")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            jev_response = json.loads(resp.read().decode())
            print("[OK] Análise Jev recebida com sucesso!\n")
            return jev_response
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"[!] Jev HTTP Error {e.code}: {e.reason}")
        print(f"    Body: {body[:500]}")
        return {"error": f"HTTP {e.code}: {e.reason}", "body": body[:500]}
    except Exception as e:
        print(f"[!] Erro ao conectar com Jev: {e}")
        return {"error": str(e)}


# ===================== RELATÓRIO FINAL =====================
def print_report(r: dict, jev: dict):
    """Imprime relatório completo e formatado"""
    print("\n" + "=" * 90)
    print("  RELATÓRIO QUANTITATIVO DEFINITIVO: ENGINE COMPLETO (ÚLTIMOS 5 ANOS)")
    print("=" * 90)
    print(f"  Tempo de Simulação: {r['simulation_time_seconds']}s")
    print(f"  * Total de Ciclos de 5m no Período:    {r['total_cycles']:,} velas")
    print(f"  * Ciclos com Trade Operado:            {r['participated']:,} ({r['participated']/max(r['total_cycles'],1)*100:.1f}%)")
    print(f"  * Ciclos Filtrados (Preservou Capital): {r['skipped']:,} ({r['skipped']/max(r['total_cycles'],1)*100:.1f}%)")
    print("-" * 90)
    print(f"  [+] RESULTADO FINANCEIRO GLOBAL (STAKE PROGRESSIVO):")
    print(f"     - Banca Inicial:                    ${r['initial_balance']:.2f} USDC")
    print(f"     - Saldo Final:                      ${r['final_balance']:,.2f} USDC")
    print(f"     - Volume Total Apostado:            ${r['total_stake']:,.2f} USDC")
    print(f"     - Payouts Totais Resgatados:        ${r['total_payout']:,.2f} USDC")
    print(f"     - Lucro Líquido Real (P&L):         {r['total_pnl']:+,.2f} USDC")
    print(f"     - Retorno sobre o Volume (ROI):     {r['roi']:+.2f}%")
    print(f"     - Retorno sobre Banca Inicial ($21): {(r['total_pnl'] / INITIAL_BALANCE * 100):+,.1f}%")
    print(f"     - Drawdown Máximo:                  ${r['max_drawdown']:.2f} USDC")
    print(f"     - Pico de Saldo:                    ${r['peak_balance']:,.2f} USDC")
    print(f"     - Stake Atual (Final):              ${r['final_stake_size']:.2f} USDC")
    print("-" * 90)
    print(f"  [+] PERFORMANCE E TAXA DE ACERTO:")
    print(f"     - Vitórias / Lucros:                {r['wins']:,} trades")
    print(f"     - Derrotas:                         {r['losses']:,} trades")
    print(f"     - Defesas Hedge:                    {r['defenses']:,} trades")
    print(f"     - TAXA DE ACERTO GLOBAL:            {r['win_rate']:.1f}%")
    print("-" * 90)
    print(f"  [+] DESDOBRAMENTO MÓDULO POR MÓDULO:")
    print(f"     1. Entrada Primária (135s):         {r['primary_trades']:,} trades | WR: {r['primary_wr']:.1f}% ({r['primary_wins']:,}V)")
    print(f"     2. SirMartingale (Take-Profit):     {r['sirmartingale_tp']:,} trades travados com lucro antecipado")
    print(f"     3. Bonereaper (Hedge Defensivo):    {r['bonereaper_hedge']:,} operações de contenção de risco")
    print(f"     4. BTC5MScour (Sweeper 255s):       {r['sweeper_trades']:,} trades | WR: {r['sweeper_wr']:.1f}% ({r['sweeper_wins']:,}V)")
    print(f"     5. Streak Snapper (Reversão 3x):    {r['streak_trades']:,} trades | WR: {r['streak_wr']:.1f}% ({r['streak_wins']:,}V)")
    print("-" * 90)
    print(f"  [+] CONSISTÊNCIA DIÁRIA:")
    print(f"     - Dias com Lucro:                   {r['profitable_days']:,} ({r['profitable_days']/max(r['total_days'],1)*100:.1f}%)")
    print(f"     - Dias com Prejuízo:                {r['loss_days']:,} ({r['loss_days']/max(r['total_days'],1)*100:.1f}%)")
    print(f"     - Dias Neutros:                     {r['neutral_days']:,}")
    print(f"     - Melhor Dia:                       {r['best_day']['date']} ({r['best_day']['pnl']:+.2f} USDC)")
    print(f"     - Pior Dia:                         {r['worst_day']['date']} ({r['worst_day']['pnl']:+.2f} USDC)")
    print(f"     - Melhor Mês:                       {r['best_month']['month']} ({r['best_month']['pnl']:+,.2f} USDC)")
    print(f"     - Pior Mês:                         {r['worst_month']['month']} ({r['worst_month']['pnl']:+,.2f} USDC)")
    print("-" * 90)
    print(f"  [+] P&L ANUAL:")
    cum = 0
    for year, pnl in sorted(r["yearly_pnl"].items()):
        cum += pnl
        status = "[+]" if pnl > 0 else ("[-]" if pnl < 0 else "[=]")
        print(f"     {status} {year}: {pnl:+10,.2f} USDC (Acumulado: {cum:+10,.2f} USDC)")
    print("-" * 90)
    print(f"  [+] P&L MENSAL (últimos 12 meses):")
    sorted_months = sorted(r["monthly_pnl"].items())
    for month, pnl in sorted_months[-12:]:
        status = "[+]" if pnl > 0 else ("[-]" if pnl < 0 else "[=]")
        print(f"     {status} {month}: {pnl:+8,.2f} USDC")

    # Jev Analysis
    print("\n" + "=" * 90)
    print("  [JEV/TYPESAFE] ANÁLISE PROBABILÍSTICA DO ENGINE")
    print("=" * 90)
    if "error" in jev:
        print(f"  [!] Jev não disponível: {jev['error']}")
        if "body" in jev:
            print(f"  [!] Detalhes: {jev['body']}")
        print("  [i] O backtest quantitativo acima permanece válido independentemente do Jev.")
    else:
        print(f"  Resposta Jev: {json.dumps(jev, indent=2, ensure_ascii=False)}")

    print("\n" + "=" * 90)
    print(f"  VEREDITO FINAL:")
    print(f"  Iniciando com ${INITIAL_BALANCE:.2f} USDC e stake progressivo,")
    print(f"  após 5 anos de operação contínua, o saldo seria:")
    print(f"  >>> ${r['final_balance']:,.2f} USDC <<<")
    print(f"  Lucro líquido: {r['total_pnl']:+,.2f} USDC ({r['total_pnl']/INITIAL_BALANCE*100:+,.1f}% sobre banca inicial)")
    print("=" * 90 + "\n")


# ===================== MAIN =====================
if __name__ == "__main__":
    # 1. Download dados
    raw_klines = download_binance_klines_5y()

    # 2. Simulação
    results = run_5y_simulation(raw_klines)

    # 3. Salvar resultados
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Resultados salvos em '{RESULTS_FILE}'.")

    # 4. Análise Jev
    jev_result = run_jev_analysis(results)

    # 5. Relatório
    print_report(results, jev_result)

    print("[FIM] Backtest de 5 anos concluído com sucesso.")
