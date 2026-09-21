import re
import json

log_path = r'C:/Users/rafae/.gemini/antigravity/brain/c125241d-a48c-4ba7-aab4-bba800620ab2/.system_generated/tasks/task-4965.log'
with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

cycles_raw = text.split('[CICLO ATIVO] Janela: ')
print(f'Total raw cycles found: {len(cycles_raw)}')

skipped = []

for c in cycles_raw[1:]:
    lines = c.split('\n')
    header = lines[0].strip()
    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', header)
    time_str = time_match.group(1) if time_match else 'UNKNOWN'
    
    had_trade = ('ORDEM PRIM' in c) or ('SWEEPER EXECUTADO' in c) or ('HEDGE EXECUTADO' in c)
    if had_trade:
        continue
    
    price_filter = re.search(r'FILTRO DE PRECO\]: Preco \$([\d\.]+) > \$0.65', c)
    sweeper_ignored = re.search(r'Sweeper Ignorado\] Cotação \$([\d\.]+) > \$0.975', c)
    sweeper_espera = re.search(r'Sweeper em Espera\] Binance Drift \(\$([+\-\d\.]+)\)', c)
    cvd_rejection = re.search(r'FILTRO CVD.*?Rejeitando', c)
    
    spot_135_m = re.search(r'Spot Chainlink aos 135s: \$([\d\.,]+) \| Drift Real \(Delta\): \$([+\-\d\.]+)', c)
    all_spots = re.findall(r'\[(\d+)s/300s\] Chainlink: \$([\d\.,]+) \(Delta: ([+\-\d\.]+)\)', c)
    
    if spot_135_m and all_spots:
        delta_135 = float(spot_135_m.group(2))
        last_delta = float(all_spots[-1][2])
        winner_would_be = 'UP' if last_delta > 0 else 'DOWN'
        trend_135 = 'UP' if delta_135 > 0 else 'DOWN'
        
        correct_direction = (trend_135 == winner_would_be) and abs(last_delta) >= 15
        
        skipped.append({
            'time': time_str,
            'delta_135': delta_135,
            'last_delta': last_delta,
            'winner': winner_would_be,
            'correct_direction': correct_direction,
            'price_filter': float(price_filter.group(1)) if price_filter else None,
            'sweeper_ignored': float(sweeper_ignored.group(1)) if sweeper_ignored else None,
            'cvd_rejection': bool(cvd_rejection)
        })

print(f'Total non-trade cycles: {len(skipped)}')
correct_signals = [s for s in skipped if s['correct_direction']]
print(f'Cycles where 135s signal was correct: {len(correct_signals)}')

print('\n--- DETALHES DOS CICLOS PULADOS ONDE A DIREÇÃO ESTAVA CERTA ---')
for s in correct_signals:
    p_str = f"CLOB Price: ${s['price_filter']:.2f}" if s['price_filter'] else "No CLOB Price"
    sw_str = f"Sweeper > 0.975 ($ {s['sweeper_ignored']:.2f})" if s['sweeper_ignored'] else ""
    cvd_str = "CVD Rejection" if s['cvd_rejection'] else ""
    reasons = " | ".join(filter(None, [p_str, sw_str, cvd_str]))
    print(f"[{s['time']}] 135s: {s['delta_135']:+0.2f} -> End: {s['last_delta']:+0.2f} ({s['winner']}) | {reasons}")
