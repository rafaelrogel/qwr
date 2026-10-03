import duckdb

print("Conectando ao DuckDB e carregando extensão HTTPFS...")
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")

url = "https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data/resolve/main/markets.parquet"
print(f"Lendo cabeçalho e estatísticas remotas de: {url}")
try:
    cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{url}')").df()
    print(f"\n[OK] Colunas no markets.parquet ({len(cols)} colunas):")
    print(cols[["column_name", "column_type"]].to_string())

    total = con.execute(f"SELECT count(*) FROM read_parquet('{url}')").fetchone()[0]
    print(f"\n[OK] Total de mercados catalogados: {total:,}")

    sample = con.execute(f"SELECT question, volume, created_at FROM read_parquet('{url}') ORDER BY volume DESC LIMIT 5").df()
    print("\n[OK] Top 5 maiores mercados históricos por volume:")
    print(sample.to_string())
except Exception as e:
    print(f"Erro na consulta DuckDB: {e}")
