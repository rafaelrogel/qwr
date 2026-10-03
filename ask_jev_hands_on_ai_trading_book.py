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

key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
client = TypeSafeClient(api_key=key)

dossier = """
================================================================================
DOSSIÊ QUANTITATIVO: AVALIAÇÃO DO LIVRO 'HANDS-ON AI TRADING WITH PYTHON, QUANTCONNECT, AND AWS' (2025)
AUTORES: Jiri Pik (RocketEdge, ex-Citi/Goldman/UBS), Dr. Ernest P. Chan (PredictNow.ai), Jared Broad (CEO QuantConnect),
Philip Sun (Adaptive Investment Solutions, ex-Fidelity/Wellington), Vivek Singh (Senior PM AWS Bedrock/SageMaker).
EDITORA: John Wiley & Sons, Inc. (2025)

CONTEXTO DO AGY TRADING SYSTEM:
- Operando 12 Desks em opções binárias (Polymarket 5m e Kalshi 15m), liquidação determinística em $0.00 ou $1.00.
- Execução de alta precisão em microestrutura L2 CLOB: Order Book Imbalance (OBI), Binance CVD & Microprice drift,
  Dynamic Deadbands com regime diurno + ATR adaptativo non-blocking, SirMartingale Take-Profit, Bonereaper Hedge e Fractional Kelly.
- Banca atual: $29.90 USD (+42.38% líquido na Polymarket) e Kalshi Shard 2 intacto ($9.05 USD livres + $5.87 em contratos).

CONTEÚDO E CONTRIBUIÇÕES DO LIVRO (2025):
1. Microestrutura L2 e Custos de Transação (Capítulos 1 e 2):
   - Detalhamento de walk-the-book, slippage por impacto temporário vs. permanente, spreads bid-ask no NBBO.
   - Modelagem de ordens com quote bars e trade bars na engine LEAN do QuantConnect.
2. Preparação de Dados e Engenharia de Features (Capítulo 4):
   - Tratamento de outliers por z-score e IQR; diferenciação fracionária (López de Prado) para preservar memória sem perder estacionariedade.
   - Cointegração Engle-Granger e expoente de Hurst para mean-reversion.
3. Modelagem de Machine Learning e 19 Exemplos Práticos (Capítulos 5 e 6):
   - Exemplo 1: Trend Scanning de López de Prado com t-value de regressão linear para filtrar ruído de tendência.
   - Exemplo 8: Comparação empírica de 3 modelos de Stop-Loss (Fixo vs. LASSO dinâmico vs. Hedge com Opção Put), provando que hedges superam stop-losses fixos.
   - Exemplo 9: Seleção de pares com PCA + OPTICS Clustering + Hurst + Meia-vida OU.
   - Exemplo 12: Otimização de Custos de Execução com DecisionTreeRegressor (adiar ordens quando o custo previsto por dólar for superior à média móvel, economizando milhares de dólares em spread/slippage).
   - Exemplo 18 & 19: Modelos de Fundação para Séries Temporais (Amazon Chronos) e NLP Financeiro (FinBERT).
4. Hedging com Reinforcement Learning em 2 Estágios (Capítulo 7 - Philip Sun):
   - Estágio 1: Pré-treinamento com dados simulados de Black-Scholes para imitar o delta.
   - Estágio 2: Refinamento com dados reais de mercado usando função de penalidade de PnL (ReLU na perda de riqueza).
5. Corrective AI e Otimização Condicional de Portfólio (CPO) (Capítulo 8 - Ernie Chan):
   - Corrective AI (Meta-labeling): Não prever o mercado, mas prever a probabilidade de lucro (PoP) da estratégia primária.
   - CPO: Otimizar alocação de capital e parâmetros condicionados a regimes de mercado usando gradient-boosted trees.
6. LLMs e Generative AI (Capítulo 9 - Vivek Singh):
   - RAG para análise de relatórios fundamentalistas via AWS Kendra e SageMaker Canvas.
================================================================================
"""

questions = {
    "book_scientific_quality_and_relevance": Choice(
        instructions="Como o JEV avalia o rigor metodológico, atualidade e relevância técnica deste livro de 2025 (Pik, Chan, Broad, Sun, Singh) em relação à prática moderna de trading quantitativo algorítmico?",
        criteria={
            "cutting_edge_institutional_handbook": "Manual Institucional de Ponta (2025): Uma das obras mais completas e contemporâneas do setor, unindo os fundadores do QuantConnect e PredictNow.ai com engenheiros da AWS. Aborda microestrutura real, execução no CLOB, meta-labeling de López de Prado e modelos práticos com código funcional.",
            "theoretical_academic_compilation": "Compilação Teórica Acadêmica: Bom apanhado de bibliotecas, mas dependente demais do ecossistema QuantConnect/AWS.",
            "unfocused_collection": "Coletânea Desfocada: Mistura muitos tópicos sem aprofundar na microestrutura de opções binárias."
        }
    ),
    "highest_value_insight_for_agy": Choice(
        instructions="Entre as dezenas de técnicas apresentadas no livro, qual oferece o MAIOR ganho de Sharpe, alpha ou redução de risco para o AGY Trading System (opções binárias de 5m/15m em Polymarket e Kalshi)?",
        criteria={
            "execution_cost_optimization_and_spread_timing": "Otimização de Custos de Execução & Timing de Spread (Exemplo 12): A modelagem preditiva de custos de transação para evitar cruzar o spread em momentos desfavoráveis. Como o custo em opções binárias decorre de spreads no CLOB e slippage, refinar os gates de spread para aguardar recomposição de liquidez protege diretamente o P&L.",
            "corrective_ai_pop_filter": "Corrective AI / Meta-Labeling (Capítulo 8): Utilizar um classificador secundário leve para estimar a Probabilidade de Lucro (PoP) do sinal primário (135s/450s), vetando entradas em que a confiança prevista seja inferior a 50%.",
            "t_stat_trend_scanning_drift": "Trend Scanning com t-Stat de Regressão (Exemplo 1): Substituir a verificação linear simples de delta do spot pelo t-valor de significância estatística da regressão da janela de observação.",
            "reinforcement_learning_hedging": "Hedging por Reinforcement Learning (Capítulo 7): Implementar a política de RL de 2 estágios para gerenciar as defesas do Bonereaper."
        }
    ),
    "should_we_create_new_desks": Choice(
        instructions="O livro explora 19 exemplos em ações da NYSE, ETFs do QQQ/SPY, futuros da CME e pares de Forex. O JEV recomenda criar algum novo desk fora de Polymarket e Kalshi?",
        criteria={
            "strictly_maintain_prediction_markets_focus": "Manter Foco Estrito em Mercados Preditivos (Recomendado): Rejeitar a criação de desks tradicionais de ações ou futuros. Esses mercados exigem infraestrutura pesada, contas institucionais caras e enfrentam concorrência direta de mega-fundos, enquanto nosso edge reside na assimetria de liquidez de opções binárias.",
            "create_quantconnect_forex_desk": "Criar Desk de Forex Intraday no QuantConnect: Implementar o trade sazonal EUR/USD do Capítulo 8.",
            "create_stock_ranking_desk": "Criar Desk de Ranking de Ações com LGBRanker: Implementar o Exemplo 10 para operar ações americanas."
        }
    ),
    "codebase_refinement_recommendation": Choice(
        instructions="Qual é a melhoria cirúrgica recomendada pelo JEV para ser incorporada ao código atual do AGY System inspirada neste livro?",
        criteria={
            "refine_spread_gate_with_cost_delay": "Refinar o Gate de Spread com Filtro de Custo de Execução: Aprimorar `risk_gate.py` com uma lógica inspirada no Exemplo 12 que audita a relação Spread/Profundidade L2 antes do disparo da ordem, vetando entradas imediatas quando o spread do topo do livro exceder a média recente.",
            "add_heavy_transformer_models": "Adicionar Modelos Transformers Pesados (Chronos/FinBERT): Incorporar redes neurais profundas de NLP dentro do loop crítico dos bots.",
            "no_code_change_needed": "Nenhuma Alteração Necessária: Manter o código exatamente como está."
        }
    ),
    "what_to_strictly_avoid_or_retire": Choice(
        instructions="O que o JEV recomenda CATEGORICAMENTE EVITAR ou expurgar do sistema com base nas lições do livro de 2025?",
        criteria={
            "avoid_heavy_deep_learning_in_hot_loops": "Evitar Deep Learning Pesado em Loops Críticos (Zero Latência Bloqueante): Nunca tentar rodar modelos como Amazon Chronos, FinBERT ou CNNs profundas dentro do loop de 5 segundos dos robôs de trading, pois a latência de inferência (segundos/minutos) destruiria a execução na CLOB.",
            "avoid_spread_checks": "Evitar Checagens de Spread: Executar ordens a qualquer preço.",
            "avoid_dynamic_deadbands": "Evitar Deadbands Dinâmicos: Usar deadband fixo."
        }
    ),
    "overall_book_scientific_score": Score(
        instructions="Classifique de 1.0 a 5.0 a qualidade científica, aplicabilidade prática e nível institucional do livro 'Hands-On AI Trading with Python, QuantConnect, and AWS' (2025).",
        criteria=[
            "1.0 - Material básico de marketing sem código funcional.",
            "2.0 - Conceitos superficiais de IA aplicados de forma ingênua.",
            "3.0 - Bom conteúdo, mas com desafios para aplicação em produção.",
            "4.0 - Excelente: 19 estratégias documentadas, microestrutura L2, código funcional e autoria de veteranos da indústria.",
            "5.0 - Estado da Arte Máximo: O mais moderno guia prático de IA institucional para traders quantitativos."
        ]
    )
}

print("=" * 80)
print("CONSULTANDO JEV SYSTEMONE SOBRE O LIVRO 'HANDS-ON AI TRADING' (2025)...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_book_quality": {
        "choice": res.answers["book_scientific_quality_and_relevance"].choice,
        "confidence": res.answers["book_scientific_quality_and_relevance"].confidence,
        "probs": res.answers["book_scientific_quality_and_relevance"].probabilities
    },
    "q2_highest_value_insight": {
        "choice": res.answers["highest_value_insight_for_agy"].choice,
        "confidence": res.answers["highest_value_insight_for_agy"].confidence,
        "probs": res.answers["highest_value_insight_for_agy"].probabilities
    },
    "q3_should_we_create_new_desks": {
        "choice": res.answers["should_we_create_new_desks"].choice,
        "confidence": res.answers["should_we_create_new_desks"].confidence,
        "probs": res.answers["should_we_create_new_desks"].probabilities
    },
    "q4_codebase_refinement": {
        "choice": res.answers["codebase_refinement_recommendation"].choice,
        "confidence": res.answers["codebase_refinement_recommendation"].confidence,
        "probs": res.answers["codebase_refinement_recommendation"].probabilities
    },
    "q5_what_to_avoid": {
        "choice": res.answers["what_to_strictly_avoid_or_retire"].choice,
        "confidence": res.answers["what_to_strictly_avoid_or_retire"].confidence,
        "probs": res.answers["what_to_strictly_avoid_or_retire"].probabilities
    },
    "q6_scientific_score": {
        "score": res.answers["overall_book_scientific_score"].score,
        "confidence": res.answers["overall_book_scientific_score"].confidence
    }
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_hands_on_ai_trading_book_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
