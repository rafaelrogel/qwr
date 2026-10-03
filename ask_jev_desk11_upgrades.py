# -*- coding: utf-8 -*-
"""
CONSULTA INSTITUCIONAL AO JEV (TypeSafe SystemOne):
Avaliação e Auditoria Matemática de 3 Propostas de Atualização para a Desk 11
(Kalshi S&P 500 15m Momentum & Sweeper - KXINX15M / KXINXU):

1. Filtro de Compressão de Volatilidade (Chop Shield / Travis Edge 2):
   - Veto de entrada se a amplitude (range) dos últimos 15 minutos for < 3.5 pontos.
2. Escudo de Abertura de Wall Street (9:30 - 10:00 AM ET):
   - Elevação do Delta mínimo de 4.0 pts para 6.0 pts nos primeiros 30 min de RTH para proteger contra o rebalanceamento de Gamma dos dealers.
3. Expansão de Séries Kalshi (Fallback Hierarchy):
   - Permitir fallback de KXINX15M para KXINXHUD (Horário) e KXINXDUD (Diário 16h EDT) quando 15m não tiver mercado ativo.
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
DOSSIÊ QUANTITATIVO: PROPOSTA DE ATUALIZAÇÃO DA DESK 11 (KALSHI S&P 500 15M)
Data/Hora: 2026-09-28 15:45 UTC
Contexto: Desdobramento do debate quantitativo sobre microestrutura de 0DTE/S&P 500 e dados Databento CME ES.
====================================================================================================

ESTRUTURA ATUAL DA DESK 11 (DESENVOLVIDA COM CALIBRAÇÃO DATABENTO CME ES):
- Ativo: S&P 500 Index (^GSPC / Globex ES)
- Horizonte Primário: Contratos de 15 minutos na Kalshi (KXINX15M).
- Janela de Entrada Primária (450s - 660s / 7m30s a 11m00s):
  * Exige Delta |Spot - Strike| >= 4.0 pontos em RTH (e 8.0 pontos fora de RTH).
  * Preço de cota aceitável: $0.20 a $0.65.
- Janela Sweeper de Alta Certeza (780s - 830s / 13m00s a 13m50s):
  * Exige Delta >= 4.0 pontos persistente.
  * Preço de cota até $0.94 (varredura com histórico CME certificado de 98.87% WR).
- Gestão de Saída:
  * SirMartingale Take-Profit antecipado a 88¢.
  * Saída por liquidação terminal no fechamento dos 15 minutos.
  * Não utiliza stop no preço de entrada (evitando o theta chop).

AS 3 PROPOSTAS DE ATUALIZAÇÃO EM AVALIAÇÃO:

PROPOSTA 1: FILTRO DE COMPRESSÃO DE VOLATILIDADE (CHOP SHIELD / TRAVIS EDGE 2)
- Conceito: Em dias ou janelas de compressão extrema do S&P 500 (ex: range de 15m < 3.5 pontos),
  um Delta de 4.0 pontos pode ser um falso rompimento (*head-fake*) que reverte rapidamente para a média.
- Mecanismo: Calcular a amplitude (High - Low) do S&P 500 na vela de 15m. Se a amplitude for inferior a 3.5 pontos,
  o robô veta entradas primárias e aguarda expansão de volatilidade real.
- Dilemma: Esse filtro aumenta a taxa de acerto ou corta oportunidades válidas em excesso?

PROPOSTA 2: ESCUDO DE ABERTURA DE WALL STREET (9:30 - 10:00 AM ET / 13:30 - 14:00 UTC)
- Conceito: Os primeiros 30 minutos do pregão regular da NYSE concentram a maior volatilidade bidirecional
  e rebalanceamento agressivo de Gamma dos formadores de mercado (dealers) e traders de 0DTE.
- Mecanismo: Nos primeiros 30 minutos de RTH, elevar o Delta mínimo requerido de 4.0 pontos para 6.0 pontos
  (ou adiar entradas para os 600s/10m da vela).
- Dilemma: É estatisticamente prudente exigir maior margem de segurança no 'open', ou o Delta de 4.0 pts já é suficiente?

PROPOSTA 3: EXPANSÃO DE SÉRIES DA KALSHI (FALLBACK HIERARCHY)
- Conceito: Na Kalshi, os mercados da série 'KXINX15M' (15 minutos) nem sempre são listados com antecedência contínua,
  mas a Kalshi mantém ativos 'KXINXHUD' (Hourly Up/Down) e 'KXINXDUD' (Daily Up/Down com fechamento às 16h EDT).
- Mecanismo Proposto: Se a série KXINX15M não tiver mercado aberto, permitir que o bot busque contratos em KXINXHUD (Horário)
  ou KXINXDUD (Diário), mantendo a lógica de Delta em relação ao Strike daquele contrato.
- Dilemma de Engenharia: Operar um contrato diário (KXINXDUD) com lógica de momentum intradiário de 15 minutos é válido,
  ou cria um 'horizon mismatch' (descasamento temporal) perigoso com risco de reversão ao longo de várias horas?
====================================================================================================
"""

questions = {
    "proposal_1_volatility_filter_verdict": Choice(
        instructions="JEV, avalie a Proposta 1 (Filtro de Compressão de Volatilidade / Chop Shield com range mínimo de 15m >= 3.5 pontos). Qual é o veredito matemático?",
        criteria={
            "APPROVE_VOLATILITY_FILTER": "APROVA O FILTRO: Exigir amplitude mínima de 3.5 pontos em 15m é altamente eficaz. Evita armadilhas de falso rompimento em mercados parados (chop) e alinha o bot com regimes de volatilidade real, preservando capital.",
            "REJECT_TOO_RESTRICTIVE": "REJEITA: Um filtro de amplitude de 3.5 pontos é desnecessário porque a exigência de Delta >= 4.0 pts já garante por si só que o preço se deslocou 4 pontos do strike.",
            "MODIFY_TO_ATR": "MODIFICAR: Em vez de range da vela atual, usar ATR de 5 períodos."
        }
    ),
    "proposal_2_rth_open_shield_verdict": Choice(
        instructions="JEV, avalie a Proposta 2 (Escudo de Abertura de Wall Street: exigir Delta >= 6.0 pontos nos primeiros 30 minutos do pregão regular, 9:30-10:00 AM ET). Qual é a recomendação?",
        criteria={
            "APPROVE_RTH_OPEN_SHIELD": "APROVA O ESCUDO DE ABERTURA: Aberturas de Wall Street têm picos violentos de Gamma e liquidez bidirecional. Exigir Delta >= 6.0 pts entre 9:30 e 10:00 ET é uma proteção institucional excelente contra whipsaws matinais.",
            "REJECT_KEEP_UNIFORM_4_POINTS": "REJEITA: O Delta de 4.0 pontos calibrado pelo Databento já possui 95.3% de win rate e não deve ser aumentado no open.",
            "DELAY_ENTRY_TO_MINUTE_12": "MODIFICAR: Não alterar o Delta, apenas adiar a entrada para o minuto 12:00 (720s) na primeira meia hora."
        }
    ),
    "proposal_3_kalshi_series_hierarchy_verdict": Choice(
        instructions="JEV, avalie a Proposta 3 (Permitir fallback de KXINX15M para KXINXHUD Horário e KXINXDUD Diário quando a série de 15m estiver vazia). Como devemos tratar essa hierarquia?",
        criteria={
            "RESTRICT_TO_INTRADAY_HOURLY_ONLY": "APROVAR COM RESTRIÇÃO (Apenas 15M e Horário HUD): Permitir fallback apenas para KXINXHUD (Horário). REJEITAR categoricamente o fallback para contratos diários (KXINXDUD), pois aplicar momentum de 15m em um contrato que vence horas depois gera descasamento de horizonte temporal (horizon mismatch) e risco severo de reversão.",
            "APPROVE_FULL_FALLBACK": "APROVAR TUDO: Permitir fallback para Horário e Diário sem restrições.",
            "STRICT_15M_ONLY_NO_FALLBACK": "REJEITAR TODO FALLBACK: A Desk 11 deve operar estritamente a série de 15 minutos (KXINX15M) e ficar em espera se ela não estiver listada."
        }
    )
}

print("=" * 80)
print(" [JEV CONSULTATION] CONSULTANDO JEV SOBRE AS 3 ATUALIZAÇÕES DA DESK 11...")
print("=" * 80)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n>>> PARECER OFICIAL DO JEV RECEBIDO EM {elapsed:.2f}s <<<\n")

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

output_file = "jev_desk11_upgrades_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Veredito do JEV gravado em '{output_file}'.")
