import psutil

target_scripts = [
    'dashboard_server.py',
    'live_trader_5m.py',
    'sol_trader_5m.py',
    'kalshi_trader_15m.py',
    'kalshi_natgas_daemon.py',
    'kalshi_natgas_trader_15m.py',
    'desk6_yield_harvester.py',
    'desk7_cross_arb.py',
    'eth_trader_5m.py',
    'kalshi_gold_trader_15m.py',
    'kalshi_spx_trader_15m.py',
    'desk12_weather_metar.py',
    'whale_flow_monitor.py'
]

print("=== AUDITORIA DE RECURSOS (13 PROCESSOS) ===")
total_cpu = 0.0
total_ram_mb = 0.0
found = 0

for p in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
    try:
        pname = (p.info.get('name') or '').lower()
        if 'python' not in pname:
            continue
        cmd = ' '.join(p.info['cmdline'] or [])
        for s in target_scripts:
            if s in cmd and 'check_resources.py' not in cmd:
                ram_mb = p.info['memory_info'].rss / (1024*1024)
                cpu = p.cpu_percent(interval=0.05)
                total_cpu += cpu
                total_ram_mb += ram_mb
                found += 1
                print(f"  • {s:<28} | PID {p.info['pid']:>5} | RAM: {ram_mb:>6.1f} MB | CPU: {cpu:>4.1f}%")
                break
    except Exception:
        pass

print("=" * 65)
print(f"Processos encontrados:        {found}/{len(target_scripts)}")
print(f"Total RAM ocupada:            {total_ram_mb:.1f} MB (~{total_ram_mb/1024:.2f} GB)")
print(f"Total CPU instantâneo desks:  {total_cpu:.1f}%")
print(f"CPU Global do Sistema:        {psutil.cpu_percent()}%")
vm = psutil.virtual_memory()
print(f"RAM Total do Sistema:         {vm.total / (1024**3):.1f} GB")
print(f"RAM Disponível no Sistema:    {vm.available / (1024**3):.1f} GB ({vm.percent}% em uso)")
