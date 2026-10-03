# -*- coding: utf-8 -*-
"""
CONSULTA DIRETA AO JEV (TypeSafe SystemOne):
Pergunta do Usuário: Vale a pena apostarmos em todas as 14 cidades ou apenas em 2 no Desk 12 (Weather METAR Arbitrage)?
"""

import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from typesafe_sdk import TypeSafeClient, Choice, Score

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
CONSULTA INSTITUCIONAL: VALE A PENA APOSTAR EM TODAS AS 14 CIDADES OU EM APENAS 2 NO DESK 12?

CONTEXTO OPERACIONAL (DESK 12 - WEATHER & METAR AIRPORT ARBITRAGE):
1. Tese Quantitativa Fundamental:
   - O Desk 12 opera por ARBITRAGEM FÍSICA DETERMINÍSTICA, explorando a latência entre as leituras meteorológicas oficiais dos sensores ASOS da NOAA (National Oceanic and Atmospheric Administration) em aeroportos e os livros de ofertas da Kalshi.
   - Uma vez que a estação física do aeroporto registra um pico diário (ex: Austin KAUS atingiu 97.0°F ou Phoenix KPHX atingiu 105.0°F), contratos com regra "Máxima < 95°F" tornam-se determinística e irreversivelmente perdedores (resolução oficial 100% NO).
   - Risco direcional / meteorológico: ZERO após o fato físico ser consumado e registrado pelo sensor oficial.

2. A Pergunta do Usuário:
   "Se a liquidação física é determinística (quase certa), vale a pena apostarmos em todas as cidades em que estamos monitorando (14 aeroportos), e não apenas em 2 no Paper Mode?"

3. Comparativo de Escala:
   A) Apenas 2 Cidades (Austin KAUS e Miami KMIA):
      - Foco em alta amplitude térmica diurna (Austin) e contratos horários de alta frequência (Miami).
      - Menos mercados inspecionados (~24 mercados/dia), janelas de oportunidade mais restritas no tempo.
   B) Todas as 14 Cidades Monitoradas:
      - 14 Grandes Hubs: Austin (KAUS), Miami (KMIA), Chicago (KORD), Newark/NYC (KEWR), Los Angeles (KLAX), Dallas (KDFW), Atlanta (KATL), Boston (KBOS), Phoenix (KPHX), Houston (KIAH), Denver (KDEN), Las Vegas (KLAS), Seattle (KSEA), San Francisco (KSFO).
      - Cobertura de 4 fusos horários dos EUA (EDT, CDT, MDT, PDT): os picos de temperatura diurna acontecem de forma escalonada (19h UTC na costa Leste, 20h UTC no Centro, 21h UTC nas Montanhas e 22h-00h UTC no Pacífico).
      - Superfície de oportunidades multiplicada por 7x (~200 mercados avaliados simultaneamente).
      - Modo Operacional: PAPER (Simulação com APIs Reais, Fail-Closed, stake de $1.00 por oportunidade, limite de 20 slots = $20.00 de teto).
      - Latência medida na API NOAA: Todas as 14 estações retornam em 200 milissegundos num único GET HTTP.

4. Critérios de Entrada:
   - Entrada apenas se o fato físico estiver 100% consumado (leitura ASOS violou o strike do contrato).
   - Teto de preço de entrada: MAX_ENTRY_PRICE = 0.97 (captura penny clipping com lucro líquido entre +3% e +40% garantidos após taxas CFTC).
"""

questions = {
    "all_cities_vs_two": Choice(
        instructions="Sob a ótica de convexidade, diversificação e ausência de risco direcional na arbitragem física, vale a pena expandir para todas as 14 cidades ou manter restrito a apenas 2?",
        criteria={
            "approved_all_14_cities": "Aprovar todas as 14 cidades: Como a liquidação é determinística (fato consumado registrado por sensor oficial ASOS), monitorar 14 cidades em 4 fusos horários multiplica a frequência de oportunidades sem aumentar o risco direcional. No Paper Mode, isso gera uma amostra estatística 7x mais rica e acelera a validação.",
            "restrict_to_top_desert_hubs": "Restringir apenas aos 4-6 maiores hubs de alta amplitude térmica: Focar em cidades com oscilações diurnas extremas (Austin, Phoenix, Dallas, Las Vegas, Denver) e descartar cidades litorâneas de clima temperado (San Francisco, Seattle).",
            "restrict_to_two_cities": "Manter restrito a apenas 2 cidades: Manter estritamente Austin e Miami para simplificar a observabilidade inicial.",
            "reject_weather_trading": "Rejeitar negociação em clima: Risco excessivo de disputa de oráculo ou regras contratuais."
        }
    ),
    "risk_and_execution_edge": Choice(
        instructions="Qual é a principal recomendação técnica para garantir que a expansão para 14 cidades opere com máxima robustez institucional?",
        criteria={
            "strict_station_ticker_mapping": "Mapeamento ICAO estrito e confirmação de fuso: Assegurar que cada contrato da Kalshi aponte exatamente para a estação ICAO correta e que o código de data (ex: 26SEP29) coincida com o dia civil local da estação.",
            "penny_clipping_cap": "Calibrar teto de preço para 97¢: Permitir entradas em cotas garantidas até 97¢ para capturar ordens esquecidas no book com lucro líquido positivo após taxas CFTC.",
            "both_strict_mapping_and_penny_cap": "Aplicar ambos: Mapeamento rigoroso ICAO/fuso civil local + teto de 97¢ para penny clipping com stake fixo ($1.00) no Paper Mode.",
            "reduce_scan_frequency": "Reduzir frequência de varredura para economizar chamadas de API."
        }
    ),
    "paper_to_live_readiness": Choice(
        instructions="Como o conselho avalia o Desk 12 operando com 20 posições ativas simultâneas ($20 de teto) em modo PAPER?",
        criteria={
            "optimal_paper_setup": "Setup ideal: 20 slots de $1.00 em Paper Mode permite que o robô explore amplamente as 14 cidades, colete dezenas de liquidações automáticas e comprove o win rate teórico de 100% antes de arriscar um único centavo real.",
            "reduce_to_10_slots": "Reduzir para 10 slots: Manter teto de 10 posições para evitar dispersão.",
            "upgrade_to_live_immediately": "Migrar para Live imediatamente sem testar em Paper."
        }
    )
}

print("=" * 80)
print("🤖 CONSULTANDO JEV: VALE A PENA EXPANDIR O DESK 12 PARA TODAS AS 14 CIDADES?")
print("=" * 80)

t0 = time.time()
try:
    resp = client.system_one(state=dossier, questions=questions)
    elapsed = time.time() - t0
    print(f"\n[OK] Resposta recebida do JEV em {elapsed:.2f} segundos!")
    print("=" * 80)

    for qname, ans in resp.answers.items():
        print(f"\n📌 PERGUNTA: {qname.upper()}")
        print(f"   ESCOLHA DO JEV: {ans.choice.upper()}")
        print(f"   CONFIANÇA: {ans.confidence * 100:.1f}%")
        print(f"   PROBABILIDADES:")
        for opt, prob in ans.probabilities.items():
            print(f"     • {opt}: {prob * 100:.1f}%")

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_weather_all_cities_verdict.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.time(),
            "elapsed_sec": round(elapsed, 2),
            "results": {k: {"choice": v.choice, "confidence": round(v.confidence, 3), "probabilities": {p_k: round(p_v, 3) for p_k, p_v in v.probabilities.items()}} for k, v in resp.answers.items()}
        }, f, indent=2, ensure_ascii=False)
    print(f"\n[SALVO] Veredito do JEV salvo em: {output_path}")

except Exception as e:
    print(f"[ERRO] {e}")
    sys.exit(1)
