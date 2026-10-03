"""
Conversor Ultrarrápido de Arquivos DBN para Parquet
===================================================
Varre o diretório scratch/data_databento/ e converte qualquer
arquivo .dbn.zst baixado da Databento para .parquet de alta performance.
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

import databento as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data_databento")

def convert_all_dbn():
    print("=" * 80)
    print("  🔄 CONVERSOR NATIVO DATABENTO DBN -> PARQUET")
    print(f"  Diretório de Busca: {DATA_DIR}")
    print("=" * 80)

    found = 0
    converted = 0

    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            if f.endswith(".dbn") or f.endswith(".dbn.zst"):
                found += 1
                dbn_path = os.path.join(root, f)
                parquet_name = f.replace(".dbn.zst", ".parquet").replace(".dbn", ".parquet")
                parquet_path = os.path.join(root, parquet_name)

                if os.path.exists(parquet_path):
                    print(f"  [✓] Já convertido: {parquet_name}")
                    continue

                print(f"  [*] Convertendo: {f} -> {parquet_name}...")
                t0 = time.time()
                try:
                    store = db.DBNStore.from_file(dbn_path)
                    store.to_parquet(parquet_path)
                    dt = time.time() - t0
                    sz_mb = os.path.getsize(parquet_path) / (1024 * 1024)
                    print(f"      [OK] Concluído em {dt:.2f}s ({sz_mb:.2f} MB)")
                    converted += 1
                except Exception as e:
                    print(f"      [ERRO] Falha ao converter {f}: {e}")

    print("=" * 80)
    print(f"  Resumo: {found} arquivos DBN encontrados | {converted} novos Parquets gerados.")
    print("=" * 80)

if __name__ == "__main__":
    convert_all_dbn()
