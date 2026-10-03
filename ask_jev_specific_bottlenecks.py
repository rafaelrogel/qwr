# -*- coding: utf-8 -*-
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

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
ANÁLISE DE GARGALOS E RISCOS OPERACIONAIS EM CONCORRÊNCIA:
Temos atualmente 9 processos de trading rodando em simultâneo:
1. live_trader_5m.py (BTC 5m na Polymarket - Live real money) - Polling Chainlink on-chain / Binance a cada 1s.
2. sol_trader_5m.py (SOL 5m na Polymarket - Paper/Live) - Polling Binance / CLOB a cada 1s.
3. kalshi_trader_15m.py (BTC 15m Kalshi - Paper com Auth RSA-PSS real) - Polling Kalshi API a cada 2s.
4. kalshi_natgas_daemon.py (NatGas EIA Kalshi) - Espera passiva semanal.
5. kalshi_natgas_trader_15m.py (NatGas 15m Kalshi) - Polling Kalshi API a cada 3s.
6. desk6_yield_harvester.py (Yield 98c) - Varredura periódica a cada 30 minutos.
7. desk7_cross_arb.py (Cross-Arb Poly/Kalshi) - Varredura periódica a cada 60s (faz requisições em lote de 3900 mercados poly e 200 kalshi).
8. eth_trader_5m.py (ETH 5m na Polymarket - Paper) - Polling Pyth / Binance a cada 1s.
9. kalshi_gold_trader_15m.py (Gold 15m Kalshi - Paper) - Polling Kalshi API a cada 3s.
10. dashboard_server.py - Servidor HTTP que a cada 2s faz leituras nos arquivos JSON de estado e polling de preços Binance.

POTENCIAIS PONTOS DE ATENÇÃO:
A. Concorrência de arquivos JSON (leitura/escrita simultânea sem file locking explícito entre robôs e dashboard).
B. Rate limits de API pública da Binance ou Kalshi se múltiplos scripts fizerem chamadas não sincronizadas.
C. Consumo de CPU/memória no Windows com 10 janelas cmd/processos Python.
D. No Dashboard (dashboard.html):
   - O P&L da Polymarket está em texto pequeno abaixo do saldo, e o Kalshi não tem P&L visível no card principal.
   - A tabela de negociações no modal corta as colunas com `.slice(0, 12)`, omitindo 'cycle_pnl', 'payout' e 'balance'.
   - O modal do Desk 1 não exibe o Win Rate e Total de Trades que estão em `pnl_summary`.
"""

questions = {
    "primary_concurrency_risk": Choice(
        instructions="What is the primary risk factor explaining the 2.95/5 score in running all 9 desks concurrently?",
        criteria={
            "api_rate_limits_and_ip_throttling": "API Rate Limits: Multiple independent processes polling Binance or Kalshi every 1-3s without a shared cache may hit HTTP 429 rate limits or IP bans.",
            "unlocked_json_race_conditions": "JSON File Race Conditions: Background feeds worker in dashboard_server.py reading JSON state files while trading bots are rewriting them, causing transient JSONDecodeError.",
            "scanner_resource_spikes": "Scanner Spikes: Desk 7 Cross-Arb fetching 4,000 markets every 60s causes network and CPU spikes that can introduce jitter into 5m execution loops.",
            "acceptable_distributed_load": "Acceptable: The load is manageable, but needs shared cache and staggered timers."
        }
    ),
    "recommended_dashboard_enhancements": Choice(
        instructions="What are the essential UX refinements needed for dashboard.html to achieve the user's requirement of 'clean, bonito, fácil de ler, com números granditos'?",
        criteria={
            "hero_pnl_badges_and_full_table": "Hero P&L Badges & Full Tables: Make P&L prominent with large typography and dedicated badges (USDC and USD) on both Polymarket and Kalshi hero cards; remove the slice(0, 12) limit so all columns (especially PnL, Payout, and Balance) are visible; and enrich modal metrics with Win Rate and cumulative statistics.",
            "keep_as_is": "Keep As Is: The current layout is sufficient as it already shows basic balances and a modal table."
        }
    ),
    "recommended_operational_action": Choice(
        instructions="What is the recommended next operational step for the user and assistant?",
        criteria={
            "polish_dashboard_and_verify_stability": "Polish Dashboard & Verify Stability: Upgrade dashboard.html to show prominent hero P&L badges and uncapped trade tables, while ensuring trading loops have retry-safety and staggered polling.",
            "halt_background_desks": "Halt Desks: Immediately shutdown all paper desks and leave only BTC 5m live."
        }
    )
}

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

q1 = response.answers["primary_concurrency_risk"]
q2 = response.answers["recommended_dashboard_enhancements"]
q3 = response.answers["recommended_operational_action"]

print("=" * 90)
print(f"1. Principal Risco de Concorrência: {q1.choice.upper()} ({q1.confidence:.1%})")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Refinamentos Recomendados no Dashboard: {q2.choice.upper()} ({q2.confidence:.1%})")
for k, v in q2.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n3. Ação Operacional Recomendada: {q3.choice.upper()} ({q3.confidence:.1%})")
for k, v in q3.probabilities.items():
    print(f"   - {k}: {v:.1%}")
print("=" * 90)
