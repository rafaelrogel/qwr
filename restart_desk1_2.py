import psutil
import subprocess
import time

# Kill old live_trader_5m and sol_trader_5m
killed = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = ' '.join(p.info['cmdline'] or [])
        if ('live_trader_5m.py' in cmd or 'sol_trader_5m.py' in cmd) and p.info['pid'] != psutil.Process().pid:
            p.kill()
            killed.append((p.info['pid'], p.info['name']))
    except Exception:
        pass

print(f"Killed {len(killed)} old processes: {killed}")
time.sleep(1.5)

# Launch Desk 1
cmd1 = 'start "AGY - Desk 1 (BTC 5m Live)" /min cmd /k "cd /d C:\\Users\\rafae\\.gemini\\antigravity\\scratch\\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u live_trader_5m.py"'
subprocess.Popen(cmd1, shell=True, cwd=r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot")

# Launch Desk 2
cmd2 = 'start "AGY - Desk 2 (SOL 5m Live)" /min cmd /k "cd /d C:\\Users\\rafae\\.gemini\\antigravity\\scratch\\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u sol_trader_5m.py"'
subprocess.Popen(cmd2, shell=True, cwd=r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot")

time.sleep(2.0)
print("Restart completed successfully.")
