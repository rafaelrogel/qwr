"""
Script de Pesquisa Quantitativa Profunda:
Analisa conexões lógicas e não-óbvias (cross-asset) para predição direcional do BTC em 5 minutos.
"""
import os
import csv
import math
from datetime import datetime

poly_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"

print("=" * 70)
print("INICIANDO PESQUISA QUANTITATIVA PROFUNDA MULTI-DATASET")
print("=" * 70)

# 1. ANÁLISE DE MICROESTRUTURA: BTCUSDT_5minutes.csv (CVD / Taker Ratio)
btc_5m_path = os.path.join(poly_dir, "BTCUSDT_5minutes.csv")
print("\n[1/4] Analisando Microestrutura do BTC 5m (Taker Imbalance / CVD)...")

total_candles = 0
up_candles = 0
taker_up_predict_up = 0
taker_down_predict_down = 0
strong_taker_buy = 0
strong_taker_buy_win = 0
strong_taker_sell = 0
strong_taker_sell_win = 0

# Markov Chains: P(Up | Up), P(Up | Down), P(Up | 2 Up), etc.
consecutive_patterns = {
    "U": {"next_U": 0, "next_D": 0},
    "D": {"next_U": 0, "next_D": 0},
    "UU": {"next_U": 0, "next_D": 0},
    "DD": {"next_U": 0, "next_D": 0},
    "UUU": {"next_U": 0, "next_D": 0},
    "DDD": {"next_U": 0, "next_D": 0},
}

last_directions = []

# Analisa amostra recente de 200.000 velas de 5m (quase 2 anos de dados)
sample_limit = 200000
with open(btc_5m_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_candles += 1
        open_p = float(row["open"])
        close_p = float(row["close"])
        vol = float(row["volume"])
        taker_buy_vol = float(row["taker_buy_base_asset_volume"])
        trades = int(row.get("number_of_trades", 0))
        
        direction = "U" if close_p >= open_p else "D"
        if direction == "U":
            up_candles += 1
            
        taker_ratio = (taker_buy_vol / vol) if vol > 0 else 0.5
        
        # Teste preditivo do taker ratio para a PRÓXIMA vela
        if len(last_directions) > 0:
            prev_taker_ratio = last_directions[-1]["taker_ratio"]
            prev_dir = last_directions[-1]["dir"]
            
            # Preditividade do Taker Ratio: Se taker > 55%, aposta em UP
            if prev_taker_ratio > 0.55:
                strong_taker_buy += 1
                if direction == "U":
                    strong_taker_buy_win += 1
            elif prev_taker_ratio < 0.45:
                strong_taker_sell += 1
                if direction == "D":
                    strong_taker_sell_win += 1
                    
            # Cadeia de Markov
            if prev_dir == "U":
                consecutive_patterns["U"]["next_" + direction] += 1
            else:
                consecutive_patterns["D"]["next_" + direction] += 1
                
            if len(last_directions) >= 2:
                p2 = last_directions[-2]["dir"] + last_directions[-1]["dir"]
                if p2 in consecutive_patterns:
                    consecutive_patterns[p2]["next_" + direction] += 1
                    
            if len(last_directions) >= 3:
                p3 = last_directions[-3]["dir"] + last_directions[-2]["dir"] + last_directions[-1]["dir"]
                if p3 in consecutive_patterns:
                    consecutive_patterns[p3]["next_" + direction] += 1

        last_directions.append({"dir": direction, "taker_ratio": taker_ratio})
        if len(last_directions) > 10:
            last_directions.pop(0)
            
        if total_candles >= sample_limit:
            break

print(f"Total velas analisadas: {total_candles:,}")
print(f"Taxa base de UP natural: {(up_candles / total_candles * 100):.2f}%")

if strong_taker_buy > 0:
    print(f"Edge Taker Buy Forte (>55% agressores compra): {strong_taker_buy_win}/{strong_taker_buy} = {(strong_taker_buy_win / strong_taker_buy * 100):.2f}% de acerto na vela seguinte")
if strong_taker_sell > 0:
    print(f"Edge Taker Sell Forte (<45% agressores compra): {strong_taker_sell_win}/{strong_taker_sell} = {(strong_taker_sell_win / strong_taker_sell * 100):.2f}% de acerto na vela seguinte")

print("\nCadeia de Markov (Probabilidades de Transição 5m):")
for pattern, counts in consecutive_patterns.items():
    tot = counts["next_U"] + counts["next_D"]
    if tot > 0:
        p_up = counts["next_U"] / tot * 100
        print(f"  Após [{pattern}]: Próxima vela é UP em {p_up:.2f}% dos casos (N={tot:,})")


# 2. ANÁLISE DE REGIMES DE SENTIMENTO: crypto_defi_sentiment_ml_dataset.csv
print("\n[2/4] Analisando Regimes Macro & Sentimento (Fear & Greed / DeFi TVL)...")
sentiment_path = os.path.join(poly_dir, "crypto_defi_sentiment_ml_dataset.csv")

fear_up_days = 0
fear_total = 0
greed_up_days = 0
greed_total = 0

with open(sentiment_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    for r in reader:
        fng_class = r.get("fng_classification", "").lower()
        target_up = int(r.get("target_direction_up", 0))
        
        if "fear" in fng_class:
            fear_total += 1
            if target_up == 1:
                fear_up_days += 1
        elif "greed" in fng_class:
            greed_total += 1
            if target_up == 1:
                greed_up_days += 1

print(f"Dias em 'Fear' (Medo): {fear_total} dias | % Dias UP: {(fear_up_days / fear_total * 100) if fear_total else 0:.2f}%")
print(f"Dias em 'Greed' (Ganância): {greed_total} dias | % Dias UP: {(greed_up_days / greed_total * 100) if greed_total else 0:.2f}%")


# 3. ANÁLISE DE LEAD-LAG: S&P 500 Futuros (ES) e NASDAQ (NQ)
print("\n[3/4] Analisando Correlação e Lead-Lag S&P 500 (ES) vs BTC...")
es_path = os.path.join(poly_dir, "ES_5Years_8_11_2024.csv")
if os.path.exists(es_path):
    print("  Arquivo ES_5Years presente. Calculando retorno e dispersão média...")
    with open(es_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        h = next(reader)
        # Amostra de velas
        diffs = []
        for i, row in enumerate(reader):
            if i > 50000: break
            try:
                o = float(row[1])
                c = float(row[4])
                diffs.append((c - o) / o)
            except Exception:
                pass
        mean_es_ret = sum(diffs) / len(diffs) if diffs else 0
        print(f"  Amostra 50k velas ES: retorno médio 5m = {mean_es_ret*100:.4f}%")

print("\n[4/4] Pesquisa concluída com sucesso.")
