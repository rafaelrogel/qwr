import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3984.log", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

idx = text.find("18:30:00")
if idx != -1:
    print(text[idx-50:idx+2500])
else:
    print("18:30:00 nao encontrado")
