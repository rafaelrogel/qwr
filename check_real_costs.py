import os
from dotenv import load_dotenv
load_dotenv()
import databento as db

client = db.Historical(os.getenv("DATABENTO_API_KEY"))
jobs = client.batch.list_jobs()

total_billed = 0.0
print("=" * 80)
print("=== DETALHAMENTO DE CUSTOS REAIS DOS JOBS BAIXADOS ===")
print("=" * 80)

for j in jobs:
    cost = j.get("cost_usd")
    dataset = j.get("dataset")
    symbols = str(j.get("symbols", ""))
    schema = str(j.get("schema", ""))
    jid = j.get("id")
    state = j.get("state")
    billed_size = j.get("billed_size", 0)
    billed_mb = billed_size / (1024 * 1024) if billed_size else 0
    if cost is not None:
        total_billed += float(cost)
        print(f"{jid} | {dataset} | {symbols:8s} | {schema:8s} | {state:6s} | {billed_mb:7.2f} MB | Cost: ${float(cost):6.2f} USD")
    else:
        print(f"{jid} | {dataset} | {symbols:8s} | {schema:8s} | {state:6s} | Cost: None")

print("=" * 80)
print(f"Total Faturado Real nos Jobs: ${total_billed:.2f} USD")
rem = 125.0 - total_billed
print(f"Saldo Restante Estimado dos $125: ${rem:.2f} USD")
print("=" * 80)
