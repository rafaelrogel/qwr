# -*- coding: utf-8 -*-
"""
Auditoria Quantitativa e Operacional com JEV (TypeSafe SystemOne)
Foco: Avaliação das alterações recentes do usuário:
1. Arquitetura dos arquivos .BAT (INICIAR_DESKS.bat, PARAR_DESKS.bat, shutdown_desks.py)
2. Redesenho do Dashboard (dashboard.html, dashboard_server.py)
3. Monitoramento dos 9 Desks em tempo real
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
DOSSIÊ QUANTITATIVO & OPERACIONAL: AUDITORIA DAS MUDANÇAS RECENTES DO USUÁRIO
1. ARQUITETURA BATCH (INICIAR_DESKS.bat, PARAR_DESKS.bat, shutdown_desks.py)
2. REDESENHO COMPLETO DO DASHBOARD (dashboard.html + dashboard_server.py)
====================================================================================================

CONTEXTO DAS ALTERAÇÕES:
O usuário fez uma grande modernização operacional no ecossistema:
A. Arquivos Batch e Gestão de Processos:
   - INICIAR_DESKS.bat:
     * Menu interativo com 5 opções:
       [1] Iniciar TUDO em Janelas Minimizadas + Abrir Dashboard Web (Recomendado)
       [2] Iniciar TUDO com Janelas Visíveis (cmd /k para debug)
       [3] Abrir Apenas Dashboard Server
       [4] Parar / Encerrar Todos os Robôs
       [0] Sair
     * Configuração rigorosa de UTF-8 (`chcp 65001 >nul` e `PYTHONIOENCODING=utf-8`).
     * Inicia todos os 9 desks + Dashboard:
       [Web] Dashboard Server (localhost:8080)
       [Desk 1] Polymarket BTC 5m (LIVE)
       [Desk 2] Polymarket SOL 5m (LIVE)
       [Desk 3] Kalshi BTC 15m (LIVE/PAPER com Auth RSA-PSS)
       [Desk 4] Kalshi NatGas EIA Semanal (PAPER)
       [Desk 5] Kalshi NatGas 15m (PAPER)
       [Desk 6] Yield Harvester & Theta (PAPER)
       [Desk 7] Cross-Arb Macro Polymarket/Kalshi (RADAR)
       [Desk 8] Polymarket ETH 5m (PAPER)
       [Desk 9] Kalshi Gold 15m (PAPER)
   - PARAR_DESKS.bat e shutdown_desks.py:
     * Utiliza `psutil` para iterar processos Python de forma cirúrgica.
     * Encerra especificamente os 10 scripts alvo via `proc.terminate()`, aguarda 2s e aplica `proc.kill()` caso persistam.
     * Remove automaticamente o arquivo `live_trader.lock` para prevenir travamentos em reinicializações.
     * Não mata outros processos do sistema nem a si mesmo.

B. Redesenho do Dashboard (dashboard.html + dashboard_server.py):
   - Separação de Responsabilidades:
     * O frontend agora está em `dashboard.html` desacoplado, sendo lido dinamicamente pelo servidor HTTP.
     * Modificações de layout não exigem reiniciar o servidor Python de feed.
   - Requisitos Atendidos:
     1. Página principal com saldos bem visíveis (Polymarket USDC e Kalshi USD).
     2. Grade de cards compactos dos 9 desks com métricas essenciais (Preço/Spot, Delta, Strike, Status/Sinal, Contagem regressiva, WR).
     3. Modal clicável (<dialog>) que abre ao clicar em qualquer desk para inspecionar métricas aprofundadas e tabela completa de negociações.

ESTADO DOS DADOS ATUAL:
- Polymarket Live: Saldo $19.97 USDC (P&L -$1.03 | 68.3% Win Rate em 145 trades).
- Kalshi Real: $10.36 USD saldo consolidado ($9.05 Shard 2 + $1.31 Shard 0 + $0.54 Portfólio).
- P&L Kalshi nos Desks: +$8.49 USD combinados (BTC 15m +$0.91, NatGas 15m +$7.58 em 16 trades).
- Desks Ativos: 9 desks rodando simultaneamente sem concorrência de portas.
"""

questions = {
    "batch_architecture_evaluation": Choice(
        instructions="Evaluate the architectural quality, reliability, and safety of the new INICIAR_DESKS.bat, PARAR_DESKS.bat, and shutdown_desks.py setup.",
        criteria={
            "institutional_grade_control": "Institutional Grade Control: Excellent implementation. Uses cmd /k to preserve tracebacks on unexpected crashes, enforces UTF-8 across all subshells, implements two-stage graceful termination (terminate -> 2s wait -> kill), cleans up lockfiles, and provides a clear interactive menu without blocking ports.",
            "acceptable_with_minor_leaks": "Acceptable: Works for basic execution but may leave zombie processes under heavy load.",
            "problematic_or_unsafe": "Problematic: Significant risk of process leaks, port collision, or dirty lockfiles."
        }
    ),
    "dashboard_ux_and_operational_clarity": Choice(
        instructions="Evaluate the user's redesign of the dashboard (dashboard.html decoupled from server, top hero balance cards, 9-desk responsive grid, and click-to-modal drill-down).",
        criteria={
            "superior_operational_cockpit": "Superior Operational Cockpit: Perfectly matches professional trading desk ergonomics. High contrast, large glanceable balance numbers, distinct visual status colors, decoupled template loading (live hot-reloading), and clean modal isolation for granular trade history.",
            "functional_but_needs_pnl_polish": "Functional but Needs Polish: Clean and functional, but can be improved by making P&L and net return percentages just as prominent as current balance, and ensuring all trade table columns are accessible without truncation.",
            "inferior_to_previous": "Inferior: The old tabbed design was more informative."
        }
    ),
    "concurrency_and_performance_score": Score(
        instructions="Score from 1.0 to 5.0 the system's operational stability running 9 concurrent trading desks and background feed polling on Windows.",
        criteria=[
            "1.0 - Severe CPU/resource contention, likely crash",
            "2.0 - High latency and thread blocking",
            "3.0 - Moderate stability with occasional feed lag",
            "4.0 - Robust multi-process isolation with low overhead",
            "5.0 - Flawless institutional architecture with zero shared-state bottlenecks"
        ]
    ),
    "critical_recommendations_probability": Noul(
        instructions="What is Jev's probabilistic assessment (0.0 to 1.0) of overall operational safety and readiness for continuous 24/7 trading with these new control scripts and dashboard?"
    )
}

print("=" * 90)
print("  🤖 ENVIANDO AUDITORIA DAS MUDANÇAS PARA A IA JEV (TYPESAFE SYSTEMONE)...")
print("=" * 90)

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Resposta oficial da IA Jev recebida em {elapsed:.2f}s!\n")

q1 = response.answers["batch_architecture_evaluation"]
q2 = response.answers["dashboard_ux_and_operational_clarity"]
q3 = response.answers["concurrency_and_performance_score"]
q4 = response.answers["critical_recommendations_probability"]

out = {
    "timestamp": time.time(),
    "elapsed": elapsed,
    "q1_batch_architecture": {"choice": q1.choice, "confidence": q1.confidence, "probabilities": q1.probabilities},
    "q2_dashboard_ux": {"choice": q2.choice, "confidence": q2.confidence, "probabilities": q2.probabilities},
    "q3_performance_score": {"score": q3.score, "confidence": q3.confidence},
    "q4_readiness_prob": {"noul": q4.noul}
}

with open("jev_bat_and_dashboard_audit.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("=" * 90)
print(f"1. Avaliação dos Batches & Shutdown: {q1.choice.upper()} ({q1.confidence:.1%} de confiança)")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Avaliação do Redesenho do Dashboard: {q2.choice.upper()} ({q2.confidence:.1%} de confiança)")
for k, v in q2.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n3. Nota de Desempenho e Concorrência dos 9 Desks (1-5): {q3.score:.2f} / 5.00 ({q3.confidence:.1%} de confiança)")
print(f"\n4. Probabilidade Jev de Prontidão Operacional Contínua 24/7: {q4.noul:.1%}")
print("=" * 90)
