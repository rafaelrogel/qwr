import re

with open(r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4169.log", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

print("Procurando 'Sweeper Ignorado':")
found = False
for m in re.finditer(r".{0,50}Sweeper Ignorado.{0,50}", text):
    print("  ->", m.group(0))
    found = True
if not found:
    print("  -> Nenhuma ocorrência de 'Sweeper Ignorado'.")

print("\nProcurando 'BTC5MSCOUR SWEEPER DISPARADO':")
found2 = False
for m in re.finditer(r".{0,50}BTC5MSCOUR SWEEPER DISPARADO.{0,50}", text):
    print("  ->", m.group(0))
    found2 = True
if not found2:
    print("  -> Nenhuma ocorrência de 'BTC5MSCOUR SWEEPER DISPARADO'.")
