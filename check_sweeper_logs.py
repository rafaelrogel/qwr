import re

with open(r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4169.log", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Procurar onde aparece 255s ou Sweeper ou SCOUR
print("Ocorrências de 'SWEEPER' ou 'SCOUR':")
for m in re.finditer(r".{0,100}(SWEEPER|SCOUR|Sweeper).{0,100}", text):
    line = m.group(0).replace("\n", " ")
    if "MULTI-ADDON MONITOR" not in line:
        print("  ->", line[:150])

# Vamos ver o que o log imprimiu em torno dos 255s-270s em algumas janelas
print("\nVerificando mensagens aos 255s nas janelas recentes:")
for m in re.finditer(r"\[25\ds/300s\].*", text):
    print("  ", m.group(0)[:120])
