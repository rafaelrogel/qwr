"""
Submissão e Download Automático do Combo A Databento ($30.19 USD)
================================================================
1. NYMEX Natural Gas (NG.c.0) - 1 Ano Completo TBBO ($24.26)
2. COMEX Gold (GC.c.0) - 1 Ano Completo TBBO ($0.09)
3. CME Micro Bitcoin (MBT.c.0) - 6 Meses TBBO ($5.84)
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

client = db.Historical(os.getenv("DATABENTO_API_KEY"))

JOBS_COMBO_A = [
    {
        "id_name": "ng_1y_tbbo_full",
        "label": "1. NYMEX Natural Gas (NG) - 1 Ano Completo TBBO (52 Semanas EIA)",
        "dataset": "GLBX.MDP3",
        "symbols": ["NG.c.0"],
        "schema": "tbbo",
        "start": "2025-09-01",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 24.26
    },
    {
        "id_name": "gc_1y_tbbo_full",
        "label": "2. COMEX Gold (GC) - 1 Ano Completo TBBO",
        "dataset": "GLBX.MDP3",
        "symbols": ["GC.c.0"],
        "schema": "tbbo",
        "start": "2025-09-01",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 0.09
    },
    {
        "id_name": "mbt_6m_tbbo_full",
        "label": "3. CME Micro Bitcoin (MBT) - 6 Meses TBBO",
        "dataset": "GLBX.MDP3",
        "symbols": ["MBT.c.0"],
        "schema": "tbbo",
        "start": "2026-03-25",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 5.84
    }
]

def submit_jobs():
    print("=" * 80)
    print("  🚀 SUBMETENDO BATCH JOBS DO COMBO A NA DATABENTO")
    print("=" * 80)

    active_job_ids = []

    for job in JOBS_COMBO_A:
        print(f"\n[*] Submetendo: {job['label']}...")
        try:
            res = client.batch.submit_job(
                dataset=job['dataset'],
                symbols=job['symbols'],
                schema=job['schema'],
                start=job['start'],
                end=job['end'],
                stype_in=job['stype_in'],
                encoding=job['encoding'],
                compression=job['compression']
            )
            jid = res.get('id')
            print(f"    [OK] Job Criado: {jid} | Estado: {res.get('state')}")
            active_job_ids.append(jid)
        except Exception as e:
            print(f"    [ERRO] Falha ao submeter {job['id_name']}: {e}")

    print("\n" + "=" * 80)
    print(f"  {len(active_job_ids)} JOBS SUBMETIDOS COM SUCESSO! MONITORANDO DOWNLOAD...")
    print("=" * 80)
    return active_job_ids

def monitor_and_download(target_jids):
    downloaded = set()

    while len(downloaded) < len(target_jids):
        try:
            jobs = client.batch.list_jobs()
            job_map = {j['id']: j for j in jobs}

            for jid in target_jids:
                if jid in downloaded:
                    continue

                info = job_map.get(jid)
                if not info:
                    continue

                state = info.get("state")
                progress = info.get("progress", 0)
                symbols = info.get("symbols")
                schema = info.get("schema")
                cost = info.get("cost_usd")

                print(f"[*] Job {jid} ({symbols} | {schema}) -> Estado: {state} ({progress}%) | Custo: ${cost}", flush=True)

                if state == "done":
                    print(f"    [!] Job {jid} CONCLUÍDO! Baixando arquivos...", flush=True)
                    paths = client.batch.download(job_id=jid, output_dir=DATA_DIR)
                    print(f"    [✓] Salvo com sucesso: {len(paths)} arquivos!", flush=True)
                    downloaded.add(jid)
                elif state in ("expired", "cancelled"):
                    print(f"    [X] Job {jid} falhou ou expirou!", flush=True)
                    downloaded.add(jid)

            if len(downloaded) < len(target_jids):
                time.sleep(15)

        except Exception as e:
            print(f"[Aviso] Erro no loop de polling: {e}", flush=True)
            time.sleep(15)

    print("\n" + "=" * 80)
    print("  🎉 TODOS OS ARQUIVOS DO COMBO A FORAM BAIXADOS E INTEGRADOS COM SUCESSO!")
    print(f"  Diretório: {DATA_DIR}")
    print("=" * 80)

if __name__ == "__main__":
    jids = submit_jobs()
    if jids:
        monitor_and_download(jids)
