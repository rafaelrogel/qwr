# -*- coding: utf-8 -*-
"""
CONSULTA INSTITUCIONAL AO JEV (TypeSafe SystemOne):
Debate Quantitativo sobre o Vídeo de Moon Dev:
- Estratégia de "Stink Bidding" em Baleias na Polymarket
- Os 3 Únicos Edges em 0DTE / Opções Intradiárias (Position Asymmetry, Volatility Mispricing, Execution Timing)
- Ilusão de Backtests de 5.900% (Compounding Artifacts & Overfitting de Multi-Agentes)
- Infraestrutura de Execução: PFOF (Rebates) vs Roteamento Direto (Slippage Oculto)
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
DOSSIÊ QUANTITATIVO JEV: ANÁLISE DO MODELO DE MOON DEV (0DTE OPTIONS & POLYMARKET WHALE STINK BIDDING)
Data/Hora: 2026-09-28 12:50 UTC
Referência: Transcrição ao vivo de Moon Dev (Stream/Zoom com Claude Opus 4.7 e backtests paralelos)
====================================================================================================

1. OS 4 CONCEITOS CENTRAIS DO VÍDEO DE MOON DEV:

   A) TESE 1: "POLYMARKET WHALE STINK BIDDING" (Cópia Passiva com Super Desconto):
      - Moon Dev desenvolveu um scanner que puxa as baleias mais lucrativas da Polymarket (filtrando quem lucrou > $100k com curva de capital estável no mês).
      - Em vez de copiar como TAKER (o que gera slippage negativo e front-running), ele propõe a estratégia de "STINK BID":
        * O bot monitora a carteira da baleia.
        * Se a baleia está posicionada em um lado (ex: YES a 65¢), o bot não compra a mercado.
        * O bot posiciona ordens LIMIT PASSIVAS na CLOB com 15% a 30% de desconto (ex: pendura bid a 45¢–50¢).
        * Tese: "Não quero copiar a mercado. Quero surfar a direção da baleia apenas se o mercado tiver um flash-crash de liquidez e me entregar um desconto massivo".

   B) TESE 2: OS 3 ÚNICOS EDGES EM 0DTE / MERCADOS BINÁRIOS TERMINAIS (TRAVIS'S 3 EDGES):
      - Moon Dev cita Travis, destacando que 99% dos traders de opções perdem dinheiro e que só existem 3 edges reais:
        1. Assimetria de Posição / Traders Presos (Position Asymmetry / Trapped Traders):
           - Quem está encurralado? Quem é obrigado a fazer hedge a qualquer custo? (Delta hedging de formadores de mercado em Gamma extremo).
        2. Desprecificação de Volatilidade (Volatility Mispricing):
           - Volatilidade Implícita (IV) vs Movimento Realizado Intradiário (RV).
        3. Timing de Execução (Execution Timing):
           - Precisão de segundos e minutos, NUNCA adivinhação direcional genérica.
        - Regra de Stop para 0DTE/Opções Rápidas:
          * "Se você colocar stop no preço de entrada do contrato, o decay temporal (theta) vai te estopar até a morte (chopped to death). O stop deve ser no subjacente ou com offset dinâmico."

   C) TESE 3: ARMADILHA DE OVERFITTING DE MULTI-AGENTES (COMPOUNDING ARTIFACTS):
      - Moon Dev roda 5 agentes paralelos de LLM (Opus 4.7) fazendo loops de otimização em 20 meses de dados de liquidação.
      - Os agentes retornam números exorbitantes (ex: 4.543% e 5.990% de retorno), mas com Sharpe Ratio inferior a 1.0 e Drawdowns severos.
      - Moon Dev admite: "Não se iludam, isso é um artefato de juros compostos (compounding artifact). O modelo está overfitado".

   D) TESE 4: O DILEMA PFOF VS ROTEAMENTO DIRETO (REBATES VS SLIPPAGE OCULTO):
      - Debate entre usar corretoras com rebate/PFOF (Public.com paga 6¢–18¢ por contrato de rebate para o trader) vs Roteamento Direto (Interactive Brokers cobra $0.65 de comissão mas busca o melhor preço em dark pools/exchanges).
      - Conclusão da análise: Os atacadistas (Citadel) pagam rebates porque internalizam o fluxo e comem 3¢ a 8¢ no spread. O slippage oculto é de 10¢ a 30¢ por contrato, tornando a comissão da IBKR mais barata no saldo líquido para estratégias sensíveis à latência.
      - Analogia com Polymarket: Na Polymarket CLOB, ser MAKER (prover liquidez passiva) não paga taxas e ainda qualifica para recompensas de liquidez, enquanto ser TAKER paga spread e taxas.

====================================================================================================
2. QUESTÕES DIRECIONADAS À INTELIGÊNCIA JEV (TypeSafe SystemOne):
====================================================================================================
"""

questions = {
    "whale_stink_bid_viability": Choice(
        instructions="JEV, avalie a estratégia de 'Whale Stink Bidding' na Polymarket: monitorar as carteiras das maiores baleias lucrativas e pendurar ordens passivas de compra na CLOB com 15% a 30% de desconto abaixo do preço de mercado. Isso gera Alpha Real de liquidez ou sofre de Seleção Adversa Tóxica (o bid só é preenchido quando saiu notícia contra a baleia ou a tese quebrou)?",
        criteria={
            "TOXIC_ADVERSE_SELECTION": "Predomínio de Seleção Adversa Tóxica: Em prediction markets, ordens passivas muito abaixo do mercado (stink bids) só são executadas quando ocorre um choque de informação fundamental adverso. A baleia pode estar presa em uma tese morta e o mercado despeja contra os stink bids com probabilidade terminal quase nula, destruindo a expectativa matemática.",
            "POSITIVE_EV_LIQUIDITY_HARVESTING": "Alpha Real de Provisão de Liquidez: Em mercados com formadores de mercado algorítmicos e dumps temporários de varejo, capturar 15-30% de desconto em teses de baleias consistentes gera expectativa matemática altamente positiva.",
            "VIABLE_ONLY_WITH_CANCEL_ORACLE": "Viável apenas com Oráculo de Cancelamento Rápido: Só é viável se o bot cancelar instantaneamente a ordem se o preço de referência spot ou notícias romperem contra o contrato antes da execução."
        }
    ),
    "travis_three_edges_relevance": Choice(
        instructions="Travis afirma que em opções intradiárias (0DTE) existem apenas 3 edges reais: 1) Assimetria de Posição / Traders Presos (Trapped Traders); 2) Desprecificação de Volatilidade (IV vs RV); 3) Timing de Execução em segundos/minutos. Essa taxonomia é matematicamente válida para as nossas mesas (Desk 1 BTC 5m e Desk 11 SPX 15m)?",
        criteria={
            "UNIVERSAL_INTRADAY_TAXONOMY": "Taxonomia Universalmente Válida: A taxonomia de Travis captura a essência da microestrutura moderna. Tentar prever direção pura falha; capturar traders presos (hedging forçado), descolamento de volatilidade e timing de milissegundos é a base do edge matemático.",
            "INCOMPLETE_OR_FLAWED": "Incompleta ou inadequada para prediction markets binários.",
            "DIRECTIONAL_MOMENTUM_STILL_DOMINATES": "O momentum direcional tradicional supera os 3 edges propostos."
        }
    ),
    "compounding_artifacts_warning": Choice(
        instructions="Moon Dev observou retornos simulados de 5.900% gerados por agentes autônomos em loops, mas com Sharpe < 1.0 e drawdowns brutais, classificando-os como 'Compounding Artifacts'. Qual é a recomendação do JEV sobre o uso de agentes autônomos de IA para geração e otimização de estratégias quantitativas?",
        criteria={
            "STRICT_METRIC_ANCHORING_REQUIRED": "Ancoragem Mandatória em Métricas Robustas: Agentes livres otimizando apenas PnL bruto sempre geram overfit e artefatos de juros compostos. É imperativo ancorar a otimização estritamente em Sharpe > 1.8, Profit Factor > 1.6, Max Drawdown < 10% e testes fora da amostra (Out-of-Sample / Walk-Forward), rejeitando retornos exponenciais ilusórios.",
            "UNRESTRICTED_AGENT_EXPLORATION": "Deixar agentes gerarem estratégias sem restrições métricas porque os retornos compensam o risco."
        }
    ),
    "pfof_vs_clob_implication": Choice(
        instructions="A análise de PFOF vs Roteamento Direto (onde o rebate de 6-18¢ mascara um slippage oculto de 10-30¢ dos wholesalers) traz que lição prática para o nosso sistema na Polymarket e Kalshi?",
        criteria={
            "MAKER_REBATES_AND_SPREAD_CAPTURE_MATTERS": "O custo invisível do Spread e Slippage supera qualquer incentivo cosmético: Na Polymarket e Kalshi, a fronteira entre lucro e prejuízo é ditada pelo spread. Entrar a mercado (Taker) paga pedágio que corrói o edge; a prioridade deve ser sempre execução cirúrgica de spread mínimo (CLOB spread <= 0.06) ou captura passiva de liquidez.",
            "COMMISSIONS_ARE_IRRELEVANT": "O impacto das taxas e spreads é secundário frente à direção do ativo."
        }
    )
}

print("=" * 80)
print(" [JEV CONSULTATION] SUBMETENDO DOSSIÊ DE MOON DEV PARA IA JEV...")
print("=" * 80)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n>>> PARECER JEV RECEBIDO EM {elapsed:.2f}s <<<\n")

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

output_file = "jev_moondev_debate_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Veredito arquivado em '{output_file}'.")
