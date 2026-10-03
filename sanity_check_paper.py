import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import psutil
from datetime import datetime, timezone

BASE_DIR = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"

paper_desks = [
    {
        "desk": "Desk 4",
        "name": "Kalshi NatGas EIA Semanal",
        "script": "kalshi_natgas_daemon.py",
        "state_file": "kalshi_live_weather_signal.json",
        "journal_file": "kalshi_natgas_journal.json"
    },
    {
        "desk": "Desk 6",
        "name": "Yield Harvester & Theta",
        "script": "desk6_yield_harvester.py",
        "state_file": "desk6_state.json",
        "journal_file": "desk6_yield_journal.json"
    },
    {
        "desk": "Desk 7",
        "name": "Cross-Market Macro Arbitrage",
        "script": "desk7_cross_arb.py",
        "state_file": "desk7_cross_arb_state.json",
        "journal_file": None
    },
    {
        "desk": "Desk 8",
        "name": "Polymarket ETH 5m",
        "script": "eth_trader_5m.py",
        "state_file": "eth_live_market_state.json",
        "journal_file": "eth_trading_journal.json"
    },
    {
        "desk": "Desk 9",
        "name": "Kalshi Gold 15m",
        "script": "kalshi_gold_trader_15m.py",
        "state_file": "kalshi_gold_15m_live_state.json",
        "journal_file": "kalshi_gold_15m_journal.json"
    },
    {
        "desk": "Desk 11",
        "name": "Kalshi S&P 500 15m Momentum",
        "script": "kalshi_spx_trader_15m.py",
        "state_file": "kalshi_spx_15m_live_state.json",
        "journal_file": "kalshi_spx_15m_journal.json"
    }
]

print("=" * 85)
print(" SANITY CHECK: AUDITORIA EM TEMPO REAL DOS 7 DESKS EM MODO PAPER / SCANNER")
print(" Data/Hora:", datetime.now(timezone.utc).isoformat())
print("=" * 85)

running_scripts = {}
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cmd = " ".join(p.info.get("cmdline") or [])
        for d in paper_desks:
            if d["script"] in cmd:
                running_scripts[d["script"]] = p.info["pid"]
    except Exception:
        pass

for d in paper_desks:
    print(f"\n--- [{d['desk']}] {d['name']} ({d['script']}) ---")
    pid = running_scripts.get(d["script"])
    if pid:
        print(f"  [✓] PROCESSO: Ativo e Executando (PID {pid})")
    else:
        print(f"  [✗] PROCESSO: NÃO ENCONTRADO!")

    st_path = os.path.join(BASE_DIR, d["state_file"])
    if os.path.exists(st_path):
        mtime = os.path.getmtime(st_path)
        age = time.time() - mtime
        try:
            with open(st_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            fresh = "FRESH" if age < 60 else f"STALE ({age:.0f}s)"
            print(f"  [✓] ESTADO JSON: Presente ({fresh}) | Gravado há {age:.1f}s")
            keys = [
                "status_signal", "spot", "strike", "delta", "deadband", "balance", 
                "paper_balance", "stream_type", "bookticker_obi", "squeeze_opportunity", 
                "squeeze_direction", "squeeze_confidence", "polymarket_markets_scanned", 
                "kalshi_markets_scanned", "active_positions_count", "current_exposure_usd",
                "seconds_elapsed", "seconds_left"
            ]
            sample = {k: st[k] for k in keys if k in st}
            print(f"      Métricas: {sample}")
        except Exception as e:
            print(f"  [!] Erro ao ler estado: {e}")
    else:
        print(f"  [!] Estado JSON não encontrado: {d['state_file']}")

    if d["journal_file"]:
        j_path = os.path.join(BASE_DIR, d["journal_file"])
        if os.path.exists(j_path):
            try:
                with open(j_path, "r", encoding="utf-8") as f:
                    j = json.load(f)
                trades = j.get("trades", [])
                wins = j.get("wins", 0)
                losses = j.get("losses", 0)
                wr = j.get("win_rate", j.get("win_rate_pct", 0.0))
                print(f"  [✓] JOURNAL: Presente ({len(trades)} trades | {wins}V / {losses}D | WR: {wr}%)")
            except Exception as e:
                print(f"  [!] Erro journal: {e}")
        else:
            print(f"  [i] JOURNAL: Ainda não gerado (Aguardando 1º trade resolvido)")

print("\n" + "=" * 85)
print(f" RESUMO DA AUDITORIA DOS {len(paper_desks)} DESKS PAPER / SCANNER")
total_running = len(running_scripts)
print(f" Total de Processos Monitorados: {total_running} de {len(paper_desks)} ativos")
if total_running == len(paper_desks):
    print(" Veredito Sanity Check: 100% OPERACIONAL, NENHUM BOT TRAVADO OU MORTO!")
else:
    print(" Veredito Sanity Check: ATENÇÃO! Verifique os robôs ausentes acima.")
print("=" * 85)
