# -*- coding: utf-8 -*-
"""
Bate-Bola Inteligente: Antigravity AI + Codex + JEV (TypeSafe SystemOne)
Auditoria e Validação do Plano de Engenharia Quantitativa:
1. Criação do Gate Único de Risco Pré-Trade (risk_gate.py)
2. Correção de Segurança no Desk 6 (stub live_executed e kill switch)
3. Reclassificação Rigorosa do Desk 7 (Basis Risk vs Arbitragem Pura)
4. Padronização Fail-Closed dos Modos no Dashboard e Bots
5. Persistência Atômica Universal para Todos os Desks
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

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
====================================================================================================
DOSSIÊ DE ENGENHARIA DE RISCO QUANTITATIVO: CODEX + ANTIGRAVITY + JEV
SISTEMA: AGY TRADING SYSTEM (9 DESKS MULTI-ASSET)
====================================================================================================

DIAGNÓSTICO CONJUNTO DOS PONTOS APONTADOS PELO CODEX:

1. DESK 6 (Yield Harvester 98¢):
   - Falha Crítica: Se DESK6_MODE=LIVE, marcava `live_executed=True` mas não continha a chamada real de execução `place_live_order`. Além disso, ignorava HALT/EMERGENCY_STOP.
   - Proposta de Solução: Travar Desk 6 estritamente em MODO PAPER, exigir verificação do RiskGate (HALT/EMERGENCY_STOP) e só permitir LIVE após integração auditada da CLOB V2.

2. DESK 7 (Cross-Market Macro Arbitrageur):
   - Falha Conceitual/Metodológica: Rotula oportunidades como "Arbitragem Pura" (Pure Arbitrage) baseado unicamente em palavras-chave e preços de midpoint/top-of-book, sem checar:
     a) Regras de liquidação dos oráculos (Polymarket UMA vs Kalshi CFTC - Basis Risk).
     b) Profundidade de liquidez (order book depth) em ambas as pernas.
     c) Execução atômica simultânea com slippage protection.
   - Proposta de Solução: Reclassificar no sistema e dashboard como "RADAR DE DIVERGÊNCIA MACRO" (Cross-Market Divergence Scanner), desabilitar a pretensão de "arbitragem livre de risco" até que haja execução atômica de duas pernas com validação de oráculo.

3. PADRÃO FAIL-CLOSED DE MODOS NO DASHBOARD:
   - Falha: O dashboard assumia "LIVE" como fallback caso a variável estivesse ausente no .env (`ENV_CFG.get("EXECUTION_MODE", "LIVE")`), enquanto executores usavam "PAPER".
   - Proposta de Solução: Implementar regra fail-closed universal: NENHUM desk assume LIVE por padrão. Se a variável não for explicitamente "LIVE", o padrão é SEMPRE "PAPER".

4. PERSISTÊNCIA ATÔMICA UNIVERSAL (JOURNALS E ESTADOS):
   - Falha: Somente o Desk 1 (BTC 5m) utilizava gravação atômica (`_atomic_json_write` com arquivo temporário e `os.replace`). Os Desks 2 a 9 gravavam diretamente com `open('w')`, arriscando corrupção do JSON em encerramentos forçados ou concorrência com o dashboard.
   - Proposta de Solução: Migrar todos os desks para um utilitário centralizado `atomic_write_json(filepath, data)` com `flush()` e `fsync()`.

5. ARQUITETURA DE GATE CENTRALIZADO (risk_gate.py):
   - Proposta: Criar o módulo unificado `risk_gate.py` contendo:
     * `check_pre_trade_gate(desk_id, side, stake, spot, oracle_ts)`:
       1. Validação de Kill Switch (HALT / EMERGENCY_STOP).
       2. Validação Fail-Closed do modo LIVE.
       3. Validação de frescor de dados (stale feed > 15s).
       4. Limite de exposição global e drawdown diário.
       5. Saldo mínimo remanescente de segurança.
"""

questions = {
    "risk_gate_architecture_verdict": Choice(
        instructions="Evaluate the creation of the centralized 'risk_gate.py' module to enforce fail-closed pre-trade checks across all desks.",
        criteria={
            "essential_institutional_hardening": "Essential Institutional Hardening: Centralizing the pre-trade gate, kill-switch check, fail-closed mode defaults, and atomic JSON persistence eliminates systemic divergence and protects capital across all 9 desks.",
            "unnecessary_overhead": "Unnecessary Overhead: Independent checks inside each trader file are sufficient.",
            "partial_solution": "Partial Solution: Centralization is good, but without hardware-level latency protection it offers marginal benefit."
        }
    ),
    "desk7_reclassification_impact": Choice(
        instructions="Evaluate reclassifying Desk 7 from 'Pure Arbitrage' to 'Cross-Market Macro Divergence Radar' to eliminate the false assumption of risk-free arbitrage without settlement equivalence.",
        criteria={
            "quantitatively_accurate_and_safe": "Quantitatively Accurate & Safe: Essential. Calling unverified cross-exchange spreads 'pure arbitrage' creates basis risk and false confidence. Reclassifying as Divergence Radar reflects reality and prevents accidental unhedged execution.",
            "keep_calling_it_pure_arb": "Keep Calling Pure Arb: The current keyword and date matching is enough to consider it pure arbitrage."
        }
    ),
    "fail_closed_mode_standardization": Choice(
        instructions="Evaluate strictly forcing default='PAPER' everywhere if 'LIVE' is not explicitly declared in .env.",
        criteria={
            "mandatory_fail_closed": "Mandatory Fail-Closed: High-reliability financial engineering rule #1. Any missing configuration or syntax fault must default to zero-risk simulation.",
            "live_default_acceptable": "Live Default Acceptable: Defaulting to LIVE is fine if the user intends to trade."
        }
    ),
    "implementation_confidence_score": Score(
        instructions="Score from 1.0 to 5.0 the systemic robustness of executing this comprehensive 5-point plan.",
        criteria=[
            "1.0 - Fragile, introduces regressions",
            "2.0 - Minor improvement",
            "3.0 - Adequate standard cleanup",
            "4.0 - Major professional risk upgrade",
            "5.0 - Institutional hedge-fund grade risk framework"
        ]
    )
}

print("=" * 90)
print("  🤖 REALIZANDO BATE-BOLA QUANTITATIVO COM A IA JEV (TYPESAFE SYSTEMONE)...")
print("=" * 90)

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

q1 = response.answers["risk_gate_architecture_verdict"]
q2 = response.answers["desk7_reclassification_impact"]
q3 = response.answers["fail_closed_mode_standardization"]
q4 = response.answers["implementation_confidence_score"]

out = {
    "timestamp": time.time(),
    "elapsed": elapsed,
    "q1_risk_gate": {"choice": q1.choice, "confidence": q1.confidence, "probabilities": q1.probabilities},
    "q2_desk7_reclass": {"choice": q2.choice, "confidence": q2.confidence, "probabilities": q2.probabilities},
    "q3_fail_closed": {"choice": q3.choice, "confidence": q3.confidence, "probabilities": q3.probabilities},
    "q4_confidence_score": {"score": q4.score, "confidence": q4.confidence}
}

with open("jev_codex_debate_verdict.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("=" * 90)
print(f"1. Centralização do Gate de Risco (risk_gate.py): {q1.choice.upper()} ({q1.confidence:.1%} de confiança)")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Reclassificação do Desk 7 (Divergência vs Arbitragem Pura): {q2.choice.upper()} ({q2.confidence:.1%} de confiança)")
for k, v in q2.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n3. Padronização Fail-Closed (Default=PAPER): {q3.choice.upper()} ({q3.confidence:.1%} de confiança)")
for k, v in q3.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n4. Nota de Robustez Sistêmica da Implementação (1-5): {q4.score:.2f} / 5.00 ({q4.confidence:.1%} de confiança)")
print("=" * 90)
