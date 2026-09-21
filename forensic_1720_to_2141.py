import sys
import json
import urllib.request
import re
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

# 1. Carregar todas as velas de 1m da Binance cobrindo das 16:15 UTC às 20:45 UTC
# (que corresponde a 17:15 até 21:45 no fuso UTC+1)
now_ms = int(datetime.now().timestamp() * 1000)
# 5 horas atrás
start_ms = now_ms - (5 * 3600 * 1000)

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

# 2. Ler todos os logs das tarefas recentes
log_files = [
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3790.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3984.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4110.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4169.log"
]

cycle_blocks = {}
for lf in log_files:
    try:
        with open(lf, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except:
        continue
    blocks = content.split("[CICLO ATIVO] Janela:")
    for b in blocks[1:]:
        m = re.match(r"\s*(\d{2}:\d{2}:\d{2})", b.splitlines()[0])
        if m:
            cycle_blocks[m.group(1)] = b

# Janelas das 17:20 até 21:40 (a cada 5 minutos)
start_hour = 17
start_min = 20
end_hour = 21
end_min = 40

windows_to_check = []
h, m = start_hour, start_min
while (h < end_hour) or (h == end_hour and m <= end_min):
    windows_to_check.append(f"{h:02d}:{m:02d}:00")
    m += 5
    if m >= 60:
        m = 0
        h += 1

print(f"Total de janelas a analisar: {len(windows_to_check)}")

analysis = []

for tw in windows_to_check:
    b = cycle_blocks.get(tw, "")
    has_log = bool(b)
    
    # Extrair informacoes do log se disponivel
    m_strike = re.search(r"Strike Oraculo Chainlink \(K\):\s*\$([\d\.,]+)", b)
    log_strike = float(m_strike.group(1).replace(",", "")) if m_strike else None
    
    m_delta135 = re.search(r"Drift Real \(Delta\):\s*\$([-\+\d\.,]+)", b)
    log_delta135 = float(m_delta135.group(1).replace(",", "")) if m_delta135 else None

    # Tentar encontrar a vela correspondente na Binance (pelo horario UTC = tw - 1h)
    # Por exemplo: 17:20 local = 16:20 UTC
    th, tm, _ = map(int, tw.split(":"))
    utc_h = th - 1
    # converter para timestamp de hoje
    # achar nas candles
    matched_ts = None
    for ts in candles.keys():
        if ts % 300 == 0:
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            if dt_utc.hour == utc_h and dt_utc.minute == tm:
                matched_ts = ts
                break

    if not matched_ts:
        continue

    c0 = candles.get(matched_ts)
    c2 = candles.get(matched_ts + 120)
    c4 = candles.get(matched_ts + 240)
    
    strike = log_strike if log_strike else c0["open"]
    
    spot_135 = (c2["open"] + c2["close"]) / 2.0 if c2 else c0["close"]
    delta_135 = log_delta135 if log_delta135 is not None else (spot_135 - strike)
    
    # Preco estimado ou preco real do log aos 135s
    m_fp = re.search(r"Preco \$([0-9\.]+) (>|<) \$([0-9\.]+)", b)
    log_price = float(m_fp.group(1)) if m_fp else None

    # Aos 255s
    spot_255 = c4["open"] if c4 else spot_135
    delta_255 = spot_255 - strike
    
    # Fechamento real
    final_close = c4["close"] if c4 else spot_255
    winner = "UP" if final_close >= strike else "DOWN"
    final_move = final_close - strike

    # O que o bot fez
    bot_action = "Nenhuma acao"
    if "VITORIA (SCOUR SWEEPER)" in b or "ORDEM SWEEPER EXECUTADA" in b:
        bot_action = "SWEEPER EXECUTADO (VITORIA +$0.16)"
    elif "ENTRADA PRIMARIA EXECUTADA" in b or "ORDEM AO VIVO ENVIADA" in b:
        bot_action = "TRADE PRIMARIO EXECUTADO"
    elif "FILTRO DE RUIDO DEADBAND" in b:
        bot_action = f"Deadband (|Delta| < $15): {delta_135:+.1f}"
    elif "FILTRO DE PRECO" in b:
        bot_action = f"Preço Fora: ${log_price:.2f}" if log_price else "Preço Fora de [0.35, 0.65]"
    elif "FILTRO DE IMBALANCE CLOB" in b:
        bot_action = "Muralha de Book (Imbalance)"
    elif not has_log:
        bot_action = "Sem log (transicao/reinicializacao)"

    # Avaliacao Honesta:
    # 1. Se tivessemos entrado aos 135s ignorando o filtro de preco:
    entry_135_side = "UP" if delta_135 > 0 else "DOWN"
    entry_135_res = "N/A"
    if abs(delta_135) >= 15.0:
        if entry_135_side == winner:
            entry_135_res = f"ACERTARIA (+{winner})"
        else:
            entry_135_res = f"ERRARIA (-{entry_135_side} virou {winner}) [ARMADILHA!]"
    else:
        entry_135_res = "Deadband (Ruído puro)"

    # 2. Se tivessemos entrado com Sweeper aos 255s:
    sweeper_eligible = abs(delta_255) >= 25.0
    sweeper_side = "UP" if delta_255 > 0 else "DOWN"
    sweeper_res = "N/A"
    if sweeper_eligible:
        if sweeper_side == winner:
            sweeper_res = f"Sweeper Ganharia (+{sweeper_side})"
        else:
            sweeper_res = f"Sweeper Perderia (-{sweeper_side} virou {winner})"
    else:
        sweeper_res = f"Delta < $25 ({delta_255:+.1f})"

    analysis.append({
        "window": tw,
        "strike": strike,
        "delta_135": delta_135,
        "log_price": log_price,
        "delta_255": delta_255,
        "final_move": final_move,
        "winner": winner,
        "bot_action": bot_action,
        "entry_135_res": entry_135_res,
        "sweeper_res": sweeper_res,
        "log_content": b
    })

# Imprimir relatorio estruturado
print("\n" + "=" * 140)
print(f"{'JANELA':<8} | {'STRIKE':<9} | {'D_135':<8} | {'D_255':<8} | {'F_MOVE':<8} | {'WIN':<4} | {'ACAO DO BOT':<30} | {'SE ENTRASSE AOS 135s':<26} | {'SWEEPER 255s'}")
print("=" * 140)

wins_135 = 0
losses_135 = 0
traps_avoided = 0
missed_wins_135 = 0
missed_sweeper_wins = 0

for a in analysis:
    print(f"{a['window']:<8} | {a['strike']:9.2f} | {a['delta_135']:+8.1f} | {a['delta_255']:+8.1f} | {a['final_move']:+8.1f} | {a['winner']:<4} | {a['bot_action']:<30} | {a['entry_135_res']:<26} | {a['sweeper_res']}")
    
    if "ACERTARIA" in a["entry_135_res"]:
        wins_135 += 1
        if "Preço Fora" in a["bot_action"]:
            missed_wins_135 += 1
    elif "ERRARIA" in a["entry_135_res"]:
        losses_135 += 1
        traps_avoided += 1
    
    if "Sweeper Ganharia" in a["sweeper_res"] and "SWEEPER EXECUTADO" not in a["bot_action"]:
        missed_sweeper_wins += 1

print("=" * 140)
print(f"\nRESUMO FORENSE QUANTITATIVO (17:20 às 21:40 - {len(analysis)} ciclos):")
print(f"  * Total de Ciclos Analisados: {len(analysis)}")
print(f"  * Trades Reais Executados: 1 (17:30 - Sweeper Ganhou +$0.16)")
print(f"  * Cenário aos 135s (Se forçasse todas as entradas com |Delta| >= $15 ignorando Preço):")
print(f"     - Acertos Possíveis: {wins_135}")
print(f"     - Derrotas por Reversão (Armadilhas Evitadas): {traps_avoided}")
print(f"     - Ganhos 'Deixados na Mesa' por Cota Cara (> $0.65): {missed_wins_135}")
print(f"  * Cenário no Sweeper aos 255s:")
print(f"     - Oportunidades teóricas onde Delta >= $25 e confirmou vitória: {missed_sweeper_wins}")
