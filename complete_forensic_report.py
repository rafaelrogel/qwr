import sys
import json
import urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

# 1. Carregar velas de 1m da Binance cobrindo das 15:40 UTC até 18:25 UTC
# (que é das 16:40 até 19:25 no fuso UTC+1 do usuário)
start_ms = 1789920000 * 1000 - (3600 * 1000) # pegar margem
now_ms = int(datetime.now().timestamp() * 1000)

url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={start_ms}&limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    klines = json.loads(r.read().decode())

candles = {}
for k in klines:
    ts = int(k[0]) // 1000
    candles[ts] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "vol": float(k[5])
    }

from detailed_forensic_analysis import cycles

# Janelas das 16:50 até 19:15
windows = [
    "16:50:00", "16:55:00", "17:00:00", "17:05:00", "17:10:00", "17:15:00", "17:20:00",
    "17:25:00", "17:30:00", "17:35:00", "17:40:00", "17:45:00", "17:50:00", "17:55:00",
    "18:00:00", "18:05:00", "18:10:00", "18:15:00", "18:20:00", "18:25:00", "18:30:00",
    "18:35:00", "18:40:00", "18:45:00", "18:50:00", "18:55:00", "19:00:00", "19:05:00",
    "19:10:00", "19:15:00"
]

import re

results = []

for tw in windows:
    b = cycles.get(tw, "")
    
    # Extrair Strike do log
    m_strike = re.search(r"Strike Oraculo Chainlink \(K\):\s*\$([\d\.,]+)", b)
    strike_val = float(m_strike.group(1).replace(",", "")) if m_strike else 0.0

    # Extrair Delta aos 135s do log
    m_delta = re.search(r"Drift Real \(Delta\):\s*\$([-\+\d\.,]+)", b)
    delta_135 = float(m_delta.group(1).replace(",", "")) if m_delta else 0.0

    # Motivo do skip / decisao
    motivo = "Ocioso"
    if "FILTRO DE RUIDO DEADBAND" in b:
        motivo = "Deadband (< $15)"
    elif "FILTRO DE PRECO" in b:
        m_fp = re.search(r"Preco \$([0-9\.]+) (>|<) \$([0-9\.]+)", b)
        if m_fp:
            motivo = f"Preço CLOB ({m_fp.group(1)}) fora de [0.35, 0.65]"
        else:
            motivo = "Preço fora da faixa"
    elif "FILTRO DE IMBALANCE CLOB" in b:
        motivo = "Desbalanceamento Book (Ask/Bid Wall)"
    elif "FILTRO DE DIVERGENCIA BINANCE" in b:
        motivo = "Divergência Binance/Chainlink"
    elif "ENTRADA PRIMARIA EXECUTADA" in b or "ORDEM AO VIVO ENVIADA" in b:
        motivo = "TRADE REAL EXECUTADO"
    elif "VITORIA (SCOUR SWEEPER)" in b or "ORDEM SWEEPER EXECUTADA" in b:
        motivo = "SWEEPER EXECUTADO"

    # Procurar o timestamp correspondente para ver o fechamento da vela
    # Achar vela na candles cujo open seja proximo do strike
    matched_ts = None
    min_diff = 999999
    for ts, c in candles.items():
        if ts % 300 == 0:
            diff = abs(c["open"] - strike_val)
            if diff < min_diff:
                min_diff = diff
                matched_ts = ts

    winner = "N/A"
    final_close = 0.0
    if matched_ts and min_diff < 50.0:
        c4 = candles.get(matched_ts + 240)
        if c4:
            final_close = c4["close"]
            winner = "UP" if final_close >= strike_val else "DOWN"

    # Analise: O que aconteceria se tivessemos entrado na direcao do Delta 135s?
    signal_135 = "UP" if delta_135 > 0 else "DOWN"
    
    status_135 = "N/A"
    if winner != "N/A":
        if abs(delta_135) < 15.0:
            status_135 = f"Ruído (Fechou {winner})"
        elif signal_135 == winner:
            status_135 = f"Acertaria ({winner})"
        else:
            status_135 = f"ERRARIA! Viroi p/ {winner} (Salvo pelo filtro!)"

    # Verificar se o Sweeper (255s) teve oportunidade
    # Pegar candle do minuto 4
    sweeper_opp = "N/A"
    if matched_ts:
        c4 = candles.get(matched_ts + 240)
        if c4:
            delta_255 = c4["open"] - strike_val
            if abs(delta_255) >= 25.0:
                sw_side = "UP" if delta_255 > 0 else "DOWN"
                if sw_side == winner:
                    sweeper_opp = f"Sweeper {sw_side} (+)"
                else:
                    sweeper_opp = f"Sweeper {sw_side} (-)"
            else:
                sweeper_opp = f"Delta 255s baixo ({delta_255:+.1f})"

    results.append({
        "janela": tw,
        "strike": strike_val,
        "delta_135": delta_135,
        "motivo": motivo,
        "winner": winner,
        "status_135": status_135,
        "sweeper_opp": sweeper_opp,
        "log_snippet": b
    })

print(f"{'JANELA':<9} | {'STRIKE':<9} | {'DELTA 135s':<11} | {'FILTRO / ACAO DO BOT':<38} | {'WINNER':<7} | {'SE ENTRASSE AOS 135s':<35} | {'SWEEPER 255s'}")
print("-" * 135)
for r in results:
    print(f"{r['janela']:<9} | {r['strike']:9.2f} | {r['delta_135']:+10.2f} | {r['motivo']:<38} | {r['winner']:<7} | {r['status_135']:<35} | {r['sweeper_opp']}")
