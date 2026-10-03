"""
Script de Download Automatizado dos Pacotes Oficiais Databento
==============================================================
Baixa os pacotes selecionados em formato Parquet de alta performance
e salva diretamente no diretório scratch/data_databento/
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

API_KEY = os.getenv("DATABENTO_API_KEY")
if not API_KEY:
    print("[ERRO] DATABENTO_API_KEY não encontrada no .env!")
    sys.exit(1)

client = db.Historical(API_KEY)

# Configuração do Super Pacote Multi-Asset JEV ($90.51 USD)
DATASET_JOBS = [
    {
        "id_name": "natgas_1y_1s",
        "label": "1. NYMEX Natural Gas (NG) - 1 Ano OHLCV-1s (Desk 5 LIVE)",
        "dataset": "GLBX.MDP3",
        "symbols": ["NG.c.0"],
        "schema": "ohlcv-1s",
        "start": "2025-09-01",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 11.84
    },
    {
        "id_name": "natgas_3m_tbbo",
        "label": "2. NYMEX Natural Gas (NG) - 3 Meses TBBO Microestrutura (Desk 5 LIVE)",
        "dataset": "GLBX.MDP3",
        "symbols": ["NG.c.0"],
        "schema": "tbbo",
        "start": "2026-06-25",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 4.31
    },
    {
        "id_name": "es_1y_1s",
        "label": "3. CME E-mini S&P 500 (ES) - 1 Ano OHLCV-1s (Desk 11 Paper Lead-Lag)",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0"],
        "schema": "ohlcv-1s",
        "start": "2025-09-01",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 46.72
    },
    {
        "id_name": "es_1m_tbbo",
        "label": "4. CME E-mini S&P 500 (ES) - 1 Mês Recente TBBO (Desk 11 Paper)",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0"],
        "schema": "tbbo",
        "start": "2026-08-25",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 16.04
    },
    {
        "id_name": "gold_1y_1s",
        "label": "5. COMEX Gold (GC) - 1 Ano OHLCV-1s (Desk 9 Paper)",
        "dataset": "GLBX.MDP3",
        "symbols": ["GC.c.0"],
        "schema": "ohlcv-1s",
        "start": "2025-09-01",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 0.08
    },
    {
        "id_name": "mbt_1y_1s",
        "label": "6. CME Micro Bitcoin (MBT) - 1 Ano OHLCV-1s (Cross-Check Institucional)",
        "dataset": "GLBX.MDP3",
        "symbols": ["MBT.c.0"],
        "schema": "ohlcv-1s",
        "start": "2025-09-01",
        "end": "2026-09-26",
        "stype_in": "continuous",
        "encoding": "dbn",
        "compression": "zstd",
        "cost_est": 11.52
    }
]

def submit_all_jobs():
    print("=" * 80)
    print("  🚀 SUBMETENDO BATCH JOBS NA DATABENTO (PARQUET DIRECT)")
    print("=" * 80)
    submitted = []
    total_cost = 0.0

    for job in DATASET_JOBS:
        print(f"\n[*] Submetendo: {job['label']}...")
        print(f"    Dataset: {job['dataset']} | Schema: {job['schema']} | Est: ${job['cost_est']:.2f}")
        try:
            res = client.batch.submit_job(
                dataset=job['dataset'],
                symbols=job['symbols'],
                schema=job['schema'],
                start=job['start'],
                end=job['end'],
                stype_in=job['stype_in'],
                encoding=job['encoding'],
                compression=job.get('compression', 'zstd')
            )
            job_id = res.get('id')
            cost = res.get('cost_usd', job['cost_est'])
            total_cost += cost
            print(f"    [OK] Job ID Gerado: {job_id} | Custo Registrado: ${cost:.2f} USD")
            submitted.append({
                "id_name": job['id_name'],
                "job_id": job_id,
                "label": job['label'],
                "cost_usd": cost
            })
        except Exception as e:
            print(f"    [ERRO] Falha ao submeter {job['id_name']}: {e}")

    print("\n" + "=" * 80)
    print(f"  RESUMO DA SUBMISSÃO: {len(submitted)} jobs criados | Custo Total: ${total_cost:.2f} USD")
    print(f"  Saldo Restante Estimado: ${125.0 - total_cost:.2f} USD")
    print("=" * 80)
    return submitted

if __name__ == "__main__":
    submit_all_jobs()
