import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()
import databento as db

client = db.Historical(os.getenv('DATABENTO_API_KEY'))

test_queries = [
    # Natural Gas (Desk 5 LIVE & Desk 4 Paper)
    {'name': 'NG OHLCV-1s (1 Ano Completo)', 'dataset': 'GLBX.MDP3', 'symbols': ['NG.c.0'], 'schema': 'ohlcv-1s', 'start': '2025-09-01', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'NG OHLCV-1s (2 Anos)', 'dataset': 'GLBX.MDP3', 'symbols': ['NG.c.0'], 'schema': 'ohlcv-1s', 'start': '2024-09-01', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'NG TBBO (1 Mês Recente)', 'dataset': 'GLBX.MDP3', 'symbols': ['NG.c.0'], 'schema': 'tbbo', 'start': '2026-08-25', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'NG TBBO (3 Meses)', 'dataset': 'GLBX.MDP3', 'symbols': ['NG.c.0'], 'schema': 'tbbo', 'start': '2026-06-25', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'NG Trades (6 Meses)', 'dataset': 'GLBX.MDP3', 'symbols': ['NG.c.0'], 'schema': 'trades', 'start': '2026-03-25', 'end': '2026-09-26', 'stype_in': 'continuous'},
    
    # E-mini S&P 500 (Desk 11 Paper)
    {'name': 'ES OHLCV-1s (1 Ano Completo)', 'dataset': 'GLBX.MDP3', 'symbols': ['ES.c.0'], 'schema': 'ohlcv-1s', 'start': '2025-09-01', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'ES OHLCV-1s (2 Anos)', 'dataset': 'GLBX.MDP3', 'symbols': ['ES.c.0'], 'schema': 'ohlcv-1s', 'start': '2024-09-01', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'ES TBBO (1 Mês Recente)', 'dataset': 'GLBX.MDP3', 'symbols': ['ES.c.0'], 'schema': 'tbbo', 'start': '2026-08-25', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'ES Trades (3 Meses)', 'dataset': 'GLBX.MDP3', 'symbols': ['ES.c.0'], 'schema': 'trades', 'start': '2026-06-25', 'end': '2026-09-26', 'stype_in': 'continuous'},
    
    # COMEX Gold (Desk 9 Paper)
    {'name': 'GC OHLCV-1s (1 Ano Completo)', 'dataset': 'GLBX.MDP3', 'symbols': ['GC.c.0'], 'schema': 'ohlcv-1s', 'start': '2025-09-01', 'end': '2026-09-26', 'stype_in': 'continuous'},
    {'name': 'GC TBBO (1 Mês Recente)', 'dataset': 'GLBX.MDP3', 'symbols': ['GC.c.0'], 'schema': 'tbbo', 'start': '2026-08-25', 'end': '2026-09-26', 'stype_in': 'continuous'},

    # Micro Bitcoin CME (Desk 1, 3, 10)
    {'name': 'MBT OHLCV-1s (1 Ano Completo)', 'dataset': 'GLBX.MDP3', 'symbols': ['MBT.c.0'], 'schema': 'ohlcv-1s', 'start': '2025-09-01', 'end': '2026-09-26', 'stype_in': 'continuous'},
]

print("=" * 80)
print("  ORÇAMENTO FORMAL DATABENTO: CONSULTA DE CUSTOS (METADATA.GET_COST)")
print("  Orçamento Disponível: $125.00 USD")
print("=" * 80)

for q in test_queries:
    try:
        cost = client.metadata.get_cost(
            dataset=q['dataset'],
            symbols=q['symbols'],
            schema=q['schema'],
            start=q['start'],
            end=q['end'],
            stype_in=q['stype_in']
        )
        # Obter também o tamanho estimado em bytes
        size = client.metadata.get_billable_size(
            dataset=q['dataset'],
            symbols=q['symbols'],
            schema=q['schema'],
            start=q['start'],
            end=q['end'],
            stype_in=q['stype_in']
        )
        mb = size / (1024 * 1024)
        print(f"  [OK] {q['name']:32s} | Tamanho: {mb:8.2f} MB | Custo: ${cost:6.2f} USD", flush=True)
    except Exception as e:
        print(f"  [!]  {q['name']:32s} | Erro: {e}", flush=True)

print("=" * 80)
