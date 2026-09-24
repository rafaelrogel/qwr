import urllib.request
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("=" * 80)
print("1. CONSULTA AO DASHBOARD HTTP (127.0.0.1:8080)")
print("=" * 80)

try:
    req = urllib.request.Request("http://127.0.0.1:8080/api/dashboard_state")
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode())

    cycle = data.get("current_cycle", {})
    acc = data.get("account", {})
    pnl = data.get("pnl_summary", {})
    sol = data.get("sol_radar", {})
    kalshi = data.get("kalshi_radar", {})
    natgas = data.get("natgas_radar", {})
    ks = data.get("kill_switch_active", False)

    print(f"Status do Kill-Switch: {'🚨 ATIVADO (SISTEMA PAUSADO)' if ks else '🛡️ NORMAL (BOTS ATIVOS)'}")
    print(f"Saldo Carteira Polygon Safe: ${float(acc.get('current_balance_live', 21.81)):.2f} USDC (Depósito inicial: ${float(acc.get('initial_deposit', 21.00)):.2f})")
    print(f"P&L Líquido da Sessão: ${float(pnl.get('net_real_pnl', 0.0)):+.2f} USDC (Win Rate: {float(pnl.get('win_rate', 0.0)):.1f}% em {pnl.get('total_participated_bets', 0)} ciclos)")

    print("\n--- DESK 1: POLYMARKET BTC 5M [LIVE] ---")
    print(f"Mercado: {cycle.get('title')}")
    print(f"Tempo: Restam {cycle.get('seconds_left')}s (Decorrido: {cycle.get('seconds_elapsed')}s | {float(cycle.get('progress_pct', 0)):.1f}%)")
    print(f"Strike (K): ${float(cycle.get('strike', 0)):,.2f} | Spot Chainlink: ${float(cycle.get('oracle_spot', 0)):,.2f} | Binance: ${float(cycle.get('binance_spot', 0)):,.2f}")
    delta = float(cycle.get('delta', 0))
    print(f"Delta Atual: {delta:+.2f} USD ({cycle.get('status')}) | Spread Feeds: ${float(cycle.get('feed_spread', 0)):.2f}")
    print(f"Preços CLOB: UP ${float(cycle.get('poly_price_up', 0.5)):.2f} | DOWN ${float(cycle.get('poly_price_down', 0.5)):.2f}")
    sig = cycle.get('signal', {})
    print(f"Sinal do Sniper (135s): {sig.get('action', 'NENHUM')} | Racional: {sig.get('rationale', 'Aguardando')}")

    print("\n--- DESK 2: POLYMARKET SOL 5M [PAPER] ---")
    print(f"Mercado: {sol.get('market_title', 'sol-updown-5m')} | Restam: {sol.get('seconds_left')}s")
    print(f"Spot SOL: ${float(sol.get('spot', 0)):.2f} | Delta: {float(sol.get('delta', 0)):+.3f} USD (Deadband: {sol.get('deadband')} USD)")
    print(f"CLOB L2: Bid ${float(sol.get('clob_bid', 0)):.2f} | Ask ${float(sol.get('clob_ask', 0)):.2f} | Spread: ${float(sol.get('clob_spread', 0)):.3f}")
    print(f"Status SOL: {sol.get('status_signal')}")

    print("\n--- DESK 3: KALSHI BTC 15M [PAPER / CONEXÃO CFTC] ---")
    print(f"Ticker: {kalshi.get('ticker', 'KXBTC15M')} | Restam: {kalshi.get('seconds_left')}s")
    print(f"Strike: ${float(kalshi.get('strike', 0)):,.2f} | Spot: ${float(kalshi.get('spot', 0)):,.2f} | Delta: {float(kalshi.get('delta', 0)):+.2f} USD")
    print(f"Status Kalshi: {kalshi.get('status_signal')}")

except Exception as e:
    print("Erro consultando dashboard:", e)

print("\n" + "=" * 80)
print("2. STATUS DAS TAREFAS DOS ROBÔS E ÚLTIMOS LOGS")
print("=" * 80)

log_dir = r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks"
task_map = {
    "task-10139": "Desk 1 (live_trader_5m - BTC LIVE)",
    "task-10141": "Desk 2 (sol_trader_5m - SOL)",
    "task-10143": "Desk 3 (kalshi_trader_15m - Kalshi)",
    "task-10286": "Dashboard Server (localhost:8080)"
}

for task_id, desc in task_map.items():
    log_file = os.path.join(log_dir, f"{task_id}.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            last_lines = lines[-4:] if lines else ["(sem logs recentes)"]
            print(f"\n[OK] {desc} ({task_id}):")
            for ll in last_lines:
                print(f"    > {ll[:120]}")
        except Exception as e:
            print(f"Erro lendo log de {task_id}: {e}")
    else:
        print(f"[!] Log para {task_id} não encontrado em {log_file}")
