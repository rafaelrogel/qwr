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
from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
client = TypeSafeClient(api_key=key)

dossier = """
================================================================================
DOSSIÊ QUANTITATIVO: AVALIAÇÃO CRÍTICA DO LIVRO 'ALGORITHMIC TRADING STRATEGIES' (2022)
Contexto do Sistema: O AGY System opera 12 Desks em mercados preditivos binários (Polymarket 5m e Kalshi 15m),
com liquidação determinística em $0.00 ou $1.00 baseada em oráculos (Chainlink/Pyth/NOAA/NYSE).
A execução é de alta precisão em microestrutura L2 (CLOB V2, Order Book Imbalance, CVD Binance, TWAP Trap Shield, SirMartingale Take-Profit e Fractional Kelly).

CONTEÚDO DO LIVRO ANALISADO:
O livro apresenta 14 indicadores do TradingView e 18 estratégias de scalping e trend-following para cripto/forex:
1. Indicadores Chave:
   - PMax (KivancOzbilgic): Supertrend modificado com ATR adaptativo e MAs (VAR/EMA).
   - QQE & QQE Mod (KivancOzbilgic / Mihkel00): Qualitative Quantitative Estimation (RSI suavizado com bandas de volatilidade ATR).
   - Normalized Smoothed MACD (NSM - Dreadblitz): MACD normalizado entre -1 e +1 com suavização.
   - Bollinger Bands on MACD (Dreadblitz): Bandas de volatilidade aplicadas ao oscilador.
   - VWMA / VWAP Bands: Médias ponderadas por volume.
   - RMI (Relative Momentum Index), Stochastic OTT, SMI, Aroon, Didi Index, REX Oscillator.
2. Estratégias Propostas:
   - Crossovers simples de médias (SMA 9/18, SMMA 4/9, SMA 200).
   - Scalping de bandas de Bollinger + RSI (4 e 7 períodos).
   - Automação sem código via TradingView Webhooks + Capitalise.ai.

GARGALOS & DIFERENÇAS ESTRUTURAIS:
- O livro foi escrito para trading direcional de spot/futuros contínuos, onde o payoff é linear (Preço de Venda - Preço de Compra).
- Nosso sistema opera opções binárias com prazo fixo e discreto de 300s (5m) ou 900s (15m), onde o oráculo liquida em $1.00 ou $0.00. Indicadores com atraso (lag) de 5 a 10 barras (como SMA 200 ou cruzamentos de médias lentas) são fatais em velas de 5 minutos.
- No entanto, conceitos de volatilidade adaptativa (ATR bands do PMax e QQE) e normalização de osciladores (NSM) podem ter valor estatístico para calibragem dinâmica de Deadbands.
================================================================================
"""

questions = {
    "retail_vs_institutional_utility": Choice(
        instructions="Qual é a avaliação quantitativa do JEV sobre a utilidade das estratégias deste livro para o AGY Trading System (opções binárias de 5m/15m em Polymarket e Kalshi)?",
        criteria={
            "selective_component_extraction": "Extração Seletiva de Componentes (Recomendado): 85% do livro é análise técnica de varejo defasada (cruzamento de médias móveis simples e webhooks lentos) que levaria ao drawdown em opções binárias. Porém, 15% (especificamente a modelagem de volatilidade adaptativa do PMax/ATR e o filtro de exaustão do QQE Mod) pode ser refinado matematicamente para modular nossos Deadbands.",
            "total_rejection_retail_fluff": "Rejeição Total: O livro é puramente focado em TradingView básico para iniciantes sem nenhuma modelagem de microestrutura, livro L2 ou opções binárias. Nada se aproveita.",
            "direct_implementation_as_new_desk": "Implementação Direta: Criar um novo Desk copiando integralmente uma das estratégias de scalping do livro."
        }
    ),
    "most_valuable_concept_extracted": Choice(
        instructions="Entre todos os 14 indicadores e estratégias do livro, qual conceito possui o maior Information Coefficient (IC) potencial se adaptado ao nosso pipeline quantitativo?",
        criteria={
            "qqe_mod_volatility_exhaustion": "QQE Mod (RSI + ATR Bands): Excelente para detectar exaustão de impulso antes do ponto de decisão (135s na Polymarket / 450s na Kalshi), servindo como filtro contra falsos rompimentos no final da vela.",
            "pmax_adaptive_trailing_deadband": "PMax Adaptive ATR: Substituir o deadband estático/linear por um canal ATR adaptativo que expande na volatilidade e contrai na calmaria.",
            "vwma_volume_weighted_drift": "VWMA Lead-Lag: Substituir a média de preços simples pelo VWMA para medir o preço justo ponderado por volume dos últimos 15 minutos.",
            "none_worth_incorporating": "Nenhum: Nenhuma métrica supera o CVD e o Order Book Imbalance que já possuímos."
        }
    ),
    "what_to_strictly_reject": Choice(
        instructions="O que o JEV recomenda categoricamente REJEITAR ou NUNCA incorporar ao código do AGY a partir deste material?",
        criteria={
            "reject_naive_ma_crossovers_and_nocode": "Rejeitar Crossovers de Médias Lentas e Plataformas Sem Código: Rejeitar absolutamente cruzamentos de SMA (9/18, 45, 200), que possuem lag terminal para velas de 5m, e rejeitar plataformas externas como Capitalise.ai que introduzem latência de 2 a 10 segundos inaceitável para a CLOB.",
            "reject_rsi_oversold_scalping": "Rejeitar Scalping de RSI Oversold: Comprar apenas porque o RSI está abaixo de 30 em opções binárias é suicídio de capital durante fortes tendências institucionais.",
            "reject_all_of_the_above": "Rejeitar Todos os Acima: Rejeitar tanto cruzamentos lentos quanto webhooks de terceiros e compras cegas em sobrevenda."
        }
    ),
    "actionable_architectural_recommendation": Choice(
        instructions="Qual é a recomendação prescritiva e prática do JEV para o nosso roadmap de desenvolvimento?",
        criteria={
            "enhance_existing_deadbands_with_atr_filter": "Aprimorar Filtros Existentes (Não criar desk novo): Não criar nenhum desk novo de varejo. Integrar uma função leve de QQE/ATR no `risk_gate.py` para reforçar a detecção de exaustão nos Desks 1, 2 e 3, mantendo a arquitetura L2 intocada.",
            "create_new_desk_desk13": "Criar Desk 13 (Crypto Trend Harvester): Abrir um desk de paper trading focado em swing trade tradicional de perpétuos da Binance utilizando PMax + QQE.",
            "do_not_touch_anything": "Não Tocar em Nada: O sistema acabou de vencer com +142% e +60% hoje. Não poluir o código com conceitos de livros de 2022."
        }
    ),
    "information_quality_score": Score(
        instructions="Classifique de 1.0 a 5.0 a densidade científica e robustez quantitativa do livro analisado (considerando que não apresenta testes estatísticos de p-value, t-stat, custos de transação ou slippage real).",
        criteria=[
            "1.0 - Varejo Básico / Não Científico: Apenas ilustrações visuais sem slippage, taxas ou testes de significância estatística.",
            "2.0 - Educacional Introdutório: Bom catálogo de ferramentas PineScript, mas sem rigor acadêmico ou quantitativo.",
            "3.0 - Médio: Estratégias heurísticas clássicas que funcionavam em mercados menos eficientes.",
            "4.0 - Robusto: Apresenta backtests rigorosos com custos de transação e walk-forward.",
            "5.0 - Nível Institucional / Hedge Fund: Modelagem econométrica, microestrutura e teste de hipótese nula."
        ]
    )
}

print("=" * 80)
print("ENVIANDO DOSSIÊ DO LIVRO 'ALGORITHMIC TRADING STRATEGIES' PARA O JEV SYSTEMONE...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_utility": {
        "choice": res.answers["retail_vs_institutional_utility"].choice,
        "confidence": res.answers["retail_vs_institutional_utility"].confidence,
        "probs": res.answers["retail_vs_institutional_utility"].probabilities
    },
    "q2_best_concept": {
        "choice": res.answers["most_valuable_concept_extracted"].choice,
        "confidence": res.answers["most_valuable_concept_extracted"].confidence,
        "probs": res.answers["most_valuable_concept_extracted"].probabilities
    },
    "q3_what_to_reject": {
        "choice": res.answers["what_to_strictly_reject"].choice,
        "confidence": res.answers["what_to_strictly_reject"].confidence,
        "probs": res.answers["what_to_strictly_reject"].probabilities
    },
    "q4_recommendation": {
        "choice": res.answers["actionable_architectural_recommendation"].choice,
        "confidence": res.answers["actionable_architectural_recommendation"].confidence,
        "probs": res.answers["actionable_architectural_recommendation"].probabilities
    },
    "q5_quality_score": {
        "score": res.answers["information_quality_score"].score,
        "confidence": res.answers["information_quality_score"].confidence
    }
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_book_review_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
