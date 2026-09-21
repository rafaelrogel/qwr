import re
import sys

log_path = r'C:/Users/rafae/.gemini/antigravity/brain/c125241d-a48c-4ba7-aab4-bba800620ab2/.system_generated/tasks/task-4965.log'
with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

cycles = text.split('[CICLO ATIVO] Janela: ')

skipped_p66_75 = []
cvd_rejections = []
drift_rejections = []
deadband_skips = []

for c in cycles[1:]:
    had_trade = ('ORDEM PRIM' in c) or ('SWEEPER EXECUTADO' in c) or ('HEDGE EXECUTADO' in c)
    if had_trade:
        continue
    
    header = c.split('\n')[0].strip()
    time_m = re.search(r'(\d{2}:\d{2}:\d{2})', header)
    tm = time_m.group(1) if time_m else '??'
    
    all_spots = re.findall(r'\[(\d+)s/300s\] Chainlink: \$([\d\.,]+) \(Delta: ([+\-\d\.]+)\)', c)
    if not all_spots:
        continue
    last_delta = float(all_spots[-1][2])
    winner = 'UP' if last_delta > 0 else 'DOWN'
    
    spot_135 = re.search(r'Spot Chainlink aos 135s: \$([\d\.,]+) \| Drift Real \(Delta\): \$([+\-\d\.]+)', c)
    d135 = float(spot_135.group(2)) if spot_135 else 0.0
    dir135 = 'UP' if d135 > 0 else 'DOWN'
    won135 = (dir135 == winner)
    
    p_m = re.search(r'FILTRO DE PRECO\]: Preco \$([\d\.]+) > \$0.65', c)
    if p_m:
        p = float(p_m.group(1))
        if 0.66 <= p <= 0.75:
            skipped_p66_75.append((tm, d135, p, winner, won135, last_delta))
            
    if 'FILTRO CVD' in c:
        cvd_rejections.append((tm, d135, winner, won135, last_delta))
        
    if 'Binance Drift' in c and 'aguardando' in c:
        drift_rejections.append((tm, d135, winner, won135, last_delta))
        
    if 'FILTRO DE RUIDO DEADBAND' in c:
        deadband_skips.append((tm, d135, winner, won135, last_delta))

print('1. Precos moderados ($0.66 a $0.75) no filtro primario:')
for x in skipped_p66_75:
    print(f'   [{x[0]}] 135s Delta: {x[1]:+0.2f}, Preco: ${x[2]:.2f}, Vencedor: {x[3]}, Acertaria? {x[4]}, Final Delta: {x[5]:+0.2f}')

print('\n2. Rejeicoes por CVD (Conflito Institucional):')
for x in cvd_rejections:
    print(f'   [{x[0]}] 135s Delta: {x[1]:+0.2f}, Vencedor: {x[2]}, Teria vencido? {x[3]}, Final Delta: {x[4]:+0.2f}')

print('\n3. Rejeicoes por Binance Drift:')
for x in drift_rejections:
    print(f'   [{x[0]}] 135s Delta: {x[1]:+0.2f}, Vencedor: {x[2]}, Teria vencido? {x[3]}, Final Delta: {x[4]:+0.2f}')

print('\n4. Zona Morta Deadband ($10 a $15):')
for x in deadband_skips:
    if abs(x[1]) >= 10.0:
        print(f'   [{x[0]}] 135s Delta: {x[1]:+0.2f}, Vencedor: {x[2]}, Acertaria? {x[3]}, Final Delta: {x[4]:+0.2f}')
