# -*- coding: utf-8 -*-
"""
CONSULTA INSTITUCIONAL AO JEV (TypeSafe SystemOne):
Auditoria Completa dos 10 Repositórios da postagem @recogard sobre Polymarket
e Debate Intelectual sobre Oportunidades de Aplicação, Novos Desks e Melhorias no Código AGY.
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
DOSSIÊ QUANTITATIVO: AUDITORIA DOS 10 REPOSITÓRIOS GITHUB (@recogard) PARA POLYMARKET
Data: 2026-09-28 | Objeto: Postagem viral @recogard com 10 ferramentas de ponta para Polymarket
Alvo: Avaliar a veracidade, o rigor quantitativo e as oportunidades reais de novos Desks e código.
====================================================================================================

OS 10 REPOSITÓRIOS AUDITADOS:

1. recogardtech/AutoPilotPM (AutoPilot AI Terminal):
   - Terminal autônomo com 80 dependências, 119 skills, interfaces Telegram/Discord/Slack/Web.
   - Suporta múltiplos mercados (Polymarket, Kalshi, Betfair, Binance, Hyperliquid).
   - Foco: Hub agregador conversacional com Claude/OpenAI. Muito amplo, pouca especialização microestrutural.

2. SII-WANGZJ/Polymarket_data (Shanghai Innovation Institute / Fudan / Westlake Univ):
   - O maior dataset público de Polymarket: 107 GB em Parquet, 1.1 bilhão de registros de trades desde a gênese.
   - Ingestão direta da Polygon blockchain (sem dependência de APIs REST com rate limit).
   - 268.000+ mercados mapeados com sincronização em tempo real (modo contínuo a cada 2s).

3. evan-kolberg/prediction-market-backtesting (Nautilus Trader Extension em Rust/Python):
   - Simulador de backtesting de nível institucional estendendo o Nautilus Trader.
   - Versão 4.1-alpha inclui encanamento de sandbox em tempo real para 'Polymarket BTC 5min markets' (o nosso nicho exato!).
   - Modela com precisão slippage da CLOB L2, latência de rede e taxas.

4. lihanyu81/polymarket_lp_tool (Polymarket Liquidity Rewards 2.0):
   - Foco exclusivo em colher recompensas diárias de liquidez da Polymarket (Liquidity Rewards em USDC).
   - Reescrito em Rust (Tokio, WebSockets) para monitorar e ajustar ordens passivas dentro do spread elegível.
   - Calcula a equação exata de pontuação de recompensas da Polymarket: S = ((v - s) / v)^2 * size.

5. ent0n29/polybot (Reverse Engineering & Whale Profiling):
   - Arquitetura corporativa em Java 21 + ClickHouse + Redpanda (Kafka).
   - Ingestão contínua de trades para rastrear e pontuar carteiras institucionais e baleias lucrativas (Replication Scoring).
   - Identifica padrões operacionais repetidos para modelagem de copy trading.

6. HarrierOnChain/Prediction-Markets-Trading-Bot-Toolkits:
   - Suíte de bots em puro Rust (Tokio, Async) cobrindo 10 estratégias formais:
     * cross_market_arb.rs (Arbitragem cruzada Polymarket vs Kalshi)
     * directional_arb.rs (Arbitragem direcional com latência Binance)
     * orderbook_imbalance.rs (Desequilíbrio de L2)
     * spread_farming.rs (Captura de spread)
     * resolution_sniper.rs (Varredura de liquidação no oráculo)
     * whale_signal.rs (Sinais de baleias)

7. yangyuan-zhen/PolyWeather (PolyWeather Pro - Weather Intelligence Stack):
   - Bot quantitativo em Python especializado em mercados de liquidação climática (temperatura diária).
   - Conecta a dados de aviação METAR (NOAA, aeroportos internacionais), MADIS, NWS e estações meteorológicas em tempo real.
   - Modelo estatístico com distribuição normal DEB para precificar contratos antes da liquidação oficial.
   - API de previsão em produção: api.polyweather.top.

8. caiovicentino/polymarket-mcp-server (Caio Vicentino / Renda Cripto):
   - Servidor oficial de Model Context Protocol (MCP) com 45 ferramentas para Polymarket.
   - Permite que agentes de IA inspecionem livros, posições, executem ordens e monitorem liquidez de forma padronizada.

9. pydantic/pydantic-ai:
   - Framework de agentes Python com tipos estritos e validação Pydantic.

10. aarora4/Awesome-Prediction-Market-Tools:
    - O diretório canônico da comunidade com mais de 150 recursos, bibliotecas e APIs para prediction markets.

====================================================================================================
NOSSO CONTEXTO ATUAL (AGY TRADING SYSTEM):
- 10 Desks ativos operando simultaneamente (Desk 1 BTC 5m Live, Desk 2 SOL 5m Live, Desk 3 Kalshi BTC 15m Live,
  Desk 5 Kalshi NatGas 15m Live, Desk 6 Yield Harvester, Desk 7 Cross-Arb, Desk 8 ETH, Desk 9 Gold, Desk 11 SPX).
- Saldo: $25.79 USDC na Polymarket (68.5% WR, 102V / 47D) e $12.47 USD na Kalshi (100% WR).
====================================================================================================
"""

questions = {
    "highest_alpha_repository": Choice(
        instructions="JEV, avalie os 10 repositórios. Qual deles oferece o MAIOR alfa quantitativo e valor estatístico imediato para o nosso sistema?",
        criteria={
            "SII_WANGZJ_POLYMARKET_DATA": "SII-WANGZJ/Polymarket_data (107 GB de dados históricos): O MAIOR ALFA ESTRATÉGICO. Ter 1.1 bilhão de trades em Parquet permite treinar e calibrar nossos modelos bayesianos e regras de deadband com a distribuição empírica real de 268.000 mercados, eliminando suposições teóricas.",
            "POLYWEATHER_METAR_STACK": "yangyuan-zhen/PolyWeather: O MAIOR ALFA OPERACIONAL. A exploração de assimetria de oráculo climático (METAR aeroportuário antes da liquidação) é a anomalia mais previsível e de maior EV no ecossistema de prediction markets.",
            "HARRIER_RUST_TOOLKITS": "HarrierOnChain/Prediction-Markets-Trading-Bot-Toolkits: O MAIOR ALFA DE EXECUÇÃO. A suíte em Rust de 10 bots com arbitragem cruzada e orderbook imbalance oferece a infraestrutura de menor latência.",
            "EVAN_KOLBERG_NAUTILUS": "evan-kolberg/prediction-market-backtesting: O maior valor para simulação rigorosa de BTC 5m.",
            "LIHANYU_LP_TOOL": "lihanyu81/polymarket_lp_tool: O maior valor para colher recompensas diárias sem risco direcional."
        }
    ),
    "new_desk_recommendation": Choice(
        instructions="JEV, considerando a nossa arquitetura de 10 Desks, devemos criar um NOVO DESK baseado em alguma dessas descobertas?",
        criteria={
            "ADD_DESK12_WEATHER_METAR_ARBITRAGE": "CRIAR DESK 12 (Weather / METAR Airport Arbitrage): Sim! Aproveitar os coletores METAR do PolyWeather para operar mercados diários de temperatura na Polymarket e Kalshi. Como os dados de aeroportos (METAR) saem a cada 20-30 minutos e os oráculos demoram horas para liquidar, há um 'lag de informação' onde a vitória já está consolidada com 99% de certeza e as cotas ainda negociam a 60¢-80¢.",
            "UPGRADE_DESK6_WITH_LP_REWARDS_TOOL": "UPGRADE DO DESK 6 (Integrar Liquidity Rewards do lihanyu81): Em vez de criar um desk novo, assimilar a fórmula exata de pontuação de recompensas LP da Polymarket no Desk 6 (Yield Harvester) para capturar o rendimento passivo diário em USDC.",
            "DO_NOT_ADD_ANY_DESK": "NÃO ADICIONAR NOVO DESK: Nosso portfólio de 10 desks já está no limite ótimo de diversificação de capital."
        }
    ),
    "code_architecture_assimilation": Choice(
        instructions="JEV, qual componente de código ou biblioteca dessas 10 ferramentas tem a aplicação técnica mais urgente e vantajosa para os nossos scripts Python?",
        criteria={
            "POLYWEATHER_METAR_INGESTION_MODULE": "MÓDULO DE INGESTÃO METAR (PolyWeather): Importar a lógica de 'metar_sources.py' e 'observation_source_gate.py' para gerar feeds diretos de temperatura e clima sem depender de APIs de terceiros.",
            "LP_REWARD_SCORING_FORMULA": "EQUAÇÃO DE LIQUIDITY REWARDS (polymarket_lp_tool): Incorporar o cálculo exato de spread elástico e score de recompensa no risk_gate.py.",
            "HARRIER_CROSS_MARKET_ARB_MATH": "MATEMÁTICA DE ARBITRAGEM CRUZADA (HarrierOnChain): Melhorar o Desk 7 (cross_arb.py) com os limiares de spread de HarrierOnChain.",
            "CLICKHOUSE_WHALE_PROFILING": "PIPELINE CLICKHOUSE (polybot): Criar banco de dados analítico para rastrear as maiores carteiras da Polymarket."
        }
    ),
    "overall_post_verdict": Choice(
        instructions="JEV, qual o seu veredito geral sobre a publicação do @recogard? Trata-se de curadoria séria ou conteúdo inflado de Twitter?",
        criteria={
            "GENUINE_HIGH_VALUE_CURATION": "CURADORIA DE ALTÍSSIMO NÍVEL TÉCNICO: Diferente da maioria das postagens superficiais de redes sociais, esta lista reuniu códigos institucionais reais (datasets de universidades, backtesting em Nautilus, motores em Rust e ferramentas de inteligência climática de produção). É uma das melhores compilações quantitativas já feitas para Polymarket.",
            "MIXED_QUALITY_WITH_GEMS": "QUALIDADE MISTA: Alguns repositórios são projetos comerciais leves ou repackaging (como AutoPilot), mas há 3 ou 4 joias genuínas de altíssimo valor (Polymarket_data, PolyWeather e HarrierOnChain).",
            "MARKETING_HYPE_ONLY": "CONTEÚDO INFLADO: Apenas repositórios populares sem utilidade real para quem opera em produção."
        }
    )
}

print("=" * 80)
print(" [JEV SYSTEMONE] CONSULTANDO JEV: AUDITORIA DOS 10 REPOSITÓRIOS (@recogard)...")
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

output_file = "jev_recogard_10_repos_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Veredito do JEV gravado em '{output_file}'.")
