import json
import re

# Vamos inspecionar exatamente as janelas onde Preço > 0.65 ou Preço < 0.35
from detailed_forensic_analysis import cycles, target_windows

# Pegar os resultados reais de fechamento de cada vela
import urllib.request

now_ms = 1789928500 * 1000 # aproximado
start_ms = 1789917600 * 1000 # 15:20 UTC

url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={start_ms}&limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    klines = json.loads(r.read().decode())

candles = {}
for k in klines:
    ts = int(k[0]) // 1000
    candles[ts] = {"open": float(k[1]), "close": float(k[4])}

print(f"{'JANELA':<10} | {'DELTA 135s':<10} | {'PRECO CLOB':<12} | {'SINAL 135s':<10} | {'FINAL WINNER':<12} | {'SE TIVESSE ENTRADO A >0.65':<28} | {'REVERSAO DE MERCADO?'}")
print("-" * 115)

for tw in target_windows:
    b = cycles.get(tw)
    if not b:
        continue

    # Extrair hora e timestamp
    m_ts = re.search(r"window_ts:?\s*(\d+)", b)
    # se nao tem, calcular pela hora
    # vamos achar na candles
    # No log tem: Strike Oraculo Chainlink (K): $81,080.40
    m_strike = re.search(r"Strike Oraculo Chainlink \(K\):\s*\$([\d\.,]+)", b)
    strike_str = m_strike.group(1).replace(",", "") if m_strike else "0"
    strike = float(strike_str)

    m_delta = re.search(r"Drift Real \(Delta\):\s*\$([-\+\d\.,]+)", b)
    delta_val = float(m_delta.group(1).replace(",", "")) if m_delta else 0.0

    m_fp = re.search(r"Preco \$([0-9\.]+) (>|<) \$([0-9\.]+)", b)
    price_val = float(m_fp.group(1)) if m_fp else None

    # Vencedor real da vela no log:
    winner = "N/A"
    if "Vencedor Apurado: UP" in b or "winner: UP" in b or "Vencedor Oficial: UP" in b:
        winner = "UP"
    elif "Vencedor Apurado: DOWN" in b or "winner: DOWN" in b or "Vencedor Oficial: DOWN" in b:
        winner = "DOWN"
    else:
        # buscar no fechamento do log
        m_win = re.search(r"Vencedor Oficial:\s*(UP|DOWN)", b)
        if m_win:
            winner = m_win.group(1)

    signal_135 = "UP" if delta_val > 0 else "DOWN"

    reversal = "Nao"
    if winner != "N/A" and winner != signal_135 and abs(delta_val) >= 15:
        reversal = "SIM! (VIROU DO 135s ATE O FIM)"

    hypo_outcome = "N/A"
    if winner != "N/A":
        if signal_135 == winner:
            hypo_outcome = "GANHARIA (Lucro pequeno)"
        else:
            hypo_outcome = "PERDERIA TUDO (-$1.00!)"

    p_str = f"${price_val:.2f}" if price_val else "N/A"
    print(f"{tw:<10} | {delta_val:+10.2f} | {p_str:<12} | {signal_135:<10} | {winner:<12} | {hypo_outcome:<28} | {reversal}")
