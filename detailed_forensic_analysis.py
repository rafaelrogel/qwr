import glob
import re

log_files = [
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3790.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-3984.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4110.log",
    r"C:\Users\rafae\.gemini\antigravity\brain\c125241d-a48c-4ba7-aab4-bba800620ab2\.system_generated\tasks\task-4169.log"
]

cycles = {}

for lf in log_files:
    try:
        with open(lf, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except:
        continue

    blocks = content.split("[CICLO ATIVO] Janela:")
    for b in blocks[1:]:
        lines = b.splitlines()
        header = lines[0].strip()
        m = re.match(r"(\d{2}:\d{2}:\d{2})", header)
        if m:
            t = m.group(1)
            cycles[t] = b

target_windows = [
    "16:50:00", "16:55:00", "17:00:00", "17:05:00", "17:10:00", "17:15:00", "17:20:00",
    "17:25:00", "17:30:00", "17:35:00", "17:40:00", "17:45:00", "17:50:00", "17:55:00",
    "18:00:00", "18:05:00", "18:10:00", "18:15:00", "18:20:00", "18:25:00", "18:30:00",
    "18:35:00", "18:40:00", "18:45:00", "18:50:00", "18:55:00", "19:00:00", "19:05:00",
    "19:10:00", "19:15:00"
]

print(f"{'JANELA':<10} | {'STRIKE':<10} | {'DELTA 135s':<12} | {'DECISAO 135s':<35} | {'SWEEPER / ACAO':<30} | {'RESULTADO':<20}")
print("-" * 130)

for tw in target_windows:
    b = cycles.get(tw)
    if not b:
        print(f"{tw:<10} | SEM REGISTRO DE LOG")
        continue

    # Extrair Strike
    m_strike = re.search(r"Strike Oraculo Chainlink \(K\):\s*\$([\d\.,]+)", b)
    strike = m_strike.group(1) if m_strike else "N/A"

    # Extrair Delta 135s
    m_delta = re.search(r"Drift Real \(Delta\):\s*\$([-\+\d\.,]+)", b)
    delta_135 = m_delta.group(1) if m_delta else "N/A"

    # Filtro Deadband ou Preço ou Aposta Primária
    decisao = "N/A"
    if "FILTRO DE RUIDO DEADBAND" in b:
        m_db = re.search(r"Delta de \$([-\+\d\.,]+) esta dentro da zona morta", b)
        val = m_db.group(1) if m_db else delta_135
        decisao = f"Deadband (<$15): {val}"
    elif "FILTRO DE PRECO" in b:
        m_fp = re.search(r"Preco \$([0-9\.]+) (>|<) \$([0-9\.]+)", b)
        if m_fp:
            decisao = f"Preço Fora ({m_fp.group(1)} {m_fp.group(2)} {m_fp.group(3)})"
        else:
            decisao = "Filtro de Preço"
    elif "FILTRO DE DIVERGENCIA BINANCE" in b:
        decisao = "Divergência Binance"
    elif "FILTRO DE SPREAD EXCESSIVO" in b:
        decisao = "Spread Excessivo"
    elif "ENTRADA PRIMARIA EXECUTADA" in b or "ORDEM AO VIVO ENVIADA" in b:
        m_side = re.search(r"(APOSTA PRIMARIA|LADO):\s*(UP|DOWN)", b)
        side = m_side.group(2) if m_side else "TRADED"
        decisao = f"TRADE PRIMARIO: {side}"
    elif "Spot Chainlink aos 135s:" in b:
        decisao = "Monitorou 135s"

    # Sweeper
    sweeper_act = "Nenhum"
    if "BTC5MScour Sweeper" in b or "SCOUR SWEEPER" in b:
        if "ORDEM SWEEPER EXECUTADA" in b or "Sweeper disparado" in b or "VITORIA (SCOUR SWEEPER)" in b:
            m_sw = re.search(r"(UP|DOWN)", b)
            sweeper_act = f"Sweeper Executado"
        elif "Preco do Sweeper" in b:
            sweeper_act = "Sweeper fora de faixa"
        else:
            sweeper_act = "Sweeper Monitorado"

    # Resultado do ciclo
    res = "Sem trade"
    if "VITORIA" in b:
        res = "VITORIA"
    elif "DERROTA" in b:
        res = "DERROTA"
    elif "Nenhuma aposta realizada" in b:
        res = "Preservou Capital"

    print(f"{tw:<10} | {strike:<10} | {delta_135:<12} | {decisao:<35} | {sweeper_act:<30} | {res:<20}")
