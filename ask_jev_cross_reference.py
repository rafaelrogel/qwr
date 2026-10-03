import os
import json
import time
from dotenv import load_dotenv

load_dotenv(".env")
from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

dossier = """
DOSSIÊ FORENSE DE CROSS-REFERENCE ENTRE TODOS OS CÓDIGOS DA FROTA AGY
Data: 2026-10-02 11:50 UTC

ESPECTRO AUDITADO (11 ROBÔS + 3 MÓDULOS NUCLEARES):
1. live_trader_5m.py (Desk 1 — Polymarket BTC 5m LIVE)
2. sol_trader_5m.py (Desk 2 — Polymarket SOL 5m LIVE)
3. kalshi_trader_15m.py (Desk 3 — Kalshi BTC 15m LIVE)
4. btc_15m_paper_trader.py (Desk 3B — Polymarket BTC 15m PAPER)
5. kalshi_natgas_trader_15m.py (Desk 5 — Kalshi NatGas 15m LIVE)
6. desk6_yield_harvester.py (Desk 6 — Yield Harvester PAPER)
7. desk7_cross_arb.py (Desk 7 — Cross-Arb Macro Radar)
8. eth_trader_5m.py (Desk 8 — Polymarket ETH 5m PAPER)
9. kalshi_gold_trader_15m.py (Desk 9 — Kalshi Gold 15m PAPER)
10. kalshi_spx_trader_15m.py (Desk 11 — Kalshi SPX 15m PAPER)
11. desk12_weather_metar.py (Desk 12 — Weather METAR PAPER)

DISPARIDADES E INCONSISTÊNCIAS ESTRUTURAIS IDENTIFICADAS NO CÓDIGO:

1. INSTANCE LOCK (Proteção contra Instâncias Duplicadas):
   - live_trader_5m possui _acquire_instance_lock ('live_trader.lock') que impede 2 processos de rodarem ao mesmo tempo.
   - sol_trader_5m (que opera DINHEIRO REAL na mesma Safe) NÃO possui instance lock! Se o usuário abrir o .bat duas vezes, pode enviar ordens duplicadas em dinheiro real.

2. RECONCILIAÇÃO DE CARTEIRA COMPARTILHADA (Shared Safe 1271):
   - Desk 1 monitora o impacto isolado de trades da SOL (get_shared_wallet_sol_impact).
   - Desk 2 não desconta trades do BTC do seu saldo local, assumindo o saldo total da Safe como seu bankroll único.

3. ESCUDO ANTI-SWEEP (Ziad Francis SMC Algorithm):
   - Presente no Desk 1 e Desk 2 (filtra falsos rompimentos e wicks).
   - Ausente no Desk 8 (ETH 5m) e Desk 3B (BTC 15m), deixando-os vulneráveis a stop-outs por wicks transitórios.

4. MODELAGEM TWAP ORACLE:
   - Desk 1 e Desk 3B têm amostragem contínua de TWAP via RPC Polygon.
   - Desk 8 (ETH 5m) depende de APIs REST defasadas da Gamma e Binance sem agregação de TWAP ponderada.

5. POLÍTICA DE TETO DE PREÇO (PRIMARY_MAX_PRICE):
   - Desk 1 ($0.65) e Desk 3B ($0.65) têm teto anti-assimetria estrito.
   - Desk 6 (Yield Harvester) opera deliberadamente no extremo oposto (compra a 98c para capturar theta residual de 2c).
"""

client = TypeSafeClient()

questions = {
    "instance_lock_urgency": Choice(
        instructions="Quão urgente é adicionar Instance Lock (.lock) no Desk 2 (sol_trader_5m.py) para evitar ordens duplicadas em dinheiro real?",
        criteria={
            "urgent_mandatory": "URGENTE E MANDATÓRIO: Operar dinheiro real sem instance lock é falha grave de segurança operacional.",
            "low_priority": "BAIXA PRIORIDADE: O usuário raramente abre duas janelas.",
            "unnecessary": "DESNECESSÁRIO: O sistema operacional lida com isso."
        }
    ),
    "anti_sweep_expansion": Choice(
        instructions="O Desk 8 (ETH 5m) e o Desk 3B (BTC 15m) deveriam herdar o Anti-Sweep Shield do Desk 1?",
        criteria={
            "highly_recommended": "ALTAMENTE RECOMENDADO: Uniformiza a robustez da frota e reduz stop-outs falsos em velas de alta volatilidade.",
            "not_applicable_to_15m": "APENAS PARA 5m: Em 15m o anti-sweep é irrelevante.",
            "neutral": "NEUTRO: Efeito marginal."
        }
    ),
    "cross_pollination_priority": Choice(
        instructions="Qual é a melhoria de maior retorno imediato que um robô pode herdar de outro?",
        criteria={
            "desk2_adopting_instance_lock": "DESK 2 ADOTAR INSTANCE LOCK: Protege capital real contra execução duplicada.",
            "desk8_adopting_twap_and_salvage": "DESK 8 ADOTAR TWAP E SALVAGE: Eleva o ETH 5m para o padrão do BTC 5m.",
            "kalshi_desks_adopting_dynamic_deadband": "DESKS KALSHI ADOTAREM DEADBAND DINÂMICO: Reduz ruído em ouro e SPX."
        }
    ),
    "fleet_code_cohesion_score": Score(
        instructions="Atribua uma nota de 1.0 (código fragmentado e díspar) a 5.0 (arquitetura modular coesa e padronizada) para o estado atual da frota.",
        criteria=[
            "1.0 = Cada robô foi escrito com paradigmas totalmente diferentes, sem reaproveitamento.",
            "2.0 = Algum reaproveitamento de risk_gate, mas com disparidades críticas de segurança entre desks live.",
            "3.0 = Coesão moderada: módulos nucleares compartilhados, mas com recursos avançados presentes em uns e ausentes em outros.",
            "4.0 = Alta padronização com poucas inconsistências residuais.",
            "5.0 = Arquitetura perfeitamente unificada."
        ]
    ),
    "final_synthesis": Noul(
        instructions="Apresente uma síntese conclusiva com o plano de ação de engenharia para padronização da frota."
    )
}

print("-> Submetendo cross-reference ao JEV...")
start_t = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - start_t

print(f"-> Resposta recebida do JEV em {elapsed:.2f}s!\n")

results = {}
for q_name, ans in response.answers.items():
    choice = getattr(ans, "choice", None)
    score = getattr(ans, "score", None)
    noul = getattr(ans, "noul", None)
    results[q_name] = {"choice": choice, "score": score, "noul": noul}
    print(f"[{q_name}]: choice={choice} | score={score} | noul={noul}")

with open("fleet_cross_reference_jev_verdict.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("Salvo em fleet_cross_reference_jev_verdict.json")
