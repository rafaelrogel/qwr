import os
from dotenv import load_dotenv
load_dotenv()
import databento as db

client = db.Historical(os.getenv('DATABENTO_API_KEY'))
jobs = client.batch.list_jobs()
print(f"Total jobs na conta: {len(jobs)}")
for j in jobs:
    print(f"ID: {j.get('id')} | Dataset: {j.get('dataset')} | Schema: {j.get('schema')} | State: {j.get('state')} | Symbols: {j.get('symbols')} | Cost: ${j.get('cost_usd')}")
