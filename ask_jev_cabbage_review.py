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
load_dotenv(r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot\.env")
from typesafe_sdk import TypeSafeClient, Choice, Score

key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
client = TypeSafeClient(api_key=key)

dossier = """
================================================================================
DOSSIÊ QUANTITATIVO: AUDITORIA DO REPOSITÓRIO 'sopersone/cabbage-trading-machine'
URL: https://github.com/sopersone/cabbage-trading-machine
DATA DO COMMIT: 24-29 de Setembro de 2026

1. ANATOMIA E ORIGEM DO CÓDIGO:
- O repositório NÃO é um bot proprietário original desenvolvido do zero.
- Ele é uma cópia integral do framework open-source 'investing-algorithm-framework' v9.0.0a18 (desenvolvido por coding-kitties / Finterion, licença Apache-2.0, ~839.000 linhas), empacotado com um wrapper CLI fino chamado 'cabbage' de apenas 4 arquivos (226 linhas de código no total):
  * `config.py` (53 linhas): Carrega variáveis de ambiente, valida mercado CCXT, par spot BTC/EUR, ticket de 50 EUR e stop de 5%.
  * `strategy.py` (53 linhas): Subclasse de `RSIEMACrossoverStrategy` (importada diretamente de `examples/simple_app.py` do framework original), operando velas de 2 horas. Exclui a vela aberta/incompleta.
  * `application.py` (35 linhas): Instancia o framework, configura SQLite local, modo paper trading ou live trading CCXT.
  * `__main__.py` (85 linhas): Subcomandos CLI: `doctor` (inspeção de credenciais/ticker público), `backtest` (execução do fixture histórico), `paper` (paper trading contínuo ou 1 iteração) e `live` (envio de ordens reais via CCXT).

2. DISCLOSURE E LIMITAÇÕES ADMITIDAS PELO DESENVOLVEDOR NO README / VALIDATION.md:
- O desenvolvedor (`sopersone`) registrou formalmente que o bot foi encomendado sob narrativas promocionais de "tracking de carteiras smart money", "inferência Jev", "80% de win rate" e "DEX de memecoins na Robinhood Chain".
- Porém, o desenvolvedor declara expressamente no README:
  "It does not use Jev or score smart-money wallets. No calibrated 80% model probability is invented. Still absent from the supplied upstream: Robinhood Chain RPC/DEX wallet scanner and signing/execution adapter; Jev inference API implementation; The promotional smart-wallet strategy and independently verified trade history."
- No arquivo `VALIDATION.md`, o backtest padrão fornecido sobre velas de 2h de BTC/EUR (10 a 20 de Junho de 2024) gerou **ZERO trades** (nenhum sinal disparado no intervalo).

3. RECURSOS DO FRAMEWORK SUBJACENTE ('investing-algorithm-framework' 9.0.0a18):
- Motor de Backtesting duplo:
  * Vetorizado com Polars (ultra-rápido para varredura de parâmetros e universos).
  * Orientado a eventos (event-driven bar-by-bar com fills simulados, custos e deslizamento).
- Formato OBTF (Open Backtest Format) em bundles `.obtf` portáteis com indexação SQLite para comparar 10.000+ testes.
- Monte Carlo / Permutation Testing para avaliar significância estatística contra random walk.
- Confluence Cards (regras declarativas de evidência primária/secundária com pontuação e vetos).
- Declarative Risk Rules (Stop Loss, Take Profit, Trailing, Exposure limits, Cooldowns).
- Relatórios HTML Auto-Contidos com dashboard interativo (dark/light mode, gráficos de Equity Curve com área, Drawdown, Ranking comparativo de estratégias por Sharpe/CAGR/MaxDD, Heatmap mensal de retornos).
- Servidor MCP embutido para permitir que LLMs/agentes consultem backtests, comparem estratégias e extraiam métricas.

4. COMPARAÇÃO COM O NOSSO AGY TRADING SYSTEM:
- AGY: 12 desks focados em microestrutura de alta frequência em mercados preditivos binários (Polymarket 5m e Kalshi 15m). Resolução determinística $0.00 ou $1.00, Order Book Imbalance (OBI), microprice weighting, drift em tempo real da Binance e Chainlink, deadbands dinâmicos, latência < 0.005ms, auditoria formal com JEV SystemOne, SirMartingale TP e Bonereaper Hedge.
- CABBAGE: Trading direcional spot de swing/position em exchanges tradicionais (Bitvavo, Binance, Kraken via CCXT), velas lentas de 2 horas, indicadores defasados clássicos (RSI 14 + EMA 12/26), stop loss fixo de 5%.
================================================================================
"""

questions = {
    "cabbage_bot_overall_verdict": Choice(
        instructions="Qual é a avaliação do JEV sobre o bot 'CABBAGE' em si (o repositório sopersone/cabbage-trading-machine)? Ele é um bot de trading avançado e lucrativo, ou é um wrapper básico sobre um framework open-source?",
        criteria={
            "thin_wrapper_over_framework": "Wrapper Fino e Estratégia Trivial: O bot CABBAGE em si consiste apenas em 226 linhas de código que encapsulam um exemplo didático de RSI/EMA de 2 horas. Não possui alpha proprietário, não possui modelo de ML, não possui integração com carteiras inteligentes e não gerou nenhum trade no período de validação fornecido. Como bot autônomo de alpha, é rudimentar.",
            "advanced_algorithmic_bot": "Bot Algorítmico Avançado: Possui inteligência preditiva sofisticada e estratégias de ponta.",
            "unusable_broken_code": "Código Quebrado e Inutilizável: Não funciona de forma alguma."
        }
    ),
    "upstream_framework_value": Choice(
        instructions="Embora o bot CABBAGE seja apenas um wrapper trivial de RSI/EMA, o framework subjacente ('investing-algorithm-framework' 9.0.0a18) possui algum valor arquitetural real para quant trading?",
        criteria={
            "valuable_infrastructure_for_traditional_markets": "Infraestrutura Robusta para Mercados Contínuos Tradicionais: O framework subjacente é muito bem estruturado para o ciclo quant clássico (Polars vector backtest, event-driven, OBTF bundles, SQLite ranking, Monte Carlo, Confluence Cards e dashboard HTML self-contained com servidor MCP embutido).",
            "completely_useless": "Totalmente Inútil: Não agrega nada a nenhuma área de finanças quantitativas.",
            "superior_to_agy_for_prediction_markets": "Superior ao AGY: Deveria substituir o motor dos 12 desks binários da Polymarket/Kalshi."
        }
    ),
    "can_we_port_features_to_agy": Choice(
        instructions="Podemos extrair ou adaptar componentes específicos deste projeto para melhorar o AGY Trading System?",
        criteria={
            "port_dashboard_and_confluence_concept": "Aproveitar o Design do Dashboard e Conceito de Confluence/MCP: O motor de microestrutura do AGY não deve ser trocado (nossos desks de 5m/15m exigem latência sub-milisegundo e lógica binária $0/$1 que o CCXT/IAF não suporta). Porém, podemos incorporar: 1) O design do Dashboard HTML/CSS (KPIs visualmente limpos, curvas de equity comparativas, heatmap mensal); 2) O conceito de Servidor MCP para o nosso Dashboard para consulta de métricas por agentes; 3) A estrutura de Confluence Scoring Cards para formalizar nossos múltiplos filtros.",
            "adopt_cabbage_rsi_ema_strategy": "Adotar a Estratégia RSI/EMA: Substituir nossas estratégias de microestrutura por cruzamento de médias e RSI.",
            "adopt_entire_framework": "Migrar Tudo para o IAF: Reescrever todos os 12 desks dentro do Investing Algorithm Framework.",
            "reject_completely_zero_takeaway": "Rejeição Total: Não olhar nem aproveitar absolutamente nada."
        }
    ),
    "should_we_create_new_desk": Choice(
        instructions="O usuário pergunta se devemos criar alguma nova 'desk' para testar com base no CABBAGE. O que o JEV recomenda?",
        criteria={
            "strictly_do_not_create_cabbage_desk": "Não Criar Desk de Swing Spot Tradicional (Recomendado): Rejeitar categoricamente criar um desk de swing spot (BTC/EUR 2h RSI/EMA) com dinheiro real ou alocar capital nisso. Nossa vantagem competitiva matemática e taxa de acerto comprovada residem em opções binárias determinísticas (Polymarket e Kalshi). Um desk de 2h de RSI em spot cripto apenas dispersaria capital e traria risco de mercado aberto sem edge comprovado.",
            "create_cabbage_spot_paper_desk": "Criar Desk 13 Spot Paper: Rodar o CABBAGE em paper trading com Bitvavo BTC/EUR apenas para testes de longo prazo sem dinheiro real.",
            "create_cabbage_live_desk": "Criar Desk 13 Live com Dinheiro Real: Alocar banca real no CABBAGE."
        }
    ),
    "backtesting_and_paper_testing_evaluation": Choice(
        instructions="Como o JEV avalia o sistema de backtesting e paper testing do Investing Algorithm Framework presente no repositório?",
        criteria={
            "high_quality_dual_engine": "Arquitetura de Alta Qualidade para Mercados Contínuos: O framework se destaca pelo motor duplo (Vetorizado em Polars para velocidade extrema e Orientado a Eventos para fidelidade microestrutural com slippage/taxas), armazenamento OBTF e paper trading local via CCXT. É uma excelente referência de engenharia de software para testes contínuos.",
            "flawed_and_misleading": "Falho e Enganoso: Possui look-ahead bias e não simula execução de mercado.",
            "standard_generic": "Padrão e Genérico: Idêntico a backtrader ou zipline sem diferenciais."
        }
    ),
    "overall_cabbage_scientific_score": Score(
        instructions="Dê uma nota de 1.0 a 5.0 para o bot CABBAGE em si (o wrapper com a estratégia proposta).",
        criteria=[
            "1.0 - Estratégia genérica e trivial de livro-texto (RSI/EMA 2h), sem alpha comprovado, sem modelo ML e com zero trades no teste.",
            "2.0 - Código limpo e estruturado, mas puramente derivativo e sem edge estatístico.",
            "3.0 - Estratégia razoável para mercados em forte tendência.",
            "4.0 - Bot quantitativo avançado com edge comprovado.",
            "5.0 - Estado da arte institucional."
        ]
    )
}

print("=" * 80)
print("CONSULTANDO JEV SYSTEMONE SOBRE O REPOSITÓRIO CABBAGE-TRADING-MACHINE...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_cabbage_verdict": {
        "choice": res.answers["cabbage_bot_overall_verdict"].choice,
        "confidence": res.answers["cabbage_bot_overall_verdict"].confidence,
        "probs": res.answers["cabbage_bot_overall_verdict"].probabilities
    },
    "q2_upstream_framework_value": {
        "choice": res.answers["upstream_framework_value"].choice,
        "confidence": res.answers["upstream_framework_value"].confidence,
        "probs": res.answers["upstream_framework_value"].probabilities
    },
    "q3_can_we_port_features": {
        "choice": res.answers["can_we_port_features_to_agy"].choice,
        "confidence": res.answers["can_we_port_features_to_agy"].confidence,
        "probs": res.answers["can_we_port_features_to_agy"].probabilities
    },
    "q4_should_we_create_new_desk": {
        "choice": res.answers["should_we_create_new_desk"].choice,
        "confidence": res.answers["should_we_create_new_desk"].confidence,
        "probs": res.answers["should_we_create_new_desk"].probabilities
    },
    "q5_backtesting_evaluation": {
        "choice": res.answers["backtesting_and_paper_testing_evaluation"].choice,
        "confidence": res.answers["backtesting_and_paper_testing_evaluation"].confidence,
        "probs": res.answers["backtesting_and_paper_testing_evaluation"].probabilities
    },
    "q6_scientific_score": {
        "score": res.answers["overall_cabbage_scientific_score"].score,
        "confidence": res.answers["overall_cabbage_scientific_score"].confidence
    }
}

output_path = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot\jev_cabbage_review_verdict.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
