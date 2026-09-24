"""
=============================================================================
BACKTEST HISTÓRICO 5 ANOS (V2): ENGINE BTC5M UP-OR-DOWN + ANÁLISE JEV
=============================================================================
CORREÇÕES V2:
- Remove trava de saldo: simula P&L teórico contínuo (sem "falência")
- Stake progressivo aplicado sobre lucro acumulado (quando positivo)
- Corrigido formato da API Jev (campo 'criteria' em vez de 'instructions')
- Cache reutilizado do download anterior
=============================================================================
"""

import urllib.request
import json
import time
import os
import sys
import ssl
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "btc_1m_5y_cache.json")
RESULTS_FILE = os.path.join(BASE_DIR, "backtest_5y_results_v2.json")

# ===================== JEV / TYPESAFE CONFIG =====================
from dotenv import load_dotenv; load_dotenv()
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

# ===================== PARÂMETROS DO ENGINE =====================
INITIAL_BALANCE = 21.00
BASE_STAKE = 1.00
STAKE_INCREMENT = 0.50
PROFIT_STEP = 10.00
MAX_STAKE = 5.00             # Cap máximo de stake para evitar explosão composta
DEADBAND = 15.0
PRIMARY_MIN_PRICE = 0.35
PRIMARY_MAX_PRICE = 0.65
STREAK_MAX_PRICE = 0.52
TP_THRESHOLD = 0.86
HEDGE_DELTA = -18.0
HEDGE_MAX_PRICE = 0.50
SWEEPER_DELTA = 25.0
SWEEPER_MIN_PRICE = 0.55
SWEEPER_MAX_PRICE = 0.965

print("\n" + "=" * 90)
print("  BACKTEST HISTÓRICO 5 ANOS (V2): BTC5M UP-OR-DOWN ENGINE")
print("  Banca Inicial: $21.00 | Stake Progressivo: +$0.50 a cada +$10 lucro")
print("  MODO: P&L Teórico Contínuo (sem trava de saldo)")
print("=" * 90)

# ===================== CARREGAR CACHE =====================
def load_cached_klines():
    if not os.path.exists(CACHE_FILE):
        print(f"[ERRO] Cache não encontrado: {CACHE_FILE}")
        print("       Execute primeiro o backtest_5y_jev.py para baixar os dados.")
        sys.exit(1)
    fsize_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
    print(f"\n[*] Carregando cache: {CACHE_FILE} ({fsize_mb:.1f} MB)...")
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[OK] {len(data):,} velas de 1m carregadas do cache.\n")
    return data

# ===================== PRECIFICAÇÃO CLOB SIMULADA =====================
def get_token_price(delta_usd: float, elapsed_sec: int) -> float:
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.98, prob))

# ===================== STAKE PROGRESSIVO =====================
def get_current_stake(total_pnl: float) -> float:
    """$1.00 base + $0.50 a cada +$10 de lucro acumulado (só quando positivo, cap em MAX_STAKE)"""
    if total_pnl <= 0:
        return BASE_STAKE
    increments = int(total_pnl // PROFIT_STEP)
    return min(round(BASE_STAKE + increments * STAKE_INCREMENT, 2), MAX_STAKE)

# ===================== ENGINE DE SIMULAÇÃO V2 =====================
def run_5y_simulation(all_klines_raw):
    # Indexar velas
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

    # Métricas
    total_cycles = 0
    participated_cycles = 0
    skipped_cycles = 0
    wins = 0
    losses = 0
    defenses = 0

    primary_trades = 0
    primary_wins = 0
    primary_losses = 0
    sirmartingale_tp_trades = 0
    bonereaper_hedge_trades = 0
    sweeper_trades = 0
    sweeper_wins = 0
    streak_snapper_trades = 0
    streak_snapper_wins = 0

    total_stake = 0.0
    total_payout = 0.0
    total_pnl = 0.0

    # V2: Saldo teórico SEM trava (pode ficar negativo teoricamente,
    # mas usamos para calcular stake progressivo apenas quando positivo)
    current_balance = INITIAL_BALANCE
    peak_balance = INITIAL_BALANCE
    max_drawdown = 0.0
    min_balance = INITIAL_BALANCE

    monthly_pnl = {}
    yearly_pnl = {}
    daily_pnl = {}
    daily_stats = {}
    quarterly_pnl = {}

    # Equity curve (amostragem diária)
    equity_curve = {}

    print("[*] Iniciando simulação V2 (sem trava de saldo) sobre 5 anos...\n")
    sim_start = time.time()
    report_interval = len(all_5m_ts) // 20

    for idx, w_ts in enumerate(all_5m_ts):
        if idx < 16:
            continue

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
        quarter_str = f"{year_str}-Q{(int(datetime.utcfromtimestamp(w_ts).strftime('%m'))-1)//3+1}"

        if day_str not in daily_pnl:
            daily_pnl[day_str] = 0.0
            daily_stats[day_str] = {"trades": 0, "wins": 0, "losses": 0, "stake": 0.0, "payout": 0.0}
        if month_str not in monthly_pnl:
            monthly_pnl[month_str] = 0.0
        if year_str not in yearly_pnl:
            yearly_pnl[year_str] = 0.0
        if quarter_str not in quarterly_pnl:
            quarterly_pnl[quarter_str] = 0.0

        strike = c0["open"]
        final_spot = c4["close"]
        winner = "UP" if final_spot >= strike else "DOWN"

        # Stake progressivo baseado no P&L acumulado
        current_stake_size = get_current_stake(total_pnl)

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

        # Preço CLOB simulado
        p_up_135 = get_token_price(delta_135s, 135)
        p_down_135 = 1.0 - p_up_135
        entry_price = p_up_135 if target_side == "UP" else p_down_135

        # Filtros de Preço (mantidos iguais ao live)
        if should_enter_primary:
            if is_streak_trade and entry_price > STREAK_MAX_PRICE:
                should_enter_primary = False
            elif entry_price < PRIMARY_MIN_PRICE or entry_price > PRIMARY_MAX_PRICE:
                should_enter_primary = False

        # V2: NÃO verificamos saldo - simulação teórica contínua

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
            cycle_stake += current_stake_size
            primary_shares = current_stake_size / entry_price
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
                        cycle_stake += current_stake_size
                        hedge_shares = current_stake_size / p_hedge

        # PASSO 3: Sweeper (desabilitado no live, mas testamos aqui para referência)
        sweeper_executed = False
        sweeper_shares = 0.0
        sweeper_side = None

        # NÃO executar sweeper pois está DESABILITADO no código live (SCOUR_ENABLED = False)
        # Mantemos apenas a entrada primária + TP + hedge (fiel ao live_trader_5m.py)

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
            else:
                primary_losses += 1

        if hedged:
            if hedge_side == winner:
                cycle_payout += round(hedge_shares * 1.00, 2)

        cycle_pnl = round(cycle_payout - cycle_stake, 2)
        total_stake += cycle_stake
        total_payout += cycle_payout
        total_pnl += cycle_pnl
        current_balance += cycle_pnl

        daily_pnl[day_str] += cycle_pnl
        monthly_pnl[month_str] += cycle_pnl
        yearly_pnl[year_str] += cycle_pnl
        quarterly_pnl[quarter_str] += cycle_pnl
        daily_stats[day_str]["payout"] += cycle_payout

        # Equity curve (uma entrada por dia)
        equity_curve[day_str] = round(current_balance, 2)

        # Drawdown
        if current_balance > peak_balance:
            peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown:
            max_drawdown = dd
        if current_balance < min_balance:
            min_balance = current_balance

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

    sim_elapsed = time.time() - sim_start
    overall_wr = (wins / participated_cycles * 100) if participated_cycles > 0 else 0.0
    overall_roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0.0

    profitable_days = sum(1 for v in daily_pnl.values() if v > 0)
    loss_days = sum(1 for v in daily_pnl.values() if v < 0)
    neutral_days = sum(1 for v in daily_pnl.values() if v == 0)
    trading_days = sum(1 for d, s in daily_stats.items() if s["trades"] > 0)

    best_day = max(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ("N/A", 0)
    worst_day = min(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ("N/A", 0)
    best_month = max(monthly_pnl.items(), key=lambda x: x[1]) if monthly_pnl else ("N/A", 0)
    worst_month = min(monthly_pnl.items(), key=lambda x: x[1]) if monthly_pnl else ("N/A", 0)

    # Média de trades por dia de trading
    avg_trades_per_day = participated_cycles / max(trading_days, 1)

    # Sharpe-like ratio (diário)
    daily_returns = [v for v in daily_pnl.values() if v != 0]
    if daily_returns:
        avg_daily = sum(daily_returns) / len(daily_returns)
        std_daily = (sum((x - avg_daily) ** 2 for x in daily_returns) / len(daily_returns)) ** 0.5
        sharpe_daily = (avg_daily / std_daily) if std_daily > 0 else 0
    else:
        avg_daily = 0
        std_daily = 0
        sharpe_daily = 0

    # Sequências máximas
    max_win_streak = 0
    max_loss_streak = 0
    curr_win = 0
    curr_loss = 0
    # Reconstruir sequências a partir de trades ordenados por dia
    for day in sorted(daily_stats.keys()):
        st = daily_stats[day]
        if st["trades"] > 0:
            day_pnl_val = daily_pnl[day]
            if day_pnl_val > 0:
                curr_win += 1
                curr_loss = 0
                max_win_streak = max(max_win_streak, curr_win)
            elif day_pnl_val < 0:
                curr_loss += 1
                curr_win = 0
                max_loss_streak = max(max_loss_streak, curr_loss)
            else:
                curr_win = 0
                curr_loss = 0

    final_stake = get_current_stake(total_pnl)

    results = {
        "version": "V2 - Sem trava de saldo, sweeper desabilitado (fiel ao live)",
        "simulation_time_seconds": round(sim_elapsed, 1),
        "period": "5 anos (~2.6M velas 1m)",
        "initial_balance": INITIAL_BALANCE,
        "final_balance": round(current_balance, 2),
        "total_cycles_5m": total_cycles,
        "participated": participated_cycles,
        "skipped": skipped_cycles,
        "participation_rate": round(participated_cycles / max(total_cycles, 1) * 100, 2),
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
        "min_balance": round(min_balance, 2),
        "final_stake_size": final_stake,
        "trading_days": trading_days,
        "profitable_days": profitable_days,
        "loss_days": loss_days,
        "neutral_days": neutral_days,
        "total_days": len(daily_pnl),
        "avg_trades_per_trading_day": round(avg_trades_per_day, 1),
        "avg_daily_pnl": round(avg_daily, 4),
        "std_daily_pnl": round(std_daily, 4),
        "sharpe_ratio_daily": round(sharpe_daily, 4),
        "max_win_streak_days": max_win_streak,
        "max_loss_streak_days": max_loss_streak,
        "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2)},
        "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2)},
        "best_month": {"month": best_month[0], "pnl": round(best_month[1], 2)},
        "worst_month": {"month": worst_month[0], "pnl": round(worst_month[1], 2)},
        "yearly_pnl": {k: round(v, 2) for k, v in sorted(yearly_pnl.items())},
        "quarterly_pnl": {k: round(v, 2) for k, v in sorted(quarterly_pnl.items())},
        "monthly_pnl": {k: round(v, 2) for k, v in sorted(monthly_pnl.items())},
        "primary_trades": primary_trades,
        "primary_wins": primary_wins,
        "primary_losses": primary_losses,
        "primary_wr": round((primary_wins / primary_trades * 100) if primary_trades > 0 else 0, 1),
        "sirmartingale_tp": sirmartingale_tp_trades,
        "bonereaper_hedge": bonereaper_hedge_trades,
        "streak_trades": streak_snapper_trades,
        "streak_wins": streak_snapper_wins,
        "streak_wr": round((streak_snapper_wins / streak_snapper_trades * 100) if streak_snapper_trades > 0 else 0, 1),
    }

    return results


# ===================== ANÁLISE JEV (TypeSafe AI) =====================
def run_jev_analysis(results: dict):
    print("\n" + "=" * 90)
    print("  [JEV] ANÁLISE PROBABILÍSTICA VIA TYPESAFE AI")
    print("=" * 90)

    state_str = json.dumps({
        "strategy": "BTC 5-Minute Up-or-Down Binary Options Engine (Polymarket)",
        "backtest_period": "5 years (2021-2026)",
        "initial_capital_usd": results["initial_balance"],
        "final_capital_usd": results["final_balance"],
        "total_pnl_usd": results["total_pnl"],
        "roi_percent": results["roi"],
        "win_rate_percent": results["win_rate"],
        "total_trades": results["participated"],
        "max_drawdown_usd": results["max_drawdown"],
        "peak_balance_usd": results["peak_balance"],
        "sharpe_ratio": results["sharpe_ratio_daily"],
        "profitable_days": results["profitable_days"],
        "loss_days": results["loss_days"],
        "trading_days": results["trading_days"],
        "yearly_pnl": results["yearly_pnl"],
        "primary_win_rate": results["primary_wr"],
        "max_win_streak": results["max_win_streak_days"],
        "max_loss_streak": results["max_loss_streak_days"],
    })

    # Jev API: formato correto com 'type' discriminador flat
    payload = json.dumps({
        "model": JEV_MODEL,
        "state": state_str,
        "questions": {
            "strategy_viability": {
                "type": "choice",
                "criteria": "Based on these 5-year backtest results (ROI, win rate, drawdown, Sharpe ratio), evaluate the overall viability of this trading strategy for real money deployment.",
                "options": {
                    "highly_viable": "Highly viable with strong consistent returns",
                    "viable_with_caveats": "Viable but has notable risks to manage",
                    "marginal": "Marginal profitability with high risk",
                    "not_viable": "Not viable for real money trading"
                }
            },
            "risk_level": {
                "type": "score",
                "criteria": "Rate the overall risk level considering max drawdown, win rate consistency, and the Sharpe ratio.",
                "levels": ["Very Low Risk", "Low Risk", "Moderate Risk", "High Risk", "Very High Risk"]
            },
            "overfitting_risk": {
                "type": "noul",
                "criteria": "Is there significant risk that this strategy is overfit to historical data and would underperform in live trading?"
            },
            "stake_scaling_ok": {
                "type": "noul",
                "criteria": "Is the progressive stake scaling (plus 0.50 dollars per 10 dollars profit, capped at 5 dollars) appropriate and sustainable for this risk profile?"
            },
            "recommendation": {
                "type": "choice",
                "criteria": "What is the best course of action for the trader based on these results?",
                "options": {
                    "scale_up": "Scale up capital - strategy has a real edge",
                    "maintain": "Maintain current approach and parameters",
                    "reduce_risk": "Reduce risk - strategy is too aggressive",
                    "paper_trade": "Switch to paper trading for more validation",
                    "stop": "Stop trading - no real edge detected"
                }
            }
        }
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
        print(f"    Body: {body[:800]}")
        return {"error": f"HTTP {e.code}: {e.reason}", "body": body[:800]}
    except Exception as e:
        print(f"[!] Erro ao conectar com Jev: {e}")
        return {"error": str(e)}


# ===================== RELATÓRIO FINAL =====================
def print_report(r: dict, jev: dict):
    print("\n" + "=" * 90)
    print("  RELATÓRIO QUANTITATIVO DEFINITIVO V2: ENGINE COMPLETO (ÚLTIMOS 5 ANOS)")
    print("=" * 90)
    print(f"  Versão: {r['version']}")
    print(f"  Tempo de Simulação: {r['simulation_time_seconds']}s")
    print(f"  * Total de Ciclos de 5m no Período:    {r['total_cycles_5m']:,} velas")
    print(f"  * Ciclos com Trade Operado:            {r['participated']:,} ({r['participation_rate']:.2f}%)")
    print(f"  * Ciclos Filtrados (Preservou Capital): {r['skipped']:,}")
    print("-" * 90)
    print(f"  [+] RESULTADO FINANCEIRO GLOBAL (STAKE PROGRESSIVO):")
    print(f"     - Banca Inicial:                    ${r['initial_balance']:.2f} USDC")
    print(f"     - SALDO FINAL:                      ${r['final_balance']:,.2f} USDC")
    print(f"     - Volume Total Apostado:            ${r['total_stake']:,.2f} USDC")
    print(f"     - Payouts Totais Resgatados:        ${r['total_payout']:,.2f} USDC")
    print(f"     - LUCRO LÍQUIDO REAL (P&L):         {r['total_pnl']:+,.2f} USDC")
    print(f"     - Retorno sobre Volume (ROI):       {r['roi']:+.2f}%")
    print(f"     - Retorno sobre Banca ($21):        {(r['total_pnl'] / INITIAL_BALANCE * 100):+,.1f}%")
    print(f"     - Drawdown Máximo:                  ${r['max_drawdown']:.2f} USDC")
    print(f"     - Pico de Saldo:                    ${r['peak_balance']:,.2f} USDC")
    print(f"     - Mínimo de Saldo:                  ${r['min_balance']:,.2f} USDC")
    print(f"     - Stake Final (Progressivo):        ${r['final_stake_size']:.2f} USDC")
    print("-" * 90)
    print(f"  [+] PERFORMANCE E TAXA DE ACERTO:")
    print(f"     - Vitórias:                         {r['wins']:,} trades")
    print(f"     - Derrotas:                         {r['losses']:,} trades")
    print(f"     - Defesas Hedge:                    {r['defenses']:,} trades")
    print(f"     - TAXA DE ACERTO GLOBAL:            {r['win_rate']:.1f}%")
    print(f"     - Dias com Trade:                   {r['trading_days']:,} dias")
    print(f"     - Média Trades/Dia:                 {r['avg_trades_per_trading_day']:.1f}")
    print(f"     - Sharpe Ratio (Diário):            {r['sharpe_ratio_daily']:.4f}")
    print(f"     - Maior Sequência de Vitórias:      {r['max_win_streak_days']} dias")
    print(f"     - Maior Sequência de Derrotas:      {r['max_loss_streak_days']} dias")
    print("-" * 90)
    print(f"  [+] DESDOBRAMENTO MÓDULO POR MÓDULO:")
    print(f"     1. Entrada Primária (135s):         {r['primary_trades']:,} trades | WR: {r['primary_wr']:.1f}% ({r['primary_wins']:,}V / {r['primary_losses']:,}D)")
    print(f"     2. SirMartingale (Take-Profit):     {r['sirmartingale_tp']:,} trades travados com lucro antecipado")
    print(f"     3. Bonereaper (Hedge Defensivo):    {r['bonereaper_hedge']:,} operações de contenção de risco")
    print(f"     4. Streak Snapper (Reversão 3x):    {r['streak_trades']:,} trades | WR: {r['streak_wr']:.1f}% ({r['streak_wins']:,}V)")
    print(f"     (Sweeper DESABILITADO - fiel ao código live)")
    print("-" * 90)
    print(f"  [+] CONSISTÊNCIA DIÁRIA:")
    print(f"     - Dias com Lucro:                   {r['profitable_days']:,} ({r['profitable_days']/max(r['trading_days'],1)*100:.1f}% dos dias de trade)")
    print(f"     - Dias com Prejuízo:                {r['loss_days']:,} ({r['loss_days']/max(r['trading_days'],1)*100:.1f}%)")
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
        bal_year = INITIAL_BALANCE + cum
        print(f"     {status} {year}: {pnl:+10,.2f} USDC | Acum: {cum:+10,.2f} | Saldo: ${bal_year:,.2f}")
    print("-" * 90)
    print(f"  [+] P&L TRIMESTRAL:")
    cum_q = 0
    for q, pnl in sorted(r["quarterly_pnl"].items()):
        cum_q += pnl
        status = "[+]" if pnl > 0 else ("[-]" if pnl < 0 else "[=]")
        print(f"     {status} {q}: {pnl:+8,.2f} USDC (Acum: {cum_q:+,.2f})")
    print("-" * 90)
    print(f"  [+] P&L MENSAL (todos os meses com trades):")
    for month, pnl in sorted(r["monthly_pnl"].items()):
        if pnl != 0:
            status = "[+]" if pnl > 0 else "[-]"
            print(f"     {status} {month}: {pnl:+8,.2f} USDC")

    # Jev
    print("\n" + "=" * 90)
    print("  [JEV/TYPESAFE] ANÁLISE PROBABILÍSTICA DO ENGINE")
    print("=" * 90)
    if "error" in jev:
        print(f"  [!] Jev retornou erro: {jev['error']}")
        if "body" in jev:
            print(f"  [!] Detalhes: {jev['body']}")
    else:
        # Parse Jev response
        print(f"\n  Resposta bruta Jev:")
        print(f"  {json.dumps(jev, indent=4, ensure_ascii=False)}")

    print("\n" + "=" * 90)
    print(f"  VEREDITO FINAL:")
    print(f"  Iniciando com ${INITIAL_BALANCE:.2f} USDC e stake progressivo,")
    print(f"  após 5 anos de operação contínua, o saldo seria:")
    print(f"")
    print(f"  >>> ${r['final_balance']:,.2f} USDC <<<")
    print(f"  >>> P&L Total: {r['total_pnl']:+,.2f} USDC ({r['total_pnl']/INITIAL_BALANCE*100:+,.1f}% sobre banca) <<<")
    print(f"")
    print("=" * 90 + "\n")


# ===================== MAIN =====================
if __name__ == "__main__":
    raw_klines = load_cached_klines()
    results = run_5y_simulation(raw_klines)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Resultados salvos em '{RESULTS_FILE}'.")

    jev_result = run_jev_analysis(results)

    print_report(results, jev_result)
    print("[FIM] Backtest V2 de 5 anos concluído com sucesso.")
