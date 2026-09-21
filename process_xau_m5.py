import os
import zipfile
import shutil
import csv

src_zip = r"C:\Users\rafae\Desktop\archive (10).zip"
scratch_dir = r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\scratch"
os.makedirs(scratch_dir, exist_ok=True)
dest_copy = os.path.join(scratch_dir, "archive(10).zip")

print(f"1. Copiando {src_zip} -> {dest_copy}...")
shutil.copy2(src_zip, dest_copy)
print("   Cópia de segurança salva com sucesso!")

poly_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
print(f"2. Extraindo em {poly_dir}...")
with zipfile.ZipFile(dest_copy, "r") as z:
    z.extractall(poly_dir)

csv_path = os.path.join(poly_dir, "XAUUSD2020.csv")
with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.reader(f)
    header = next(reader)
    first_row = next(reader)
    row_count = 1
    last_row = first_row
    for r in reader:
        row_count += 1
        last_row = r

print(f"\n3. Concluído com sucesso:")
print(f"   Arquivo: {csv_path} ({os.path.getsize(csv_path) / (1024*1024):.2f} MB)")
print(f"   Total de velas de 5 minutos (M5): {row_count:,}")
print(f"   Colunas ({len(header)}): {header}")
print(f"   Primeira vela: {first_row}")
print(f"   Última vela: {last_row}")
