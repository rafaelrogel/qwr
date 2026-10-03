# -*- coding: utf-8 -*-
"""
CONSULTA AO CONSELHO DE INTELIGÊNCIAS JEV (TYPESAFE SYSTEMONE)
Avaliação Forense dos 5 Candidatos Adicionais:
1. xrp-updown-5m (Polymarket)
2. doge-updown-5m (Polymarket)
3. KXETH15M (Kalshi)
4. KXWTI15M (Kalshi)
5. KXNDQ15M (Kalshi)
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

from typesafe_sdk import TypeSafeClient, Choice, Score

JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

client = TypeSafeClient()

dossier = """
====================================================================================================
DOSSIÊ FORENSE DO CONSELHO JEV: AVALIAÇÃO DE 5 CANDIDATOS ADICIONAIS
Data: 2026-09-26 (Sábado)
Contexto do Usuário:
O usuário perguntou:
"Da lista abaixo, quais podemos adicionar, quais valem a pena adicionar também?
Ou não valem a pena e ficamos apenas com ETH e Ouro mesmo?
1. xrp-updown-5m (Ripple 5m) -> Forte desequilíbrio no livro de ofertas.
2. doge-updown-5m (Dogecoin 5m).
3. KXETH15M (Ethereum 15m).
4. KXWTI15M (Petróleo WTI 15m).
5. KXNDQ15M (Nasdaq 100 15m)."

FATOS EMPÍRICOS E DADOS COLETADOS EM TEMPO REAL PELO SISTEMA:

1. POLYMARKET XRP 5M (xrp-updown-5m):
   - Backtest teórico spot (Binance): 95.8% WR, Profit Factor 19.63, EV +$0.776/trade ($1 stake).
   - REALIDADE DO LIVRO NA POLYMARKET:
     * Best Bid: $0.23 | Best Ask: $0.99
     * SPREAD REAL: $0.76 (76 CENTS em um contrato de $1.00!)
     * Volume: $0.00 | Liquidez rasa
     * O suposto "desequilíbrio no livro" é ilusório: formadores de mercado colocaram bids a 23¢ e asks a 99¢.
     * Pagar 99¢ como taker para ganhar $1.00 tem assimetria brutalmente negativa.

2. POLYMARKET DOGE 5M (doge-updown-5m):
   - Backtest teórico spot (Binance): 88.5% WR, Profit Factor 6.27.
   - REALIDADE DO LIVRO NA POLYMARKET:
     * Best Bid: $0.23 | Best Ask: $0.99
     * SPREAD REAL: $0.76 (76 CENTS!)
     * Volume: $0.00
     * Exatamente a mesma armadilha de liquidez e spread predatório de 76¢.

3. KALSHI ETHEREUM 15M (KXETH15M):
   - Backtest: 85.7% WR.
   - Status Kalshi: Mercado listado mas sem liquidez no momento (Bid $0.00 / Ask $0.00, Volume 0).
   - Conflito de Carteira: Já implementamos Desk 8 (ETH 5m na Polymarket), que tem book líquido e spread de 1¢ a 2¢. Adicionar ETH 15m na Kalshi dobra o risco no mesmo ativo em uma exchange com book vazio.

4. KALSHI PETRÓLEO WTI 15M (KXWTI15M):
   - Status Kalshi: MERCADO FECHADO / NÃO LISTADO aos fins de semana.
   - Liquidez: Opera apenas em horários de pregão de energia (NYMEX) e com baixa profundidade no varejo.

5. KALSHI NASDAQ 100 15M (KXNDQ15M):
   - Status Kalshi: MERCADO FECHADO aos fins de semana (Sábado/Domingo).
   - Ruído Intraday: Durante a semana, sofre alta intervenção de HFTs institucionais na abertura americana.
   - Parecer anterior do JEV: "pure intraday noise".

STATUS ATUAL DO SISTEMA:
- Desks Live: BTC 5m Live (Polymarket), SOL 5m Live (Polymarket), BTC 15m Live (Kalshi).
- Novos Desks Ativos em Paper: ETH 5m (Polymarket) + Ouro 15m (Kalshi KXGOLD15M).
- Desks Auxiliares: NatGas 15m (Paper), Yield Harvester 98¢ (Paper), Cross-Arb Radar.
====================================================================================================
"""

questions = {
    "strategic_action_verdict": Choice(
        instructions="Diante dos dados empíricos de spread de 76¢ no XRP/DOGE, falta de liquidez no ETH 15m Kalshi, e mercados fechados no fds para WTI/NDQ: Qual a ação recomendada?",
        criteria={
            "STICK_STRICTLY_TO_ETH_AND_GOLD": "Ficar estritamente com ETH 5m e Ouro 15m (além de BTC e SOL). Não adicionar nenhum dos 5 agora por risco de spread predatório, iliquidez ou mercados fechados.",
            "ADD_XRP_ONLY": "Adicionar apenas XRP 5m.",
            "ADD_ETH_15M_KALSHI_ONLY": "Adicionar apenas ETH 15m Kalshi.",
            "ADD_ALL_FIVE": "Adicionar todos os 5 candidatos."
        }
    ),
    "xrp_5m_verdict": Choice(
        instructions="Parecer do JEV sobre xrp-updown-5m com spread real de 76¢ (Bid 23¢ / Ask 99¢):",
        criteria={
            "REJECT_PREDATORY_SPREAD": "Rejeitado: O spread de 76¢ destrói qualquer expectativa matemática positiva para takers.",
            "STANDBY_IF_LIQUIDITY_IMPROVES": "Standby: Aguardar se a Polymarket injetar formadores de mercado com spread < 4¢.",
            "APPROVE_NOW": "Aprovar agora mesmo com spread de 76¢."
        }
    ),
    "doge_5m_verdict": Choice(
        instructions="Parecer do JEV sobre doge-updown-5m com spread de 76¢ e volume zero:",
        criteria={
            "REJECT_MEMECOIN_ILLIQUID": "Rejeitado: Memecoin ilíquida com spread predatório e ruído irracional.",
            "STANDBY": "Standby para monitoramento passivo.",
            "APPROVE_NOW": "Aprovar agora."
        }
    ),
    "kalshi_eth15m_verdict": Choice(
        instructions="Parecer do JEV sobre KXETH15M (Kalshi) já tendo o Desk ETH 5m na Polymarket:",
        criteria={
            "REJECT_REDUNDANT_AND_ILLIQUID": "Rejeitado: Redundante com o ETH 5m da Polymarket (que tem muito mais liquidez) e concentra risco excessivo em Ethereum.",
            "APPROVE_AS_COMPLEMENT": "Aprovar como complemento de 15 minutos.",
            "STANDBY": "Standby."
        }
    ),
    "kalshi_wti_ndq_verdict": Choice(
        instructions="Parecer do JEV sobre WTI 15m (Petróleo) e NDQ 15m (Nasdaq 100):",
        criteria={
            "REJECT_CLOSED_OR_NOISY": "Rejeitado: Ambos fecham no fim de semana, NDQ tem ruído tóxico de HFT e WTI tem liquidez irregular de varejo.",
            "APPROVE_FOR_WEEKDAYS": "Aprovar apenas para operar de segunda a sexta.",
            "APPROVE_IMMEDIATELY": "Aprovar imediatamente."
        }
    ),
    "portfolio_sufficiency_score": Score(
        instructions="De 1 a 5, qual a suficiência e excelência do portfólio atual (BTC + SOL + ETH + OURO + NATGAS) para alcançar os $10/dia sem os 5 candidatos?",
        criteria=[
            "1.0 - Insuficiente",
            "2.0 - Parcialmente suficiente",
            "3.0 - Suficiente",
            "4.0 - Muito robusto e suficiente",
            "5.0 - Portfólio ideal e completo: Máxima diversificação com mínima fricção de spread"
        ]
    )
}

print("=" * 80)
print("  🏛️ CONSULTANDO CONSELHO JEV SOBRE OS 5 CANDIDATOS...")
print("=" * 80)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[+] Veredito recebido em {elapsed:.2f}s!\n")

results = {}
for q_name, ans in resp.answers.items():
    if hasattr(ans, "choice"):
        print(f"📌 {q_name}:")
        print(f"   Veredito JEV: {ans.choice} (Confiança: {ans.confidence:.1%})")
        for opt, p in ans.probabilities.items():
            print(f"     - {opt}: {p:.1%}")
        print()
        results[q_name] = {"verdict": ans.choice, "confidence": ans.confidence, "probabilities": ans.probabilities}
    elif hasattr(ans, "score"):
        print(f"⭐ {q_name}: {ans.score:.2f} / 5.00 (Confiança: {ans.confidence:.1%})")
        for k, p in ans.probabilities.items():
            print(f"     - Nível {k}: {p:.1%}")
        print()
        results[q_name] = {"score": ans.score, "confidence": ans.confidence, "probabilities": ans.probabilities}

with open("jev_5_candidates_council_verdict.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("[✓] Parecer gravado em jev_5_candidates_council_verdict.json!")
