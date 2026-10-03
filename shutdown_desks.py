# -*- coding: utf-8 -*-
"""
Script utilitário para desligar todos os robôs de trading e o dashboard server com segurança.
Pode ser chamado via terminal ou pelo batch PARAR_TODOS_OS_DESKS.bat.
"""
import os
import sys
import time

try:
    import psutil
except ImportError:
    print("[ERRO] Biblioteca 'psutil' nao encontrada. Instalando...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

TARGET_SCRIPTS = [
    "dashboard_server.py",
    "live_trader_5m.py",
    "sol_trader_5m.py",
    "kalshi_trader_15m.py",
    "kalshi_natgas_daemon.py",
    "kalshi_natgas_trader_15m.py",
    "desk6_yield_harvester.py",
    "desk7_cross_arb.py",
    "eth_trader_5m.py",
    "kalshi_gold_trader_15m.py",
    "desk10_microstructure_harvester.py",
    "kalshi_spx_trader_15m.py",
    "desk12_weather_metar.py",
    "whale_flow_monitor.py",
    "btc_15m_paper_trader.py",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def stop_all_desks():
    print("=" * 65)
    print(" [AGY DESKS] ENCERRANDO ROBÔS DE TRADING E DASHBOARD SERVER")
    print("=" * 65)
    
    my_pid = os.getpid()
    killed = 0
    to_kill = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == my_pid:
                continue
            
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline)
            
            if "shutdown_desks.py" in cmd_str:
                continue

            for target in TARGET_SCRIPTS:
                if target in cmd_str:
                    to_kill.append((proc, target))
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not to_kill:
        print("[INFO] Nenhum robô ou dashboard em execução no momento.")
    else:
        for proc, target in to_kill:
            try:
                print(f"[PARANDO] PID {proc.pid}: {target}...")
                proc.terminate()
                killed += 1
            except Exception as e:
                try:
                    proc.kill()
                    killed += 1
                except Exception:
                    pass

        # Aguardar 2 segundos para encerramento gracioso
        time.sleep(2)

        # Forçar kill se algum ainda estiver vivo
        for proc, target in to_kill:
            try:
                if proc.is_running():
                    print(f"[FORÇANDO ENCERRAMENTO] PID {proc.pid}: {target}")
                    proc.kill()
            except Exception:
                pass

        print(f"\n[SUCESSO] Total de {killed} processo(s) encerrado(s).")

    # Limpeza de lock file
    lock_file = os.path.join(BASE_DIR, "live_trader.lock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
            print("[LOCK] live_trader.lock removido com sucesso.")
        except Exception as e:
            print(f"[LOCK] Nota: live_trader.lock não pôde ser removido: {e}")

    print("=" * 65)
    print(" Todos os serviços foram desligados com segurança.")
    print("=" * 65)


if __name__ == "__main__":
    stop_all_desks()
