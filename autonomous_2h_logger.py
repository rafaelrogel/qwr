"""
Experimento Autônomo de 2 Horas - Polymarket BTC 5m Trading Simulado
- Duração: 2 horas (24 ciclos consecutivos de 5 minutos)
- Aposta fixa: 1.00 USDC por ciclo
- Registra: Entrada, Preço da cota, Strike, Spot, Sinal, Vencedor, Payout e P&L
- Salva tudo em tempo real em:
  - autonomous_2h_results.json
  - autonomous_2h_results.csv
"""
import os
import sys
import time
import json
import csv
import urllib.request
from datetime import datetime

TOTAL_HOURS = 2
TOTAL_SECONDS = TOTAL_HOURS * 3600
BET_AMOUNT = 1.00  # 1 USDC fixo por rodada

base_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
json_output = os.path.join(base_dir, "autonomous_2h_results.json")
csv_output = os.path.join(base_dir, "autonomous_2h_results.csv")

def get_binance_spot():
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return float(json.loads(r.read().decode())["price"])
        except Exception:
            pass
    return None

def get_candle_open(window_ts):
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=3"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            for k in data:
                if int(k[0]) // 1000 == window_ts:
                    return float(k[1])
            if data:
                return float(data[-1][1])
    except Exception:
        pass
    return None

def get_polymarket_prices(window_ts):
    slug = f"btc-updown-5m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode())
            if data:
                prices = json.loads(data[0].get("outcomePrices", "[]"))
                if len(prices) >= 2:
                    return float(prices[0]), float(prices[1])
    except Exception:
        pass
    return 0.50, 0.50

def run_experiment():
    start_time = time.time()
    end_time = start_time + TOTAL_SECONDS
    
    print("=" * 70)
    print(f"INICIANDO EXPERIMENTO DE 2 HORAS (1 USDC POR APOSTA)")
    print(f"Início: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Término Previsto: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Aposta Fixa: ${BET_AMOUNT:.2f} USDC em todas as rodadas de 5 minutos")
    print("=" * 70)

    # Inicializa CSV se não existir
    if not os.path.exists(csv_output):
        with open(csv_output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "cycle_num", "time_start", "window_ts", "strike_K", "entry_time", 
                "chosen_side", "entry_price", "shares_bought", "signal_rationale",
                "final_spot", "delta_p", "winner", "result", "payout_gross", "pnl_net", 
                "cumulative_spent", "cumulative_pnl", "win_rate"
            ])

    cycles_completed = 0
    total_spent = 0.0
    total_pnl = 0.0
    total_wins = 0
    recent_results = [] # Para contagem de sequências (Markov DDD/UUU)

    # Carrega dados prévios se houver
    if os.path.exists(json_output):
        try:
            with open(json_output, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cycles_completed = saved.get("total_cycles", 0)
                total_spent = saved.get("total_spent", 0.0)
                total_pnl = saved.get("total_pnl", 0.0)
                total_wins = saved.get("total_wins", 0)
                recent_results = [h["winner"] for h in saved.get("rounds", [])[-5:]]
        except Exception:
            pass

    while time.time() < end_time:
        now = int(time.time())
        window_ts = now - (now % 300)
        seconds_elapsed = now - window_ts
        seconds_left = 300 - seconds_elapsed

        cycle_num = cycles_completed + 1
        time_str = datetime.fromtimestamp(window_ts).strftime("%H:%M:%S")

        print(f"\n>>> [Ciclo #{cycle_num}] Janela {time_str} (Restam {seconds_left}s)")

        # 1. Pega o Strike Price
        strike = get_candle_open(window_ts)
        if not strike:
            strike = get_binance_spot() or 82000.0
        print(f"    Strike Price (Price to Beat): ${strike:,.2f}")

        # 2. Aguarda até o segundo 120-150 da vela para coletar dados intra-candle e Polymarket
        target_eval_sec = 135
        if seconds_elapsed < target_eval_sec:
            sleep_needed = target_eval_sec - seconds_elapsed
            print(f"    Coletando dados intra-candle... aguardando {sleep_needed}s para tomada de decisão")
            time.sleep(sleep_needed)

        # 3. Decisão de Aposta (Segundo 135)
        spot_at_eval = get_binance_spot() or strike
        delta = spot_at_eval - strike
        poly_up, poly_down = get_polymarket_prices(window_ts)
        
        # Lógica Quantitativa:
        # Se houve sequência de 3 quedas anteriores [D, D, D] -> Viés forte de reversão para UP (55.4% Markov)
        is_ddd = len(recent_results) >= 3 and recent_results[-3:] == ["DOWN", "DOWN", "DOWN"]
        
        chosen_side = "UP"
        entry_price = poly_up
        rationale = ""

        if is_ddd and delta > -10.0:
            chosen_side = "UP"
            entry_price = poly_up
            rationale = "Gatilho de Reversão Markov (3 vermelhas anteriores DDD) + Spot defendendo strike"
        elif delta >= 15.0:
            chosen_side = "UP"
            entry_price = poly_up
            rationale = f"Drift Intra-Vela Positivo (+$ {delta:.1f} acima do strike no 2º minuto)"
        elif delta <= -15.0:
            chosen_side = "DOWN"
            entry_price = poly_down
            rationale = f"Drift Intra-Vela Negativo (-$ {abs(delta):.1f} abaixo do strike no 2º minuto)"
        else:
            # Perto do strike: aposta no lado com melhor EV no Polymarket
            if poly_up < 0.48:
                chosen_side = "UP"
                entry_price = poly_up
                rationale = f"Assimetria de Preço Polymarket (UP barato a ${poly_up:.2f})"
            elif poly_down < 0.48:
                chosen_side = "DOWN"
                entry_price = poly_down
                rationale = f"Assimetria de Preço Polymarket (DOWN barato a ${poly_down:.2f})"
            else:
                chosen_side = "UP" if delta >= 0 else "DOWN"
                entry_price = poly_up if chosen_side == "UP" else poly_down
                rationale = f"Seguindo micro-tendência spot (Delta: {delta:+.1f})"

        # Limites de segurança para preço da cota
        entry_price = max(0.05, min(0.95, entry_price))
        shares_bought = round(BET_AMOUNT / entry_price, 4)
        entry_time_str = datetime.now().strftime("%H:%M:%S")

        print(f"    -> DECISÃO REGISTRADA: 1 USDC em {chosen_side} @ ${entry_price:.2f} ({shares_bought} cotas)")
        print(f"       Justificativa: {rationale}")

        # 4. Aguarda o fechamento da vela de 5m (segundo 300)
        curr_elapsed = int(time.time()) - window_ts
        remaining_to_close = max(1, 300 - curr_elapsed + 2) # +2s para garantir fechamento
        print(f"    Aguardando encerramento da rodada em {remaining_to_close}s...")
        time.sleep(remaining_to_close)

        # 5. Apuração do Resultado Oficial
        final_spot = get_binance_spot() or spot_at_eval
        final_delta = final_spot - strike
        winner = "UP" if final_spot >= strike else "DOWN"

        is_win = (chosen_side == winner)
        total_spent += BET_AMOUNT
        cycles_completed += 1

        if is_win:
            total_wins += 1
            payout_gross = round(shares_bought * 1.00, 2)
            pnl_net = round(payout_gross - BET_AMOUNT, 2)
            result_str = "VITÓRIA"
        else:
            payout_gross = 0.00
            pnl_net = -round(BET_AMOUNT, 2)
            result_str = "DERROTA"

        total_pnl = round(total_pnl + pnl_net, 2)
        win_rate = round(total_wins / cycles_completed * 100, 1)
        recent_results.append(winner)
        if len(recent_results) > 10:
            recent_results.pop(0)

        print(f"    ================ RESULTADO CICLO #{cycle_num} ================")
        print(f"    Strike: ${strike:,.2f} | Final: ${final_spot:,.2f} (Delta: {final_delta:+.2f})")
        print(f"    Vencedor Oficial: {winner} | Nossa Aposta: {chosen_side}")
        print(f"    Resultado: {result_str} | P&L Rodada: {pnl_net:+.2f} USDC")
        print(f"    ACUMULADO: Gasto: ${total_spent:.2f} | P&L: {total_pnl:+.2f} USDC | Win Rate: {win_rate}% ({total_wins}/{cycles_completed})")
        print("    ============================================================")

        # 6. Salva no CSV
        with open(csv_output, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                cycle_num, time_str, window_ts, round(strike, 2), entry_time_str,
                chosen_side, round(entry_price, 3), shares_bought, rationale,
                round(final_spot, 2), round(final_delta, 2), winner, result_str,
                payout_gross, pnl_net, round(total_spent, 2), round(total_pnl, 2), win_rate
            ])

        # 7. Salva no JSON consolidado para consulta da API e Dashboard
        round_data = {
            "cycle_num": cycle_num,
            "time_start": time_str,
            "strike": round(strike, 2),
            "chosen_side": chosen_side,
            "entry_price": round(entry_price, 3),
            "final_spot": round(final_spot, 2),
            "delta": round(final_delta, 2),
            "winner": winner,
            "result": result_str,
            "pnl": pnl_net,
            "rationale": rationale
        }

        # Lê histórico existente
        history = []
        if os.path.exists(json_output):
            try:
                with open(json_output, "r", encoding="utf-8") as f:
                    history = json.load(f).get("rounds", [])
            except Exception:
                pass
        history.append(round_data)

        state = {
            "status": "RUNNING",
            "start_time": datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time_target": datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S"),
            "total_cycles": cycles_completed,
            "total_spent": round(total_spent, 2),
            "total_pnl": round(total_pnl, 2),
            "total_wins": total_wins,
            "total_losses": cycles_completed - total_wins,
            "win_rate": win_rate,
            "roi_pct": round((total_pnl / total_spent * 100) if total_spent > 0 else 0, 2),
            "rounds": history
        }

        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        # Pequena pausa para sincronizar com o próximo ciclo
        time.sleep(2)

    # Conclusão do Experimento de 2 Horas
    print("\n" + "#" * 70)
    print("EXPERIMENTO DE 2 HORAS CONCLUÍDO COM SUCESSO!")
    print(f"Total de Ciclos Operados: {cycles_completed}")
    print(f"Total Gasto: ${total_spent:.2f} USDC")
    print(f"P&L Líquido Final: {total_pnl:+.2f} USDC")
    print(f"Taxa de Vitória: {win_rate}% ({total_wins} vitórias / {cycles_completed - total_wins} derrotas)")
    print("#" * 70)

if __name__ == "__main__":
    run_experiment()
