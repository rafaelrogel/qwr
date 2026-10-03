# -*- coding: utf-8 -*-
"""
Auditoria Forense e Quantitativa com a IA Jev (TypeSafe SystemOne)
Validação de Horizontes Operacionais de Gás Natural na Kalshi:
- Intradiário 15m (KXNATGAS15M)
- Diário 17h EDT (KXNATGASD)
- Semanal Sexta 17h EDT (KXNATGASW)
- Semanal de Quinta (Relatório EIA Storage / Desk 4)
- Mensal (KXNATGASMON)
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
====================================================================================================
DOSSIÊ QUANTITATIVO JEV: VALIDAÇÃO DE HORIZONTES TEMPORAIS EM NATURAL GAS (CFTC KALSHI)
Data: 2026-09-26
Ambiente: Kalshi Prediction Markets (CFTC Regulated Exchange)
Ativo Subjacente: Henry Hub Natural Gas Cash / NYMEX CME Continuous Futures

1. DADOS E INFRAESTRUTURA QUE POSSUÍMOS ATUALMENTE:
   a) Feed Spot em Tempo Real: Pyth Network Henry Hub price service feed (latência submétrica, alta resolução).
   b) Engine Meteorológica Ponderada 7-Day (Open-Meteo GFS + NOAA NWS):
      - 5 macrorregiões dos EUA com pesos reais de consumo/produção:
        * Midwest (Chicago, IL): 30% do consumo residencial de aquecimento
        * East (New York, NY): 32% do consumo de aquecimento
        * South Central (Houston, TX): 22% (Power burn elétrico e polo físico Henry Hub)
        * Pacific (Los Angeles, CA): 10%
        * Mountain (Denver, CO): 6%
      - Cálculo diário de HDD (Heating Degree Days) e CDD (Cooling Degree Days).
      - Regressão empírica de injeção/saque de estoques EIA:
        * Desvio de 1 HDD = ~0.55 Bcf de variação na queima de gás
        * Desvio de 1 CDD = ~0.40 Bcf de variação na geração elétrica
        * Consenso ingênuo de mercado vs previsão do modelo climatológico.
   c) Modelo Intradiário de Microestrutura (Desk 5):
      - Deadband dinâmico de 10 bps ($0.0030/MMBtu).
      - Rastreamento de momentum da vela anterior de 15m.
      - Take-profit antecipado dinâmico (limite $0.88-$0.92).
      - Histórico comprovado no Paper: 16 trades, 15 vitórias, 1 derrota (93.8% Win Rate, +$7.58 USD de lucro).
   d) Perfil de Capital:
      - Gestão de banca quantitativa (capital entre $10 USD e $1,000 USD).
      - Custo de oportunidade de capital: preferência por rotação rápida e turnover composto.

2. HIPÓTESE APRESENTADA PELO ANALISTA HUMANO:
   - Hipótese 1 (Semanal de Quinta / EIA Storage): O modelo meteorológico NOAA/GFS possui o maior "alpha" fundamentalista, pois na quarta-feira à tarde (14h-18h ET) os dados dos 7 dias anteriores já ocorreram, eliminando o erro de previsão antes da divulgação do relatório oficial na quinta às 10:30 AM EDT.
   - Hipótese 2 (Diários KXNATGASD): Viabilidade imediata se operado nas horas finais do dia (13:00 - 15:00 EDT) explorando a distância do spot em relação aos strikes além da volatilidade esperada (lógica Yield Harvester / Theta decay com 90-95% probabilidade).
   - Hipótese 3 (Semanais de Preço KXNATGASW): Não operar de segunda a quarta devido a frentes meteorológicas incertas; operar apenas na quinta-feira pós-EIA para colher a tendência confirmada até sexta-feira às 17h EDT.
   - Hipótese 4 (Mensais KXNATGASMON): Não recomendado. 30 dias de capital travado, baixa liquidez no book da Kalshi e forte dependência de variáveis macroeconômicas (exportação de GNL, geopolítica europeia, paradas industriais) fora do escopo meteorológico.
====================================================================================================
"""

questions = {
    "validation_eia_thursday": Choice(
        instructions="JEV, você valida a Hipótese 1: operar o contrato semanal de estoques da EIA na janela de quarta-feira à tarde (14h-18h ET) com a Engine NOAA/GFS de graus-dia (HDD/CDD) ponderados?",
        criteria={
            "STRONGLY_VALIDATED_HIGH_ALPHA": "Validado Fortemente: Alta assimetria estatística. Na quarta à tarde, o clima dos 7 dias do ciclo já está consolidado e o varejo na Kalshi ainda precifica pelo consenso ingênuo da mídia.",
            "MODERATE_EDGE": "Edge Moderado: Útil, mas os market makers institucionais ajustam seus spreads antes do fechamento de quarta.",
            "INVALID_NO_EDGE": "Inválido: Sem vantagem estatística mensurável contra a precificação da Kalshi."
        }
    ),
    "validation_daily_kxnatgasd": Choice(
        instructions="JEV, você valida a Hipótese 2: operar os contratos diários KXNATGASD (vencimento às 17h EDT) na janela da tarde (13h-15h EDT) via modelo de distância de volatilidade (Yield Harvester)?",
        criteria={
            "VALIDATED_EXCELLENT_TURNOVER": "Validado com Louvor: Excelente turnover de capital diário, explorando o decaimento do tempo (theta) em strikes protegidos por desvios-padrão de volatilidade intradiária.",
            "VIABLE_WITH_STRICT_STOP_LOSS": "Viável apenas com Stop-Loss Estrito: Gás Natural tem caudas pesadas (kurtose alta), exigindo stop-loss rígido caso ocorra choque repentino na CME à tarde.",
            "REJECTED_TOO_VOLATILE": "Rejeitado: Volatilidade da tarde é muito perigosa para venda de opções binárias."
        }
    ),
    "validation_weekly_kxnatgasw": Choice(
        instructions="JEV, você valida a Hipótese 3: nos contratos semanais de preço (KXNATGASW), evitar entrar no início da semana e focar na entrada de quinta-feira pós-relatório EIA até sexta às 17h EDT?",
        criteria={
            "VALIDATED_POST_EIA_ONLY": "Validado: Entrar pós-choque do EIA elimina o risco de evento binário descontrolado e permite surfar a tendência consolidada com decaimento acelerado de sexta-feira.",
            "ENTER_EARLY_WEEK": "Incorreto: É melhor entrar na segunda-feira para capturar o prêmio máximo da semana inteira.",
            "AVOID_WEEKLY_ENTIRELY": "Incorreto: Contratos semanais de preço não devem ser operados sob nenhuma condição."
        }
    ),
    "validation_monthly_kxnatgasmon": Choice(
        instructions="JEV, você valida a Hipótese 4: descartar os contratos mensais (KXNATGASMON) devido ao travamento de capital de 30 dias, menor liquidez na Kalshi e fatores macro fora do escopo?",
        criteria={
            "VALIDATED_DISCARD_MONTHLY": "Validado: Descartar mensais. O custo de oportunidade para bancas quantitativas de crescimento é proibitivo e a dependência de fatores macro/geopolíticos reduz o edge algorítmico.",
            "RECOMMEND_MONTHLY": "Incorreto: Mensais deveriam ser o foco principal pela previsibilidade macroeconômica sazonal.",
            "INDIFFERENT": "Indiferente entre horizontes mensais e diários."
        }
    ),
    "comparative_ranking_order": Choice(
        instructions="Qual é o ranking quantitativo definitivo de atratividade e relação Risco x Retorno para a nossa banca nos contratos de Natural Gas da Kalshi?",
        criteria={
            "RANKING_15M_AND_EIA_FIRST_THEN_DAILY": "1º Desk 5 (15m KXNATGAS15M) + Desk 4 (Semanal EIA Quarta/Quinta) | 2º Diário da Tarde (KXNATGASD) | 3º Semanal pós-EIA (KXNATGASW) | Último: Mensal (KXNATGASMON).",
            "RANKING_MONTHLY_FIRST": "1º Mensais | 2º Semanais | 3º Diários | 4º 15 minutos.",
            "RANKING_ALL_EQUAL": "Todos os horizontes possuem exatamente o mesmo perfil de risco e retorno."
        }
    ),
    "overall_thesis_score": Score(
        instructions="Provide an overall quant score from 1.0 to 5.0 for the analyst's thesis and diagnosis on Natural Gas horizons (15m, Daily, Weekly, Thursday EIA, Monthly).",
        criteria=[
            "1.0 - Misaligned thesis with poor risk understanding",
            "2.0 - Superficial understanding with high basis risk",
            "3.0 - Adequate baseline but misses microstructure realities",
            "4.0 - Solid institutional alignment: correctly prioritizes weather arbitrage and intraday drift while avoiding monthly lockups",
            "5.0 - Flawless quantitative discrimination: perfect capital turnover prioritization, rigorous weather degree-day edge, and disciplined risk allocation"
        ]
    )
}

print("=" * 95)
print("  🤖 INICIANDO AUDITORIA QUANTITATIVA FORENSE COM A IA JEV (TYPESAFE SYSTEMONE)")
print("  Tópico: Validação e Comparação dos Horizontes de Gás Natural na Kalshi (15m, Diário, Semanal, Mensal)")
print("=" * 95)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[+] Resposta recebida da IA JEV em {elapsed:.2f}s!\n")

results_summary = {}

for q_name, ans in resp.answers.items():
    if hasattr(ans, "choice"):
        print(f"📌 {q_name}:")
        print(f"   Decisão JEV: {ans.choice} (Confiança: {ans.confidence:.1%})")
        print("   Probabilidades:")
        for opt, p in ans.probabilities.items():
            print(f"     - {opt}: {p:.1%}")
        print()
        results_summary[q_name] = {
            "verdict": ans.choice,
            "confidence": ans.confidence,
            "probabilities": ans.probabilities
        }
    elif hasattr(ans, "value"):
        print(f"⭐ {q_name}: {ans.value:.2f} / 5.00")
        results_summary[q_name] = {
            "score": ans.value
        }

with open("jev_natgas_horizons_audit.json", "w", encoding="utf-8") as f:
    json.dump(results_summary, f, indent=2)

print("[✓] Auditoria da IA Jev concluída e salva em jev_natgas_horizons_audit.json!")
