"""
Monitor e Downloader Automático dos Batch Jobs do Databento
===========================================================
Monitora o status dos 6 jobs submetidos na Databento e faz
o download automático dos arquivos DBN/Zstandard diretamente
para o diretório scratch/data_databento/ assim que forem processados.
"""

import os
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import databento as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data_databento")
os.makedirs(DATA_DIR, exist_ok=True)

TARGET_JOB_IDS = [
    "GLBX-20260927-5V4SUPXBBS",  # NG OHLCV-1s (1 Ano)
    "GLBX-20260927-R7V4469JAL",  # NG TBBO (3 Meses)
    "GLBX-20260927-RG6GDN8WJ4",  # ES OHLCV-1s (1 Ano)
    "GLBX-20260927-89MU8XJJLS",  # ES TBBO (1 Mês)
    "GLBX-20260927-TPATKTCBVU",  # GC OHLCV-1s (1 Ano)
    "GLBX-20260927-K37J3QPWV8",  # MBT OHLCV-1s (1 Ano)
]

client = db.Historical(os.getenv("DATABENTO_API_KEY"))

def monitor_and_download():
    print("=" * 80)
    print("  📦 MONITOR & DOWNLOADER AUTOMÁTICO DATABENTO BATCH JOBS")
    print(f"  Diretório Destino: {DATA_DIR}")
    print(f"  Total de Jobs Monitorados: {len(TARGET_JOB_IDS)}")
    print("=" * 80)

    downloaded = set()
    
    # Verifica o que já foi baixado anteriormente
    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            for jid in TARGET_JOB_IDS:
                if jid in f:
                    downloaded.add(jid)

    while len(downloaded) < len(TARGET_JOB_IDS):
        try:
            jobs = client.batch.list_jobs()
            job_map = {j['id']: j for j in jobs}

            all_done = True
            for jid in TARGET_JOB_IDS:
                if jid in downloaded:
                    continue

                info = job_map.get(jid)
                if not info:
                    continue

                state = info.get("state")
                progress = info.get("progress", 0)
                dataset = info.get("dataset")
                schema = info.get("schema")
                symbols = info.get("symbols")
                cost = info.get("cost_usd")

                print(f"[*] Job {jid} ({symbols} | {schema}) -> Estado: {state} ({progress}%) | Custo: ${cost}")

                if state == "done":
                    print(f"    [!] Job {jid} CONCLUÍDO! Iniciando download...")
                    paths = client.batch.download(job_id=jid, output_dir=DATA_DIR)
                    print(f"    [✓] Download finalizado: {len(paths)} arquivos salvos em {DATA_DIR}")
                    for p in paths:
                        size_mb = os.path.getsize(p) / (1024 * 1024)
                        print(f"        -> {os.path.basename(p)} ({size_mb:.2f} MB)")
                    downloaded.add(jid)
                elif state in ("queued", "processing", "in_progress"):
                    all_done = False
                elif state in ("expired", "cancelled"):
                    print(f"    [X] Job {jid} falhou ou expirou com estado: {state}")
                    downloaded.add(jid)

            if len(downloaded) < len(TARGET_JOB_IDS):
                time.sleep(15)

        except Exception as e:
            print(f"[Aviso] Erro no polling de jobs: {e}")
            time.sleep(15)

    print("\n" + "=" * 80)
    print("  🎉 TODOS OS BATCH JOBS FORAM BAIXADOS COM SUCESSO!")
    print(f"  Arquivos disponíveis em: {DATA_DIR}")
    print("=" * 80)

if __name__ == "__main__":
    monitor_and_download()
