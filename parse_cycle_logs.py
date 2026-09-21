import glob
import re

log_files = [
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3790.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3984.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4110.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4169.log"
]

cycles_logged = {}

cycle_regex = re.compile(r"\[CICLO ATIVO\] Janela:\s*(\d{2}:\d{2}:\d{2})")

for lf in log_files:
    try:
        with open(lf, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        continue

    # Dividir por ciclos
    blocks = content.split("[CICLO ATIVO] Janela:")
    for b in blocks[1:]:
        header_line = b.splitlines()[0]
        m = re.match(r"\s*(\d{2}:\d{2}:\d{2})", header_line)
        if m:
            time_str = m.group(1)
            cycles_logged[time_str] = b

print(f"Total de janelas logadas encontradas: {len(cycles_logged)}")
for t in sorted(cycles_logged.keys()):
    print(f"Janela: {t}")
