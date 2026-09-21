"""
Pesquisa de Microestrutura Intra-Candle (1m dentro da vela de 5m)
Carrega BTCUSDT_1minute.csv e agrupa em blocos de 5 minutos:
Calcula: Se o minuto 1, 2, 3 estiverem UP (ou acumulando delta positivo),
qual a probabilidade de fechamento da vela de 5m em UP?
"""
import os
import csv

poly_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
csv_1m = os.path.join(poly_dir, "BTCUSDT_1minute.csv")

print("Analisando intra-candle 1m dentro de blocos de 5m...")

# Agrupa velas de 1m por bloco de 5m (timestamp // 300000)
blocks = {}
total_read = 0
sample_limit = 500000 # 500k minutos = ~100k velas de 5m

with open(csv_1m, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ts = int(row["timestamp"])
        block_id = ts // 300000
        minute_idx = (ts % 300000) // 60000 # 0, 1, 2, 3, 4
        
        if block_id not in blocks:
            blocks[block_id] = [None] * 5
            
        if 0 <= minute_idx < 5:
            blocks[block_id][minute_idx] = {
                "open": float(row["open"]),
                "close": float(row["close"]),
                "vol": float(row["volume"]),
                "taker_buy": float(row["taker_buy_base_asset_volume"])
            }
            
        total_read += 1
        if total_read >= sample_limit:
            break

print(f"Total de minutos lidos: {total_read:,} | Blocos completos de 5m formados: {len(blocks):,}")

# Analisa predição intra-candle
valid_blocks = 0
# Testes:
# Teste A: Sinal no minuto 1 (após 60 segundos)
m1_up_total = 0
m1_up_finish_up = 0

# Teste B: Sinal no minuto 2 (após 120 segundos)
m2_cum_up_total = 0
m2_cum_up_finish_up = 0

# Teste C: Sinal no minuto 3 (após 180 segundos)
m3_cum_up_total = 0
m3_cum_up_finish_up = 0

# Teste D: Sinal no minuto 4 (após 240 segundos - Reta final 60s)
m4_cum_up_total = 0
m4_cum_up_finish_up = 0

for block_id, mins in blocks.items():
    if any(m is None for m in mins):
        continue
    valid_blocks += 1
    
    strike = mins[0]["open"]
    close_5m = mins[4]["close"]
    final_is_up = close_5m >= strike
    
    # Minuto 1 (decorrido 60s)
    m1_close = mins[0]["close"]
    if m1_close > strike:
        m1_up_total += 1
        if final_is_up:
            m1_up_finish_up += 1
            
    # Minuto 2 (decorrido 120s)
    m2_close = mins[1]["close"]
    if m2_close > strike:
        m2_cum_up_total += 1
        if final_is_up:
            m2_cum_up_finish_up += 1

    # Minuto 3 (decorrido 180s)
    m3_close = mins[2]["close"]
    if m3_close > strike:
        m3_cum_up_total += 1
        if final_is_up:
            m3_cum_up_finish_up += 1

    # Minuto 4 (decorrido 240s - Últimos 60 segundos)
    m4_close = mins[3]["close"]
    if m4_close > strike:
        m4_cum_up_total += 1
        if final_is_up:
            m4_cum_up_finish_up += 1

print(f"\nResultados Intra-Candle (N = {valid_blocks:,} velas completas de 5m):")
print(f"1. Após 60s (Minuto 1 > Strike):  {m1_up_finish_up}/{m1_up_total} = {(m1_up_finish_up / m1_up_total * 100):.2f}% fecham em UP")
print(f"2. Após 120s (Minuto 2 > Strike): {m2_cum_up_finish_up}/{m2_cum_up_total} = {(m2_cum_up_finish_up / m2_cum_up_total * 100):.2f}% fecham em UP")
print(f"3. Após 180s (Minuto 3 > Strike): {m3_cum_up_finish_up}/{m3_cum_up_total} = {(m3_cum_up_finish_up / m3_cum_up_total * 100):.2f}% fecham em UP")
print(f"4. Após 240s (Minuto 4 > Strike - Final 60s): {m4_cum_up_finish_up}/{m4_cum_up_total} = {(m4_cum_up_finish_up / m4_cum_up_total * 100):.2f}% fecham em UP")
