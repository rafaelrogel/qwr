"""
=============================================================================
BACKTEST HISTÓRICO 9 ANOS (2017-2026): KALSHI BTC 15-MINUTE (KXBTC15M)
=============================================================================
- Ativo: BTC/USDT (Binance 5m klines -> Janelas de 15m)
- Período: Agosto 2017 a Setembro 2026 (~957.000 velas de 5m = ~319.000 janelas de 15m)
- Banca Inicial: $35.00 USD ($10 depósito + $25 bônus Kalshi)
- Avaliação: T+450s (metade da vela de 15m)
- Deadband Dinâmico: 3.5 bps (0.035%) com piso de $25.00
- Teto de Cota: 60 centavos (breakeven <= 60%)
- Take-Profit: Venda antecipada em 86¢
- Integração: Jev / TypeSafe AI para avaliação probabilística institucional
=============================================================================
"""

import os
import sys
import time
import json
import ssl
import urllib.request
from datetime import datetime

# Garante UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "btc_5m_9y_cache.json")
RESULTS_FILE = os.path.join(BASE_DIR, "backtest_kalshi_15m_9y_results.json")

INITIAL_CAPITAL = 35.00       # $10 depósito + $25 bônus Kalshi
BASE_STAKE = 1.00            # $1.00 por aposta
DEADBAND_BPS = 0.00035       # 3.5 bps (0.035%)
DEADBAND_MIN_FLOOR = 25.0    # Piso de $25
PRIMARY_MAX_PRICE = 0.60     # Teto de 60¢
PRIMARY_MIN_PRICE = 0.35     # Piso de 35¢
TP_PRICE = 0.86              # Take profit em 86¢

print("\n" + "=" * 95)
print("  🚀 BACKTEST 9 ANOS (2017-2026): KALSHI BTC 15-MINUTE (KXBTC15M)")
print("  Banca Inicial: $35.00 USD ($10 depósito + $25 bônus Kalshi)")
print("  Estratégia: Drift aos 450s (3.5 bps) + Teto 60¢ + Take-Profit 86¢")
print("=" * 95)

# ===================== DOWNLOAD / CARREGAMENTO DE VELAS 5M =====================
def get_9y_5m_klines():
    if os.path.exists(CACHE_FILE):
        fsize_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
        print(f"\n[*] Carregando cache local: {CACHE_FILE} ({fsize_mb:.1f} MB)...")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[OK] {len(data):,} velas de 5m carregadas do cache.")
        return data

    print("\n[*] Cache não encontrado. Iniciando download de 9 anos de dados 5m da Binance...")
    print("    Início: 17 de Agosto de 2017 | Fim: Setembro de 2026 (~957k velas)")
    
    start_ts = 1502942400000 # 17/08/2017 04:00 UTC
    end_ts = int(time.time() * 1000)
    current_ts = start_ts
    all_klines = []
    req_count = 0
    t0 = time.time()

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    while current_ts < end_ts:
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={current_ts}&limit=1000"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                batch = json.loads(r.read().decode())
                if not batch:
                    break
                
                # Guarda apenas [ts_sec, open, high, low, close] para economizar RAM
                for k in batch:
                    all_klines.append([
                        int(k[0]) // 1000,
                        float(k[1]),
                        float(k[2]),
                        float(k[3]),
                        float(k[4])
                    ])
                
                req_count += 1
                last_candle_ms = int(batch[-1][0])
                current_ts = last_candle_ms + (5 * 60 * 1000)

                if req_count % 50 == 0:
                    dt_str = datetime.utcfromtimestamp(int(batch[-1][0]) // 1000).strftime("%Y-%m-%d")
                    elapsed = time.time() - t0
                    print(f"    [{req_count} reqs] {len(all_klines):,} velas | Data: {dt_str} | Tempo: {elapsed:.1f}s")
                
                time.sleep(0.04) # Evita rate limit
        except Exception as e:
            time.sleep(1.0)

    print(f"\n[OK] Download concluído! {len(all_klines):,} velas de 5m baixadas em {time.time()-t0:.1f}s.")
    print(f"[*] Salvando cache compacto em {CACHE_FILE}...")
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_klines, f)
    print(f"[OK] Cache salvo com sucesso ({os.path.getsize(CACHE_FILE)/(1024*1024):.1f} MB).\n")
    return all_klines


# ===================== SIMULADOR DE PREÇO CLOB KALSHI =====================
def get_kalshi_cota_price(delta_usd: float, strike: float, elapsed_sec: int = 450) -> float:
    """Modela o preço em centavos (0.01 a 0.99) na CLOB com base no drift relativo"""
    time_factor = 1.0 + (elapsed_sec / 900.0) * 1.5
    vol_scale = strike * 0.0020 / time_factor # ~20 bps de desvio padrão em 15m
    prob = 0.50 + (delta_usd / (vol_scale * 3.5))
    return round(max(0.05, min(0.95, prob)), 2)


# ===================== ENGINE DE BACKTEST 15M (9 ANOS) =====================
def run_15m_simulation(klines_5m):
    print("[*] Indexando velas de 5 minutos e construindo janelas de 15m...")
    candles_by_ts = {k[0]: {"open": k[1], "high": k[2], "low": k[3], "close": k[4]} for k in klines_5m}
    all_5m_ts = sorted(candles_by_ts.keys())

    # Agrupa em janelas de 15 minutos (00, 15, 30, 45) -> 900 segundos
    windows_15m = [ts for ts in all_5m_ts if ts % 900 == 0]
    print(f"[OK] {len(windows_15m):,} janelas de 15 minutos disponíveis nos 9 anos.\n")

    total_windows = len(windows_15m)
    participated = 0
    skipped = 0
    wins = 0
    losses = 0
    tp_wins = 0

    total_stake = 0.0
    total_payout = 0.0
    total_pnl = 0.0

    current_balance = INITIAL_CAPITAL
    peak_balance = INITIAL_CAPITAL
    max_drawdown = 0.0
    min_balance = INITIAL_CAPITAL

    yearly_pnl = {}
    daily_pnl = {}
    monthly_pnl = {}

    t0 = time.time()
    report_step = total_windows // 10

    for idx, w_ts in enumerate(windows_15m):
        if idx % report_step == 0 and idx > 0:
            dt_s = datetime.utcfromtimestamp(w_ts).strftime("%Y-%m-%d")
            print(f"    [{(idx/total_windows*100):5.1f}%] {dt_s} | Saldo: ${current_balance:,.2f} | Trades: {participated:,} | P&L: {total_pnl:+,.2f} USD")

        c0 = candles_by_ts.get(w_ts)         # Vela 1: 0m-5m (0s a 300s)
        c1 = candles_by_ts.get(w_ts + 300)   # Vela 2: 5m-10m (300s a 600s) -> avalia no meio (450s)
        c2 = candles_by_ts.get(w_ts + 600)   # Vela 3: 10m-15m (600s a 900s) -> fechamento

        if not (c0 and c1 and c2):
            skipped += 1
            continue

        day_str = datetime.utcfromtimestamp(w_ts).strftime("%Y-%m-%d")
        month_str = datetime.utcfromtimestamp(w_ts).strftime("%Y-%m")
        year_str = datetime.utcfromtimestamp(w_ts).strftime("%Y")

        if day_str not in daily_pnl: daily_pnl[day_str] = 0.0
        if month_str not in monthly_pnl: monthly_pnl[month_str] = 0.0
        if year_str not in yearly_pnl: yearly_pnl[year_str] = 0.0

        strike = c0["open"]
        spot_450s = (c1["open"] + c1["close"]) / 2.0
        final_spot = c2["close"]
        winner = "UP" if final_spot >= strike else "DOWN"

        delta = spot_450s - strike
        dynamic_deadband = max(DEADBAND_MIN_FLOOR, round(strike * DEADBAND_BPS, 2))

        should_enter = False
        target_side = None

        if delta >= dynamic_deadband:
            target_side = "UP"
            should_enter = True
        elif delta <= -dynamic_deadband:
            target_side = "DOWN"
            should_enter = True
        else:
            skipped += 1
            continue

        # Preço da cota na Kalshi aos 450s
        p_up = get_kalshi_cota_price(delta, strike, 450)
        cota_price = p_up if target_side == "UP" else (1.0 - p_up)

        # Filtro estrito de teto de preço
        if cota_price < PRIMARY_MIN_PRICE or cota_price > PRIMARY_MAX_PRICE:
            skipped += 1
            continue

        # Stake fixo de $1.00 ou proporcional
        stake_size = BASE_STAKE
        shares = stake_size / cota_price
        cycle_payout = 0.0
        sold_tp = False

        participated += 1

        # Simulação de Take-Profit aos ~650s-750s (se vela 2 ou 3 esticou a favor)
        favored_high = c1["high"] if target_side == "UP" else (2 * strike - c1["low"])
        max_delta_seen = favored_high - strike
        if max_delta_seen >= (dynamic_deadband * 1.8):
            sold_tp = True
            tp_wins += 1
            cycle_payout = round(shares * TP_PRICE, 2)
        else:
            # Liquidação normal no fechamento aos 900s
            if target_side == winner:
                cycle_payout = round(shares * 1.00, 2)
                wins += 1
            else:
                losses += 1

        cycle_pnl = round(cycle_payout - stake_size, 2)
        total_stake += stake_size
        total_payout += cycle_payout
        total_pnl += cycle_pnl
        current_balance += cycle_pnl

        daily_pnl[day_str] += cycle_pnl
        monthly_pnl[month_str] += cycle_pnl
        yearly_pnl[year_str] += cycle_pnl

        if current_balance > peak_balance: peak_balance = current_balance
        dd = peak_balance - current_balance
        if dd > max_drawdown: max_drawdown = dd
        if current_balance < min_balance: min_balance = current_balance

    sim_time = time.time() - t0
    total_victories = wins + tp_wins
    wr = (total_victories / participated * 100) if participated > 0 else 0
    roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0

    # Sharpe Diário
    d_returns = [v for v in daily_pnl.values() if v != 0]
    avg_d = sum(d_returns) / len(d_returns) if d_returns else 0
    std_d = (sum((x - avg_d)**2 for x in d_returns) / len(d_returns))**0.5 if d_returns else 1
    sharpe = (avg_d / std_d) if std_d > 0 else 0

    results = {
        "period": "Agosto 2017 a Setembro 2026 (9 Anos)",
        "total_15m_windows": total_windows,
        "participated": participated,
        "skipped": skipped,
        "participation_rate": round(participated / total_windows * 100, 2),
        "wins_held": wins,
        "wins_tp": tp_wins,
        "total_wins": total_victories,
        "losses": losses,
        "win_rate": round(wr, 2),
        "initial_capital": INITIAL_CAPITAL,
        "final_balance": round(current_balance, 2),
        "total_pnl": round(total_pnl, 2),
        "total_stake": round(total_stake, 2),
        "total_payout": round(total_payout, 2),
        "roi_on_volume": round(roi, 2),
        "max_drawdown": round(max_drawdown, 2),
        "peak_balance": round(peak_balance, 2),
        "min_balance": round(min_balance, 2),
        "sharpe_daily": round(sharpe, 4),
        "yearly_pnl": {k: round(v, 2) for k, v in sorted(yearly_pnl.items())},
        "profitable_days": sum(1 for v in daily_pnl.values() if v > 0),
        "loss_days": sum(1 for v in daily_pnl.values() if v < 0),
        "simulation_time_sec": round(sim_time, 2)
    }

    return results


# ===================== INTEGRAÇÃO JEV / TYPESAFE AI =====================
def run_jev_kalshi_analysis(r: dict):
    print("\n" + "=" * 95)
    print("  [JEV/TYPESAFE AI] ENVIANDO RESULTADOS DOS 9 ANOS PARA ANÁLISE INSTITUCIONAL")
    print("=" * 95)

    try:
        from typesafe_sdk import TypeSafeClient, Choice, Score, Noul
        from dotenv import load_dotenv; load_dotenv()
os.environ["TYPESAFE_API_KEY"] = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
        client = TypeSafeClient()

        state = f"""
KALSHI BTC 15-MINUTE BINARY OPTIONS ENGINE (KXBTC15M) - 9-YEAR AUDIT
Period: August 2017 to September 2026 (9 full years)
Initial Deposit: $10.00 + $25.00 Bonus = $35.00 USD
Final Capital: ${r['final_balance']:,.2f} USD
Net P&L: {r['total_pnl']:+,.2f} USD
Win Rate: {r['win_rate']:.1f}% ({r['total_wins']:,} wins / {r['losses']:,} losses)
Total Trades: {r['participated']:,} across {r['total_15m_windows']:,} 15-minute cycles
Take-Profit (86c) Wins: {r['wins_tp']:,} ({r['wins_tp']/max(r['total_wins'],1)*100:.1f}% of wins)
Max Drawdown: ${r['max_drawdown']:.2f} USD
Sharpe Ratio (Daily): {r['sharpe_daily']:.4f}
Yearly Breakdown: {json.dumps(r['yearly_pnl'])}
Strategy: 15-Minute Drift @ 450s with Dynamic Deadband (3.5 bps), Max Ticket 60c, TP 86c
"""
        print("[*] Conectando com a API Jev (SystemOne)...")
        response = client.system_one(
            state=state,
            questions={
                "kalshi_viability": Choice(
                    instructions="Evaluate the overall viability of deploying this 15-minute BTC strategy on Kalshi with a $35 starting capital.",
                    criteria={
                        "highly_viable": "Highly viable - exceptional consistency and statistical edge across 9 full years",
                        "viable_moderate": "Viable with moderate expectations - strong long-term return",
                        "marginal": "Marginal - return is modest for the time invested",
                        "not_viable": "Not viable - avoid deploying real capital"
                    }
                ),
                "risk_rating": Score(
                    instructions="Rate the risk level from 1 (very safe) to 5 (very risky) considering the $35 starting bankroll, drawdown, and win rate.",
                    criteria=["Very Low Risk", "Low Risk", "Moderate Risk", "High Risk", "Very High Risk"]
                ),
                "kalshi_vs_polymarket": Choice(
                    instructions="Compare the 15-minute Kalshi format to the 5-minute Polymarket format based on noise reduction and edge stability.",
                    criteria={
                        "kalshi_superior": "Kalshi 15m is superior due to lower microstructure noise and cleaner momentum trends",
                        "both_viable": "Both 5m and 15m are equally viable complementary strategies",
                        "polymarket_superior": "Polymarket 5m is superior due to higher trade frequency"
                    }
                ),
                "recommendation": Choice(
                    instructions="What is the final recommendation for the trader regarding depositing $10 to get the $25 bonus on Kalshi?",
                    criteria={
                        "deposit_and_run": "Deposit $10, claim $25 bonus ($35 total), and run the 15m bot",
                        "paper_trade_first": "Paper trade for 1-2 weeks on Kalshi demo before depositing",
                        "do_not_deposit": "Do not deposit - stick exclusively to Polymarket"
                    }
                )
            }
        )
        print("[OK] Resposta Jev recebida com sucesso!")
        return response
    except Exception as e:
        print(f"[!] Erro ao chamar Jev: {e}")
        return None


# ===================== MAIN =====================
if __name__ == "__main__":
    klines_5m = get_9y_5m_klines()
    results = run_15m_simulation(klines_5m)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Resultados salvos em '{RESULTS_FILE}'.")

    # Imprime Relatório
    print("\n" + "=" * 95)
    print("  📊 RESULTADO DO BACKTEST DE 9 ANOS: KALSHI BTC 15M")
    print("=" * 95)
    print(f"  Janelas de 15m Analisadas:  {results['total_15m_windows']:,}")
    print(f"  Trades Executados:          {results['participated']:,} ({results['participation_rate']}%)")
    print(f"  Vitórias:                   {results['total_wins']:,} (Hold: {results['wins_held']:,} | TP: {results['wins_tp']:,})")
    print(f"  Derrotas:                   {results['losses']:,}")
    print(f"  TAXA DE ACERTO (WIN RATE):  {results['win_rate']:.1f}%")
    print("-" * 95)
    print(f"  Banca Inicial (com Bônus):  ${results['initial_capital']:.2f} USD")
    print(f"  SALDO FINAL (9 ANOS):       ${results['final_balance']:,.2f} USD")
    print(f"  LUCRO LÍQUIDO TOTAL (P&L):  {results['total_pnl']:+,.2f} USD")
    print(f"  Retorno sobre Volume (ROI): {results['roi_on_volume']:+.2f}%")
    print(f"  Drawdown Máximo:            ${results['max_drawdown']:.2f} USD")
    print(f"  Pico de Saldo:              ${results['peak_balance']:,.2f} USD")
    print(f"  Sharpe Diário:              {results['sharpe_daily']:.4f}")
    print("-" * 95)
    print("  P&L ANUAL DETALHADO (2017 a 2026):")
    for yr, val in results["yearly_pnl"].items():
        icon = "[+]" if val > 0 else "[-]"
        print(f"    {icon} {yr}: {val:+10,.2f} USD")
    print("=" * 95)

    # Executa Jev
    jev_resp = run_jev_kalshi_analysis(results)
    if jev_resp:
        print("\n" + "=" * 95)
        print("  🤖 VEREDITO PROBABILÍSTICO DA IA JEV (TYPESAFE INSTITUCIONAL)")
        print("=" * 95)
        v = jev_resp.answers["kalshi_viability"]
        print(f"  1. Viabilidade Geral:       {v.choice.upper()} (Confiança: {v.confidence:.1%})")
        r = jev_resp.answers["risk_rating"]
        print(f"  2. Nível de Risco:          Score {r.score:.2f}/5 (Confiança: {r.confidence:.1%})")
        c = jev_resp.answers["kalshi_vs_polymarket"]
        print(f"  3. Kalshi 15m vs Poly 5m:   {c.choice.upper()}")
        rec = jev_resp.answers["recommendation"]
        print(f"  4. Recomendação Direta:     {rec.choice.upper()} (Confiança: {rec.confidence:.1%})")
        print("=" * 95 + "\n")
