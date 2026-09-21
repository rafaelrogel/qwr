# Vamos ver exatamente:
# 1. Nas janelas onde delta aos 255s era >= 25, qual era o delta medio?
# 2. Quando o delta aos 255s e > $50, qual e a cotacao tipica na CLOB da Polymarket?
from forensic_1720_to_2141 import analysis

print("Janelas entre 17:20 e 21:40 com Delta_255s >= 25:")
count_above_965_est = 0
count_within_sweeper = 0

for a in analysis:
    d = abs(a["delta_255"])
    if d >= 25.0:
        # Se d >= 50 aos 255s (faltando 45s), o preco na CLOB tipicamente e >= 0.97
        status = "CLOB Provavelmente >= $0.97 (Sem margem de seguranca)" if d >= 45.0 else "CLOB Provavelmente entre $0.75 e $0.95 (Na faixa do Sweeper)"
        print(f"  {a['window']} | Strike: {a['strike']:.2f} | D_255: {a['delta_255']:+6.1f} | {status} | Vencedor: {a['winner']}")
