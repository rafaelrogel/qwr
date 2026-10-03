# -*- coding: utf-8 -*-
"""
CONSULTA INSTITUCIONAL AO JEV (TypeSafe SystemOne):
Auditoria Completa do Perfil e Repositórios GitHub de Ziad Francis (@ZiadFrancis)
e Debate Intelectual sobre Oportunidades de Aplicação no Ecossistema AGY (Polymarket & Kalshi).
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

from typesafe_sdk import TypeSafeClient, Choice

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
====================================================================================================
DOSSIÊ QUANTITATIVO: AUDITORIA DO PERFIL GITHUB DE ZIAD FRANCIS (@ZiadFrancis)
Data: 2026-09-28 | Contexto: Análise de 19 Repositórios e Debate Intelectual com JEV SystemOne
Alvo: Identificar insights, bibliotecas, algoritmos e técnicas aplicáveis aos nossos Desks
(Polymarket BTC/SOL/ETH 5m e Kalshi BTC/NatGas/Gold/SPX 15m).
====================================================================================================

1. PANORAMA GERAL DO AUTOR (Ziad Francis / CodeTradingCafe):
Ziad Francis é um desenvolvedor quantitativo com foco em:
- Reinforcement Learning avançado aplicado a trading com guardrails anti-leakage (PPO, walk-forward).
- Agentes de Trading baseados em LLMs (ReAct loop com Claude / GPT) com blindagem anti-lookahead.
- Algoritmos Genéticos / Programação Simbólica (DEAP + vectorbt).
- Conceitos de Microestrutura e Smart Money (Liquidity Sweeps, detecção de pivôs vetorizados).
- Redes Neurais para Séries Temporais (PyTorch Transformers, XGBoost Indicator Classifiers).
- Processamento de Linguagem Natural Financeiro (FinBERT tone classifier para notícias).

2. OS PRINCIPAIS REPOSITÓRIOS AUDITADOS E SEUS COMPONENTES TÉCNICOS:

A) Reinforcement_Trading_Part_2 (Pipelined PPO em XAUUSD 23 Anos):
   - Pipeline de M1 para M15/H1 retendo ticks de M1 para simulação intrabar de Bracket Orders (TP/SL).
   - Espaço de ação MultiDiscrete([direction, SL bucket, TP/R bucket]).
   - Validação Walk-Forward rigorosa com conjunto de teste permanentemente selado.
   - Script específico de 'leakage_checks.py' para certificar que nenhum dado futuro vaze nas features.
   - Causalidade e estacionaridade: features normalizadas por ATR e preços, eliminando não-estacionariedade.

B) GPT_5.6_Sol_Trading_Agent (LLM Agent em BTC/Gold com Anti-Lookahead Guards):
   - ReAct Tool Loop: get_price -> get_indicators -> check_position -> place_order.
   - 5 Guardas Anti-Lookahead estritas:
     [GUARD 1] O agente só vê df.iloc[:i+1] (barras já fechadas).
     [GUARD 2] Barras diárias resampladas da fatia 1H visível, descartando barra em formação.
     [GUARD 3] Fill no open da barra seguinte (+ slippage e fee), nunca no close observado.
     [GUARD 4] Indicadores e ATR recalculados dinamicamente apenas na fatia visível.
     [GUARD 5] Anonimização de escala e alertas de cutoff de pré-treino para evitar memorização histórica.

C) BreakOutLiquiditySweep (Detecção Vetorizada de Pivôs e Varredura de Liquidez):
   - Função 'mark_pivots' vetorizada com extrema rolante centrada.
   - Algoritmo 'detect_structure' para rastrear Pivot High (PH) e Pivot Low (PL).
   - Identifica quando um rompimento é um sweep (captura de liquidez passageira) versus rompimento real com confirmação de EMA.

D) NewsSentimentScanner (NLP Financeiro com FinBERT):
   - Integração com Google News RSS + BeautifulSoup para raspagem em tempo real.
   - Pipeline de 'yiyanghkust/finbert-tone' (FinBERT) gerando scores ponderados (Positive, Negative, Neutral).

E) Genetics_Trading_Part_1 (Programação Genética com DEAP e Vectorbt):
   - Evolução de árvores de regras sintáticas de trading através de crossover e mutação.
   - Avaliação vetorizada ultrarrápida via Vectorbt.
   - Separação estrita em Train, Validation e Test out-of-sample.

F) Transformers_Trading_01 & MachineLearningIndicator_Classifier:
   - Transformer Encoder (2 camadas, 8 cabeças, pos-embedding) para regressão de preços em Forex.
   - XGBoost Classifier com TimeSeriesSplit para consenso entre múltiplos indicadores técnicos.

====================================================================================================
3. PONTOS DE CONEXÃO COM O NOSSO ECOSSISTEMA AGY (POLYMARKET & KALSHI):
- A nossa derrota recente no Desk 1 (17:02 UTC) foi exatamente uma VIOLINADA DE LIQUIDEZ (Liquidity Sweep)
  que o algoritmo de Ziad em 'BreakOutLiquiditySweep' formaliza como falso rompimento.
- Os 5 Guardas de Ziad em 'GPT_5.6_Sol_Trading_Agent' coincidem com a nossa arquitetura de oráculos redundantes.
- O pipeline de bracket intrabar em M1/M15 de 'Reinforcement_Trading_Part_2' conversa diretamente com o Desk 9 (Gold Kalshi) e Desk 11 (SPX).
====================================================================================================
"""

questions = {
    "ziad_engineering_quality_assessment": Choice(
        instructions="JEV, avalie o nível técnico e o rigor metodológico dos repositórios de Ziad Francis. Como você classifica a engenharia quantitativa dele?",
        criteria={
            "TOP_TIER_RIGOROUS_ENGINEERING": "ENGENHARIA DE ELITE: Ziad demonstra um rigor quantitativo raro no ecossistema open-source. O uso de walk-forward com teste selado, verificação explícita de leakage (leakage_checks.py), causalidade estrita e 5 guardas anti-lookahead coloca o código dele no patamar dos fundos quantitativos sistemáticos sérios.",
            "INTERMEDIATE_EDUCATIONAL_CODE": "INTERMEDIÁRIO / EDUCATIVO: O código é bem estruturado para tutoriais e vídeos do YouTube, mas carece de gestão de latência L2 e execução em tempo real para produção HFT.",
            "SUPERFICIAL_REPACKAGED": "SUPERFICIAL: Apenas reempacotamento de bibliotecas comuns como vectorbt e stable-baselines sem profundidade matemática."
        }
    ),
    "most_valuable_component_for_our_desks": Choice(
        instructions="JEV, considerando os nossos 10 Desks na Polymarket e Kalshi (opções binárias de 5m e 15m), qual componente do Ziad possui o MAIOR valor de assimilação imediata?",
        criteria={
            "LIQUIDITY_SWEEP_PIVOT_FILTER": "DETECÇÃO DE LIQUIDITY SWEEPS (BreakOutLiquiditySweep): Altíssimo valor imediato. O algoritmo de pivôs e detecção de falsos rompimentos pode ser convertido em um 'Anti-Fakeout Gate' para as velas de 5m do Desk 1 (BTC) e Desk 2 (SOL), prevenindo violinadas exatamente como a que nos estopou hoje.",
            "FINBERT_NEWS_SENTIMENT_SCANNER": "SCANNER FINBERT (NewsSentimentScanner): Maior valor. Integrar análise de sentimento em tempo real de notícias de juros (Fed) e petróleo/gás no Desk 4 (NatGas EIA) e Desk 7 (Cross-Arb).",
            "REINFORCEMENT_BRACKET_PIPELINE": "PIPELINE RL PPO COM BRACKET INTRABAR (Reinforcement_Trading_Part_2): Maior valor para o treinamento de modelos preditivos de 15m em Ouro (Desk 9) e SPX (Desk 11).",
            "GENETIC_PROGRAMMING_VECTORBT": "PROGRAMAÇÃO GENÉTICA (Genetics_Trading_Part_1): Maior valor para descobrir combinações não-lineares de deadband e CVD."
        }
    ),
    "debate_verdict_on_ai_agents_vs_heuristics": Choice(
        instructions="JEV, reflita sobre o repositório 'GPT_5.6_Sol_Trading_Agent': agentes autônomos baseados em LLMs (ReAct) superam modelos estatísticos/Bayesianos determinísticos como os que usamos hoje, ou são lentos e arriscados para microestrutura de 5m?",
        criteria={
            "HYBRID_REGIME_LLM_NOT_EXECUTION": "MODELO HÍBRIDO (LLM apenas para Macro/Regime, Bayesiano para Execução): Agentes LLM são lentos demais (latência >1-3s) e não-determinísticos para execução direta em 5m na CLOB. No entanto, usar um agente LLM para classificar regimes macro diários/horários e calibrar os parâmetros dos nossos modelos Bayesianos determinísticos é a arquitetura ideal.",
            "LLM_DIRECT_EXECUTION_SUPERIOR": "LLMS DIRETOS SÃO SUPERIORES: Os LLMs possuem visão holística superior a modelos estatísticos e devem substituir as regras dos desks.",
            "LLMS_ARE_TOYS_AVOID_IN_PROD": "LLMS SÃO BRINQUEDOS EM TRADING: Devemos evitar completamente LLMs e focar 100% em microestrutura e tick data de baixa latência."
        }
    )
}

print("=" * 80)
print(" [JEV SYSTEMONE] CONSULTANDO JEV: AUDITORIA DO GITHUB DE ZIAD FRANCIS...")
print("=" * 80)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n>>> PARECER DO JEV RECEBIDO EM {elapsed:.2f}s <<<\n")

results = {}
for qname, ans in resp.answers.items():
    print(f"[{qname.upper()}]")
    print(f"Decisão: {ans.choice}")
    print(f"Confiança: {ans.confidence * 100:.1f}%")
    print("Probabilidades:")
    for opt, p in ans.probabilities.items():
        print(f"  * {opt}: {p:.1%}")
    print("-" * 60)
    results[qname] = {
        "choice": ans.choice,
        "confidence": ans.confidence,
        "probabilities": ans.probabilities
    }

output_payload = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "answers": results
}

output_file = "jev_ziad_francis_audit_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Veredito do JEV gravado em '{output_file}'.")
