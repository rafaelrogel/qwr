import glob
import os
from datetime import datetime

task_files = glob.glob(r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-*.log")
tasks = []
for tf in task_files:
    mtime = os.path.getmtime(tf)
    base = os.path.basename(tf)
    tasks.append((mtime, base, tf))

tasks.sort()
# ultimos 15 tasks
for mtime, base, tf in tasks[-15:]:
    dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    size = os.path.getsize(tf)
    with open(tf, "r", encoding="utf-8", errors="ignore") as f:
        first_line = f.readline().strip()[:60]
    print(f"{base} | {dt} | size={size} | {first_line}")
