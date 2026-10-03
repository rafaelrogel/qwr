import os
from dotenv import load_dotenv
load_dotenv()
import databento as db

client = db.Historical(os.getenv("DATABENTO_API_KEY"))

candidates = [
    # 1. 1 Ano Completo de TBBO em Natural Gas (Cobre todas as 52 EIAs do ano!)
    {"name": "NG TBBO (1 Ano Completo)", "dataset": "GLBX.MDP3", "symbols": ["NG.c.0"], "schema": "tbbo", "start": "2025-09-01", "end": "2026-09-26", "stype_in": "continuous"},
    
    # 2. 1 Ano Completo de TBBO em COMEX Gold (Microestrutura de Ouro!)
    {"name": "GC TBBO (1 Ano Completo)", "dataset": "GLBX.MDP3", "symbols": ["GC.c.0"], "schema": "tbbo", "start": "2025-09-01", "end": "2026-09-26", "stype_in": "continuous"},
    
    # 3. Nasdaq 100 Futures (NQ.c.0) - Modelo Chris Creamer / Kalshi KXNDX15M
    {"name": "NQ OHLCV-1s (6 Meses)", "dataset": "GLBX.MDP3", "symbols": ["NQ.c.0"], "schema": "ohlcv-1s", "start": "2026-03-25", "end": "2026-09-26", "stype_in": "continuous"},
    {"name": "MNQ OHLCV-1s (6 Meses)", "dataset": "GLBX.MDP3", "symbols": ["MNQ.c.0"], "schema": "ohlcv-1s", "start": "2026-03-25", "end": "2026-09-26", "stype_in": "continuous"},

    # 4. WTI Crude Oil (CL.c.0) - Par Macro com Natural Gas
    {"name": "CL OHLCV-1s (1 Ano)", "dataset": "GLBX.MDP3", "symbols": ["CL.c.0"], "schema": "ohlcv-1s", "start": "2025-09-01", "end": "2026-09-26", "stype_in": "continuous"},
    {"name": "CL OHLCV-1s (6 Meses)", "dataset": "GLBX.MDP3", "symbols": ["CL.c.0"], "schema": "ohlcv-1s", "start": "2026-03-25", "end": "2026-09-26", "stype_in": "continuous"},

    # 5. Micro Bitcoin TBBO (MBT.c.0)
    {"name": "MBT TBBO (6 Meses)", "dataset": "GLBX.MDP3", "symbols": ["MBT.c.0"], "schema": "tbbo", "start": "2026-03-25", "end": "2026-09-26", "stype_in": "continuous"},
]

print("=" * 80)
print("=== COTAÇÃO DE CANDIDATOS PARA CONSUMIR OS $34.49 RESTANTES ===")
print("=" * 80)

for q in candidates:
    try:
        cost = client.metadata.get_cost(
            dataset=q["dataset"],
            symbols=q["symbols"],
            schema=q["schema"],
            start=q["start"],
            end=q["end"],
            stype_in=q["stype_in"]
        )
        size = client.metadata.get_billable_size(
            dataset=q["dataset"],
            symbols=q["symbols"],
            schema=q["schema"],
            start=q["start"],
            end=q["end"],
            stype_in=q["stype_in"]
        )
        mb = size / (1024 * 1024)
        print(f"  [OK] {q['name']:32s} | Tamanho: {mb:8.2f} MB | Custo: ${cost:6.2f} USD")
    except Exception as e:
        print(f"  [!]  {q['name']:32s} | Erro: {e}")

print("=" * 80)
