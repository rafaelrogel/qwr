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
DOSSIÊ QUANTITATIVO: AVALIAÇÃO CRÍTICA DO LIVRO 'QUANTITATIVE TRADING' (2ª EDIÇÃO, 2021)
AUTOR: DR. ERNEST P. CHAN (PhD em Física Teórica por Cornell, ex-Morgan Stanley, Credit Suisse, IBM, QTS Capital & PredictNow.ai)
EDITORA: John Wiley & Sons

CONTEXTO DO SISTEMA EM PRODUÇÃO:
- O AGY Trading System opera 12 Desks em mercados preditivos binários (Polymarket 5m e Kalshi 15m).
- Liquidação determinística em $0.00 ou $1.00 baseada em oráculos (Chainlink/Pyth/NOAA/NYSE).
- Microestrutura L2: CLOB V2, Order Book Imbalance (OBI), Binance CVD & Microprice drift, Dynamic Deadbands moduladas por regime diurno + multiplicador ATR adaptativo, SirMartingale Take-Profit, Bonereaper Hedge e Fractional Kelly.
- Banca Atual: $29.90 USD (+42.38% de lucro líquido na Polymarket) e Kalshi Shard 2 intacto ($9.05 USD + $5.87 em custódia de contratos).

CONTEÚDO E PILARES QUANTITATIVOS DO LIVRO DE ERNIE CHAN (2ª EDIÇÃO):
1. A Vantagem do Trader Independente vs. Hedge Funds Gigantes:
   - Capacidade e Nichos: Fundos de $1B+ sofrem com impacto de mercado brutal e não conseguem operar em nichos de baixa capacidade ($50k-$500k).
   - O trader independente prospera em nichos microscópicos atuando como provedor de liquidez oportunista e explorador de fricções de curto prazo (exatamente nosso modelo em Polymarket e Kalshi).
2. Crítica Científica à IA / Machine Learning Ingênuo:
   - Previsão direta de preços via IA (redes neurais em retornos brutos) falha devido à baixa relação sinal-ruído, não-estacionariedade e reflexividade.
   - O único uso válido de IA é o Metalabeling (López de Prado / PredictNow.ai) e a Otimização Condicional de Parâmetros (CPO) — prevendo a probabilidade de lucro da própria estratégia, não o mercado público.
3. Rigor de Backtesting e Métricas Avançadas:
   - Teste de Truncamento para Detecção de Look-Ahead Bias: truncar os últimos N dias e comparar as ordens geradas.
   - Deflated Sharpe Ratio (Bailey & López de Prado) e tamanho amostral mínimo ($N \ge 681$ para Sharpe=1, $N \ge 174$ para Sharpe=2).
   - Fricções reais: bid-ask spread, slippage, market impact (regra do 1% do ADV e escala pela raiz quarta do market cap).
4. Gestão de Risco e Alocação de Capital (Capítulo 6):
   - Critério de Kelly: $f^* = (m - r_f)/s^2$ e alocação multivariada $F^* = C^{-1}M$.
   - Taxa de crescimento composto a longo prazo: $g = r_f + S^2 / 2$ (o crescimento depende do Sharpe ao quadrado, não do retorno nominal).
   - Half-Kelly como norma institucional para mitigar caudas pesadas (fat tails / Black Swans).
   - A Doutrina do Stop-Loss de Ernie Chan: Stop-loss é benéfico APENAS em regimes de momentum; em regimes de reversão à média, o stop-loss é prejudicial pois força a liquidação no pior momento da oscilação com slippage catastrófico.
   - Não-Ergodicidade e Aversão à Perda como Racionalidade Matemática: Com base em Ole Peters e Murray Gell-Mann (2016), a média de tempo de um único agente sob apostas multiplicativas repetidas colapsa a zero se o risco não for controlado, provando que a aversão à ruína não é um viés comportamental, mas sim sobrevivência física.
5. Tópicos Especiais (Capítulo 7):
   - Cointegração vs. Correlação: teste CADF (Dickey-Fuller aumentado) e estacionariedade.
   - Processo de Ornstein-Uhlenbeck (OU) e Meia-Vida de Reversão: $dz = \\theta(\\mu - z)dt + dw$, onde Meia-Vida $= -\\ln(2)/\\theta$.
   - Modelos de Fatores (Fama-French 3-Factors, PCA de fatores estatísticos).
   - Estratégias Sazonais: Gasolina em Abril (NYMEX RB) e Gás Natural (NG).
   - Paridade de Risco: alavancar carteiras de baixo beta supera carteiras de alto beta desalavancadas.
================================================================================
"""

questions = {
    "scientific_rigor_and_pedigree": Choice(
        instructions="Como o JEV avalia o rigor científico, a densidade matemática e o pedigree institucional deste livro de Ernest P. Chan (2021) em comparação com livros convencionais de análise técnica de varejo?",
        criteria={
            "institutional_masterpiece": "Obra-Prima Institucional e Referência Científica: Escrito por um PhD em Física Teórica com experiência em Wall Street (Morgan Stanley, Credit Suisse), o livro é um tratado rigoroso de econometria, microestrutura, controle estocástico e gestão de risco não-ergódica, diametralmente oposto ao material de varejo.",
            "intermediate_academic_survey": "Pesquisa Acadêmica Intermediária: Bom apanhado de tópicos, mas muito focado em equities e futuros da CME tradicionais.",
            "retail_fluff": "Material de Varejo Básico: Sem profundidade para operações algorítmicas de ponta."
        }
    ),
    "most_valuable_concept_for_agy": Choice(
        instructions="Entre todos os conceitos fundamentais explorados por Ernie Chan, qual oferece a validação teórica e o insight operacional de MAIOR impacto para o nosso ecossistema de 12 Desks em opções binárias (Polymarket 5m e Kalshi 15m)?",
        criteria={
            "ergodicity_and_fractional_kelly": "Não-Ergodicidade (Ole Peters) & Fractional Kelly: A prova matemática de que o crescimento de capital a longo prazo é governado pela média temporal e pelo Sharpe ao quadrado (g = rf + S^2/2), validando categoricamente nossa política de Fractional Kelly (0.15 a 0.40) e risk gates estritos para blindar o capital contra absorção em zero.",
            "stop_loss_regime_doctrine": "Doutrina de Stop-Loss por Regime: A demonstração de que stop-losses cegos destroem valor em regimes de reversão à média, justificando nossa arquitetura de Bonereaper Hedge e SirMartingale TP em vez de saídas desesperadas a mercado.",
            "ornstein_uhlenbeck_half_life": "Meia-Vida de Ornstein-Uhlenbeck: A modelagem da velocidade de reversão à média (half-life = -ln(2)/theta) para calibrar com precisão cirúrgica o tempo de vida restante das anomalias de spread e delta antes da expiração da vela.",
            "independent_low_capacity_niche_edge": "Teoria da Capacidade & Vantagem do Trader Independente: A confirmação de que mercados de micro-capacidade (como prediction markets) são onde os grandes fundos não conseguem entrar, criando uma barreira natural contra a predação de HFTs bilionários."
        }
    ),
    "should_we_create_new_desks": Choice(
        instructions="O livro apresenta exemplos práticos em pares de ETFs (GLD/GDX), fatores de Fama-French/PCA e contratos sazonais de commodities (Gasolina NYMEX em Abril e Gás Natural). O JEV recomenda abrir novos desks para operar esses mercados tradicionais?",
        criteria={
            "strictly_maintain_prediction_markets_focus": "Manter Foco Estrito em Mercados Preditivos (Recomendado): Rejeitar categoricamente a criação de desks de commodities ou ações tradicionais. Esses mercados exigem margens de dezenas de milhares de dólares na CME/Interactive Brokers, possuem alta competição institucional e diluiriam nosso edge cirúrgico e assimétrico em Polymarket e Kalshi.",
            "create_commodity_seasonal_desk": "Criar Desk de Sazonalidade de Commodities: Abrir um desk em futuros da CME para operar o contrato de Gasolina RB em abril.",
            "create_etf_stat_arb_desk": "Criar Desk de Arbitragem Estatística de ETFs: Implementar o par GLD/GDX via corretora tradicional."
        }
    ),
    "actionable_codebase_refinement": Choice(
        instructions="Qual é a recomendação prescritiva e prática do JEV para aprimoramento no código do AGY System inspirado no trabalho de Ernie Chan?",
        criteria={
            "ornstein_uhlenbeck_half_life_decay_gate": "Incorporar Meia-Vida de Ornstein-Uhlenbeck no Risk Gate: Adicionar em `risk_gate.py` ou `execution_math.py` uma rotina leve de estimação de reversão OU para medir a meia-vida do delta em relação ao strike, bloqueando trades onde a meia-vida projetada exceder o tempo restante da vela de 5m/15m.",
            "deflated_sharpe_ratio_audit": "Implementar Auditoria de Deflated Sharpe Ratio no Dashboard: Calcular o Deflated Sharpe Ratio de Bailey & López de Prado no `dashboard_server.py` para monitorar alpha decay.",
            "no_code_change_needed_current_setup_is_optimal": "Nenhuma Alteração de Código Necessária: O sistema atual já opera com Fractional Kelly, Deadband ATR adaptativo e Bonereaper Hedge em harmonia com todos os princípios de Chan."
        }
    ),
    "what_to_strictly_avoid_or_retire": Choice(
        instructions="O que o JEV recomenda CATEGORICAMENTE EVITAR ou expurgar do sistema com base nas lições de risco de Ernie Chan?",
        criteria={
            "avoid_blind_stop_losses_and_overfitting": "Evitar Stop-Loss Cego a Mercado e Evitar Adicionar Dezenas de Parâmetros: Nunca adotar ordens de stop-loss a mercado que vendam centavos em pânico, e nunca aumentar o número de parâmetros livres das estratégias (manter <= 5 regras para blindar contra data-snooping bias).",
            "avoid_fractional_kelly": "Evitar Fractional Kelly: Voltar a operar com tamanho fixo.",
            "avoid_limit_orders": "Evitar Ordens Limite: Usar apenas ordens a mercado."
        }
    ),
    "overall_book_scientific_score": Score(
        instructions="Classifique de 1.0 a 5.0 a qualidade científica, relevância prática e solidez metodológica do livro de Ernest P. Chan (2021) para o desenvolvimento de sistemas algorítmicos profissionais.",
        criteria=[
            "1.0 - Material puramente comercial ou de varejo básico.",
            "2.0 - Introdutório superficial sem rigor econométrico.",
            "3.0 - Qualidade razoável, com conceitos clássicos porém datados.",
            "4.0 - Muito bom: rigor estatístico, cobertura de custos reais e gestão de risco.",
            "5.0 - Referência Máxima / Nível Institucional: Alinha física teórica, microestrutura, formulação não-ergódica de risco e estratégias comprovadas."
        ]
    )
}

print("=" * 80)
print("CONSULTANDO JEV SYSTEMONE SOBRE O LIVRO 'QUANTITATIVE TRADING' DE ERNEST P. CHAN...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_scientific_rigor": {
        "choice": res.answers["scientific_rigor_and_pedigree"].choice,
        "confidence": res.answers["scientific_rigor_and_pedigree"].confidence,
        "probs": res.answers["scientific_rigor_and_pedigree"].probabilities
    },
    "q2_most_valuable_concept": {
        "choice": res.answers["most_valuable_concept_for_agy"].choice,
        "confidence": res.answers["most_valuable_concept_for_agy"].confidence,
        "probs": res.answers["most_valuable_concept_for_agy"].probabilities
    },
    "q3_should_we_create_new_desks": {
        "choice": res.answers["should_we_create_new_desks"].choice,
        "confidence": res.answers["should_we_create_new_desks"].confidence,
        "probs": res.answers["should_we_create_new_desks"].probabilities
    },
    "q4_actionable_refinement": {
        "choice": res.answers["actionable_codebase_refinement"].choice,
        "confidence": res.answers["actionable_codebase_refinement"].confidence,
        "probs": res.answers["actionable_codebase_refinement"].probabilities
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

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_ernie_chan_book_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
