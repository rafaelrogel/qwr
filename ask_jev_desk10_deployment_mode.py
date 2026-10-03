# -*- coding: utf-8 -*-
"""
Consulta Institucional ao JEV (TypeSafe SystemOne):
Avaliar se o Desk 10 (Binance Microstructure & Toxic Flow Harvester)
deve ser lançado inicialmente em modo PAPER para calibração de latência e slippage da CLOB Polymarket,
ou se já possui edge suficiente para entrar direto em LIVE com dinheiro real.
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
PROPOSTA DE LANÇAMENTO: DESK 10 (BINANCE MICROSTRUCTURE & TOXIC FLOW HARVESTER)
====================================================================================================
Ativo: Polymarket BTC 5m (com expansão para ETH 5m)
Tese: Capturar desequilíbrios atípicos de agressão institucional (CVD Z-Score > 2.5 ou Whale Trades >= 5 BTC em < 3s)
na Binance Spot antes que formadores de mercado da Polymarket reajustem cotações (vantagem de latência de 2 a 8 segundos).

CONSIDERAÇÕES DE ENGENHARIA E INFRAESTRUTURA:
1. Execução na Polygon PoS: Latência de RPC, transações de Smart Wallet Poly1271, gas price dinâmico e slippage na CLOB.
2. Embora o edge matemático em dados históricos de 50 GB mostre 84.3% de acerto na convergência,
   o ambiente real de execução envolve 'latency race' contra formadores de mercado algorítmicos.
3. Prática institucional padrão: Executar 24-48 horas em PAPER MODE (Shadow Trading) com registro de preenchimento simulado
   para medir latência exata entre WebSocket e orderbook da Polymarket, slippage e fill rate real.
4. Alternativa agressiva: Iniciar diretamente em LIVE MODE com micropostas fixas de $1.00 USDC e circuit breaker de -$3.00.
====================================================================================================
"""

questions = {
    "deployment_mode_recommendation": Choice(
        instructions="JEV, o usuário perguntou: 'Desk 10 vamos iniciar em paper mode, a não ser que o JEV prefira iniciar logo em live mode. O que você diz?'. Qual é a sua recomendação técnica e por que?",
        criteria={
            "START_IN_PAPER_MODE": "Recomenda PAPER MODE: Mesmo com edge matemático comprovado de 84.3%, uma estratégia de microestrutura e fluxo tóxico depende criticamente da latência de execução no book da Polymarket. Recomenda-se iniciar em PAPER MODE por 24-48h para calibrar o tempo de resposta do WebSocket e validar a liquidez das cotas antes de arriscar capital real.",
            "START_IN_LIVE_MODE": "Recomenda LIVE MODE DIRETO: O edge de fluxo institucional é tão assimétrico e o stake é tão conservador ($1.00 com circuit breaker) que é preferível testar imediatamente com dinheiro real na blockchain para capturar lucros desde o primeiro trade.",
            "DO_NOT_LAUNCH": "Recomenda NÃO lançar a estratégia."
        }
    )
}

print("=" * 80)
print(" [JEV CONSULTATION] CONSULTANDO IA JEV SOBRE MODO DE EXECUÇÃO DO DESK 10...")
print("=" * 80)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

ans = resp.answers["deployment_mode_recommendation"]

print(f"\n>>> VEREDITO JEV RECEBIDO EM {elapsed:.2f}s <<<\n")
print(f"Decisão: {ans.choice}")
print(f"Confiança: {ans.confidence * 100:.1f}%")
print(f"Probabilidades:")
for opt, p in ans.probabilities.items():
    print(f"  - {opt}: {p:.1%}")

result = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "decision": ans.choice,
    "confidence": ans.confidence,
    "probabilities": ans.probabilities
}

with open("jev_desk10_deployment_verdict.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)

print("\n[SUCESSO] Parecer do JEV gravado em 'jev_desk10_deployment_verdict.json'.")
