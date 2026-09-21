import os
import zipfile
import shutil
import csv

desktop = r"C:\Users\rafae\Desktop"
target_zip = None

# Localiza arquivo archive (25).zip ou archive(25).zip
for f in os.listdir(desktop):
    if "archive" in f.lower() and "25" in f and f.endswith(".zip"):
        target_zip = os.path.join(desktop, f)
        break

if not target_zip:
    print("Arquivo archive(25).zip não encontrado. Lista de zips no Desktop:")
    for f in os.listdir(desktop):
        if f.endswith(".zip"):
            print(" ", f)
    exit(1)

size_mb = os.path.getsize(target_zip) / (1024*1024)
print(f"1. Arquivo localizado: {target_zip} ({size_mb:.2f} MB)")

scratch_dir = r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\scratch"
os.makedirs(scratch_dir, exist_ok=True)
dest_copy = os.path.join(scratch_dir, "archive(25).zip")

print(f"2. Copiando para segurança -> {dest_copy}...")
shutil.copy2(target_zip, dest_copy)
print("   Cópia de segurança concluída!")

poly_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
print(f"3. Extraindo na pasta {poly_dir}...")

extracted_files = []
with zipfile.ZipFile(dest_copy, "r") as z:
    for item in z.infolist():
        target_name = item.filename
        if target_name == "README.md":
            target_name = "README_btcusdt_5m.md"
        dest_path = os.path.join(poly_dir, target_name)
        if item.is_dir():
            os.makedirs(dest_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with z.open(item) as src_f, open(dest_path, "wb") as dst_f:
                dst_f.write(src_f.read())
            extracted_files.append((target_name, os.path.getsize(dest_path)))

print(f"\n4. Total de arquivos extraídos: {len(extracted_files)}")
for name, size in extracted_files:
    print(f"   - {name} ({size / (1024*1024):.2f} MB)")

# Amostra do CSV
main_csv = None
for name, _ in extracted_files:
    if name.endswith(".csv"):
        main_csv = os.path.join(poly_dir, name)
        break

if main_csv and os.path.exists(main_csv):
    with open(main_csv, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader)
        first_row = next(reader)
        count = 1
        last_row = first_row
        for r in reader:
            count += 1
            last_row = r
    print(f"\n5. Amostra de ({os.path.basename(main_csv)}):")
    print(f"   Total de velas M5 (5 minutos): {count:,}")
    print(f"   Colunas ({len(header)}): {header}")
    print(f"   Primeira vela: {first_row}")
    print(f"   Última vela: {last_row}")
