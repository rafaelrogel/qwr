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
DOSSIÊ QUANTITATIVO: AVALIAÇÃO DO LIVRO 'GENERATIVE AI FOR TRADING AND ASSET MANAGEMENT' (2025)
AUTORES: Hamlet Jesse Medina Ruiz (Chief Data Scientist na Criteo, MIT MicroMasters in Finance, PhD em Física por Paris-Saclay)
e Dr. Ernest P. Chan (PredictNow.ai, QTS Capital Management, PhD em Física por Cornell).
EDITORA: John Wiley & Sons, Inc. (2025)

CONTEXTO DO AGY TRADING SYSTEM:
- 12 Desks em produção operando opções binárias (Polymarket 5m e Kalshi 15m), liquidação determinística em $0.00 ou $1.00.
- Microestrutura L2: CLOB V2, Order Book Imbalance (OBI), Binance CVD & Microprice drift, Dynamic Deadbands modulados por regime diurno + ATR adaptativo non-blocking, gate refinado de spread em 4 faixas com tolerância de 2.0s para recomposição (Wiley 2025), SirMartingale Take-Profit, Bonereaper Hedge e Fractional Kelly.
- Banca atual: $29.90 USD (+42.38% líquido na Polymarket) e Kalshi Shard 2 intacto ($9.05 USD livres + $5.87 em custódia).

CONTEÚDO E CONTRIBUIÇÕES CIENTÍFICAS DA OBRA (2025):
1. Parte I - GenAI No-Code & Machine Learning na Gestão de Investimentos (Dr. Ernie Chan):
   - Reforço do Corrective AI (Meta-Labeling): O ML nunca deve prever o preço bruto de mercado (sujeito a arbitragem e decay), mas sim prever a Probabilidade de Lucro (PoP > 0.50) da estratégia primária.
   - Hierarchical Risk Parity (HRP) e cMDA (Cluster-based Feature Selection): Agrupar features e ativos por correlação hierárquica antes de calcular importância de permutação ou alocar capital (evita seleção arbitrária de variáveis colineares).
   - Auditoria de dados: Cuidado extremo com look-ahead bias em revisões de dados econômicos (NFP), datas de balanços esperadas (Wall Street Horizon) e quebras estruturais em feeds de terceiros (mudanças de metodologia de sentiment em 2015).
2. Parte II - Modelos Generativos Profundos (Hamlet Medina Ruiz):
   - Modelagem Híbrida p(x, y) = p(x) * p(y|x): Modelos puramente discriminativos p(y|x) falham em produção porque emitem previsões com alta confiança sobre dados fora da distribuição (Out-of-Distribution / OOD / Regime Shifts). Modelar a densidade de entrada p(x) permite detectar anomalias e forçar o modelo a "não opinar" (incerteza / veto) quando p(x) colapsa!
   - Famílias Generativas: Modelos Autoregressivos (WaveNet, Transformers, Chronos vs Lag-Llama), VAEs (TimeVAE com blocos interpretáveis de tendência e sazonalidade), Normalizing Flows (NICE, Real-NVP invertíveis) e GANs (WGAN-GP, TimeGAN).
   - Aplicação Real de Alta Frequência (Capítulo 9): Pipeline ponta-a-ponta processando discursos em vídeo do Fed Chair Jerome Powell (YouTube -> ffmpeg 60s bars com lag de 15s -> Whisper ASR -> FinBERT sentiment -> sinal de trading de 30s no SPY). Resultado: correlação de 14.14% com retornos forward (p = 0.00199), 53.15% de acerto direcional e Sharpe positivo após custos de 5 bps!
   - Eficiência de Inferência (Capítulo 10): Knowledge Distillation (FinBERT -> DistilFinBERT gerando 2.12x de aceleração com mesma acurácia) e Quantização Linear INT8 (gerando 3.35x de aceleração com 4x de compressão de memória).
================================================================================
"""

questions = {
    "book_scientific_rigor_and_depth": Choice(
        instructions="Como o JEV avalia o rigor teórico, a originalidade matemática e o valor prático desta obra de Medina Ruiz e Ernie Chan (2025) para a engenharia quantitativa moderna?",
        criteria={
            "institutional_state_of_the_art": "Estado da Arte Institucional (2025): Uma das obras mais sofisticadas do mercado, combinando a física teórica de Medina Ruiz e Chan com microestrutura rigorosa, formulação de modelos de fluxo, VAEs para séries temporais e soluções reais de latência e inferência.",
            "advanced_niche_survey": "Pesquisa Avançada de Nicho: Bom tratado sobre modelos generativos, mas com foco predominantemente acadêmico em redes profundas.",
            "commercial_fluff": "Material Comercial Básico: Sem profundidade analítica."
        }
    ),
    "highest_value_insight_for_agy": Choice(
        instructions="Entre os avanços teóricos do livro, qual oferece o MAIOR benefício arquitetural e de segurança para o AGY Trading System (opções binárias de 5m/15m em Polymarket e Kalshi)?",
        criteria={
            "hybrid_modeling_ood_veto": "Modelagem Híbrida & Detecção de Out-of-Distribution (OOD): A prova de que modelos puramente discriminativos p(y|x) quebram diante de choques de regime emitindo falsas certezas. Modelar a densidade de entrada p(x) (ex: volatilidade, profundidade L2, CVD) para criar um veto automático de incerteza ('Não Sei / Não Opere') quando o mercado entra em anomalia severa.",
            "inference_efficiency_quantization_principle": "Princípio da Eficiência de Inferência: A confirmação de que em trading sistemático a latência de execução dita o P&L, justificando manter nossa inferência ultraleve em memória (< 0.005ms) em vez de carregar modelos pesados não-quantizados no loop quente.",
            "event_driven_fed_speech_nlp": "Trading Orientado a Eventos de Discursos do Fed: Utilizar transcrição Whisper e FinBERT em dias de FOMC para alimentar os Desks 3 e 11 de 15m da Kalshi.",
            "hierarchical_risk_parity_and_cmda": "HRP e cMDA: Agrupamento em cluster de variáveis colineares antes de calcular importância de features."
        }
    ),
    "should_we_create_new_desks": Choice(
        instructions="O livro apresenta aplicações em ações individuais, futuros do VIX, calendar spreads de opções SPX e pares de Forex. O JEV recomenda criar algum novo desk fora de Polymarket e Kalshi?",
        criteria={
            "strictly_maintain_prediction_markets_focus": "Manter Foco Estrito em Mercados Preditivos (Recomendado): Rejeitar categoricamente abrir novos desks tradicionais fora de Polymarket e Kalshi. Esses mercados tradicionais demandam grande capital institucional na CME/CBOE e diluem nossa vantagem competitiva em opções binárias.",
            "create_fomc_speech_desk": "Criar Desk Dedicado de Discursos do Fed (FOMC Speech Harvester): Implementar um novo desk conectado ao YouTube/Whisper para operar eventos do Fed.",
            "create_vix_futures_carry_desk": "Criar Desk de Carry em Futuros do VIX: Operar a estratégia Simon & Campasano em futuros da CBOE."
        }
    ),
    "codebase_refinement_recommendation": Choice(
        instructions="Qual é a melhoria conceitual ou cirúrgica recomendada pelo JEV inspirada neste livro para o nosso código?",
        criteria={
            "integrate_ood_novelty_veto_gate": "Integrar Gate de Novidade/OOD no Risk Gate: Formalizar uma verificação em `risk_gate.py` que avalia se os inputs correntes (spread, desbalanceamento de livro, drift de spot) estão fora de 3 sigmas da distribuição normal recente (p(x) colapsada), vetando a entrada por incerteza de regime.",
            "deploy_heavy_diffusion_models": "Adicionar Modelos de Difusão no Robô: Integrar geradores de séries temporais difusivas no loop dos robôs.",
            "no_code_change_needed": "Nenhuma Alteração Necessária: Manter o código exatamente como está."
        }
    ),
    "what_to_strictly_avoid_or_retire": Choice(
        instructions="O que o JEV recomenda CATEGORICAMENTE EVITAR ou expurgar do sistema com base nas lições do livro de 2025?",
        criteria={
            "avoid_unquantized_heavy_models_in_realtime": "Evitar Modelos Pesados Não-Quantizados e Feeds de Terceiros Não-Auditados: Nunca colocar modelos de deep learning de grande escala no caminho crítico de execução em tempo real, e nunca aceitar feeds de dados ou indicadores externos sem teste prévio de quebra estrutural e look-ahead bias.",
            "avoid_probabilistic_models": "Evitar Modelos Probabilísticos: Usar apenas heurísticas manuais simples.",
            "avoid_kalshi_contracts": "Evitar Contratos da Kalshi: Operar apenas na Polymarket."
        }
    ),
    "overall_book_scientific_score": Score(
        instructions="Classifique de 1.0 a 5.0 a qualidade científica, originalidade matemática e rigor prático do livro de Medina Ruiz e Ernie Chan (2025).",
        criteria=[
            "1.0 - Conteúdo superficial sem fundamentação teórica.",
            "2.0 - Compilação de código básico sem profundidade matemática.",
            "3.0 - Bom conteúdo técnico, mas com pouca aplicação direta para microestrutura.",
            "4.0 - Excelente: une teoria de probabilidades, deep generative modeling, microestrutura e otimização computacional.",
            "5.0 - Obra-Prima Máxima: Redefine a literatura de AI generativa e inferência eficiente para o setor financeiro."
        ]
    )
}

print("=" * 80)
print("CONSULTANDO JEV SYSTEMONE SOBRE O LIVRO 'GENERATIVE AI FOR TRADING' (2025)...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_book_quality": {
        "choice": res.answers["book_scientific_rigor_and_depth"].choice,
        "confidence": res.answers["book_scientific_rigor_and_depth"].confidence,
        "probs": res.answers["book_scientific_rigor_and_depth"].probabilities
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

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_genai_trading_book_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
