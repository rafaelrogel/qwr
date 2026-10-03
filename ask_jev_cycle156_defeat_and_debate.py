# -*- coding: utf-8 -*-
"""
CONSULTA QUANTITATIVA AO JEV (TypeSafe SystemOne):
Auditoria Forense dos Últimos Ciclos (#155 e #156) e Debate Intelectual:
1. Reversão Terminal (Late-Candle Squeeze nos últimos 35s).
2. Descompasso de Strike (Spread Binance vs Chainlink na Abertura).
3. Calibração de Take-Profit Escalonado (SirMartingale) vs Deixar Expirar.
4. Gestão de Risco e Kelly Sizing para a Banca Atual ($25.39 USDC).
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
DOSSIÊ QUANTITATIVO: AUDITORIA FORENSE DOS CICLOS 155 E 156 (BTC 5M LIVE) & DEBATE DE MELHORIAS
====================================================================================================
Estado Atual da Carteira Polygon Safe (0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c):
- Depósito Inicial: $21.00 USDC
- Saldo Real Atual: $25.39 USDC
- Lucro Líquido Acumulado Real: +$4.39 USDC (+20.90%)
- Histórico Consolidado: 156 ciclos (106 Vitórias / 50 Derrotas | Win Rate: 67.9%)
- Operando com dinheiro real na Polymarket CLOB V2.

----------------------------------------------------------------------------------------------------
1. ANATOMIA FORENSE DA DERROTA MAIS RECENTE - CICLO 156 (2026-10-01 07:05:00 UTC):
- Ativo: Polymarket BTC Up or Down 5m (btc-updown-5m-1790834700)
- Tx de Entrada Real: 0x40691f84bd79b2fd81f705c39d9c22ab10a7c3822b7578b78b94e2a21a83864d
- Abertura da Vela (07:05:00 UTC):
  * Strike Chainlink Oráculo: $84,255.23
  * Binance Spot Referência: $84,325.50 (Spread de +$70.27 entre Binance e Chainlink na largada!)
- Ponto de Entrada (135s / 07:07:15 UTC):
  * Spot Chainlink: $84,226.11 (Delta = -$29.12 vs Deadband de $22.10 em regime TRENDING_MOMENTUM)
  * Binance Spot: $84,278.92 (Delta Binance = -$46.58)
  * Fluxo Futuros Binance: Net CVD = -3.51 BTC (33.9% de compras, venda institucional forte)
  * Top-of-Book OBI: -0.983 (venda maciça)
  * Livro Polymarket: Best Ask DOWN = $0.35 (desconto extremo, 2.85x payoff potencial)
  * Stake Kelly (25%): $2.22 USDC (6.3056 cotas)
  * Execução aprovada com Fair Value Bayesiano de 72.51%.
- Comportamento Intra-Vela (135s aos 260s):
  * 143s: Chainlink $84,226.11 (Delta -$29.12) -> Lucrando
  * 203s: Chainlink $84,232.39 (Delta -$22.84) -> Lucrando
  * 240s: Chainlink $84,228.42 (Delta -$26.81) -> Lucrando
  * 260s: Chainlink $84,228.42 (Delta -$26.81) -> Lucrando
- O Late-Candle Squeeze (265s aos 300s):
  * Aos 272s: Chainlink sobe para $84,243.31 (Delta -$11.92)
  * Nos últimos 30 segundos (07:09:30 a 07:10:00 UTC), entra uma pancada violenta de compra spot na Binance:
    o preço salta de $84,279 para $84,333.36!
  * O Chainlink Data Streams oficial da Polymarket calculou o TWAP dos últimos 60 segundos acima do strike inicial.
  * Resolução Oficial Polymarket: UP (OutcomePrices: ["1", "0"]).
  * Prejuízo na rodada: -$2.22 USDC.
  * Reconciliador assíncrono sincronizou a carteira on-chain perfeitamente.

----------------------------------------------------------------------------------------------------
2. ANATOMIA FORENSE DO CICLO ANTERIOR - CICLO 155 (2026-09-30 09:35:00 UTC):
- Strike Chainlink: $83,037.32
- Entrada aos 135s: Delta fraco de apenas -$11.45 (DOWN) cotado a $0.47.
- A vela reverteu no final para $83,100.37 (Delta +$63.05).
- Perda: -$2.11 USDC.
- Remédio implementado após o Ciclo 155: Elevação do Deadband Dinâmico com ATR e regime diurno
  (o que evitou com sucesso dezenas de falsas entradas durante as 12 horas da noite/madrugada).

----------------------------------------------------------------------------------------------------
3. DILEMAS ESTRATÉGICOS PARA O DEBATE INTELECTUAL COM O JEV:

DILEMA 1: Reversões nos últimos 30-40 segundos (Late-Candle Squeeze)
- Hipótese A: É ruído de cauda aleatório intrínseco de opções binárias 5m. O robô acertou a direção em 85% do tempo, pagou barato ($0.35) e tem WR de 68%. Qualquer tentativa de stop nos últimos 30s gerará slippage catastrófico devido ao spread aberto na Polymarket perto do vencimento.
- Hipótese B: Take-Profit Escalonado (SirMartingale). Se a cota comprada a $0.35 atingir >= $0.70 (lucro de +100%) entre 200s e 240s, colocar ordem limite de venda para realizar lucro garantido antes do risco de fechamento de vela.

DILEMA 2: Descompasso de Abertura entre Binance e Chainlink (Spread Lead-Lag)
- No Ciclo 156, a Binance abriu em $84,325 e a Chainlink em $84,255 (spread de +$70). A queda na Binance foi apenas uma retração em relação ao seu open, enquanto na Chainlink parecia um rompimento de strike.
- Devemos instituir um filtro onde, se |Binance_Open - Chainlink_Strike| > $50 USD na largada (:00s), a entrada primária é VETADA por inconsistência de oráculo?

DILEMA 3: Dimensionamento Kelly e Preservação de Capital da Banca ($25.39 USDC)
- O Kelly Fracionário (25%) alocou $2.22 (8.7% da banca).
- Manter o teto estrito de 8% (max $2.00-$2.50) ou restringir para aposta fixa de $1.00 até ultrapassar $30.00 USDC?
====================================================================================================
"""

questions = {
    "dilemma1_late_candle_squeeze_solution": Choice(
        instructions="JEV, avalie o Dilema 1: Qual é a melhor abordagem matemática para o risco de 'late-candle squeeze' nos últimos 30 segundos em opções de 5m da Polymarket?",
        criteria={
            "MAINTAIN_CURRENT_HOLD_EXPIRY": "MANTER COMO ESTÁ (HOLD ATÉ O VENCIMENTO): Reversões de últimos 30s são ruído intrínseco. Vender antecipadamente na Polymarket sofre com spread largo (5-10 centavos) e corta o payoff máximo de $1.00 de uma aposta comprada a $0.35. A assimetria matemática de pagar $0.35 para receber $1.00 com WR > 65% supera com folga essas perdas pontuais.",
            "ADD_STAGED_TAKE_PROFIT_AT_2X": "ADICIONAR TAKE-PROFIT ESCALONADO (2.0x / 70¢): Se o Best Bid atingir >= $0.70 entre 200s e 240s para cotas compradas <= $0.40, realizar lucro antecipado de 100% e zerar o risco de reversão nos 60s finais.",
            "TIGHTEN_STOP_LOSS_LAST_MINUTE": "STOP-LOSS AGRESSIVO NO ÚLTIMO MINUTO: Se o delta spot reverter contra o strike após os 240s, despejar a mercado imediatamente."
        }
    ),
    "dilemma2_oracle_lead_lag_spread_filter": Choice(
        instructions="JEV, avalie o Dilema 2: A divergência inicial de +$70 entre Binance Spot e Strike Chainlink no Ciclo 156 justifica a criação de um Filtro de Discrepância de Abertura (Lead-Lag Strike Gate)?",
        criteria={
            "APPROVE_ORACLE_SPREAD_FILTER_50USD": "APROVA O FILTRO DE SPREAD DE ABERTURA: Se |Binance_Spot - Chainlink_Strike| > $50 USD na largada (:00s), vetar a entrada primária. Um spread excessivo indica defasagem temporária no feed Chainlink, o que distorce o verdadeiro delta intra-vela e expõe o trade a fakeouts quando a Chainlink convergir para a Binance.",
            "TOLERATE_SPREAD_BELOW_100USD": "TOLERAR ATÉ $100 USD: O spread entre Binance e Chainlink oscila naturalmente em alta volatilidade. Um teto de $50 USD vetaria muitos trades legítimos. O teto deveria ser de pelo menos $90-$100 USD.",
            "IGNORE_BINANCE_ORACLE_ONLY_MATTERS": "REJEITA O FILTRO: A Polymarket liquida exclusivamente pela Chainlink. O preço da Binance na abertura é irrelevante para a resolução do contrato."
        }
    ),
    "dilemma3_kelly_sizing_current_bankroll": Choice(
        instructions="JEV, avalie o Dilema 3: Com a banca atual em $25.39 USDC (+20.9% de lucro real sobre o aporte de $21.00), qual deve ser a política de dimensionamento de apostas no Desk 1?",
        criteria={
            "MAINTAIN_FRACTIONAL_KELLY_8PCT_CAP": "MANTER KELLY FRACIONÁRIO COM TETO DE 8% (MAX $2.00 - $2.50): O dimensionamento atual está matematicamente impecável. A perda no ciclo 156 foi de apenas $2.22 (8.7%), preservando 91.3% da banca e mantendo o lucro acumulado em +20.9%. Reduzir para $1.00 mutila o crescimento composto em sequências vitoriosas.",
            "REDUCE_TO_FIXED_1_USD_UNTIL_30": "REDUZIR PARA $1.00 FIXO ATÉ BANCA ATINGIR $30.00: Por prudência psicológica e preservação de capital após duas derrotas recentes, travar em $1.00 fixo até a banca alcançar $30.00 USDC.",
            "INCREASE_STAKE_FOR_FAST_RECOVERY": "AUMENTAR STAKE: Aumentar o teto para 12-15% para recuperar a perda mais rapidamente."
        }
    ),
    "intellectual_consensus_and_code_action": Choice(
        instructions="JEV, sintetizando a análise quantitativa global: devemos alterar o código de live_trader_5m.py neste momento? Se sim, qual é a única alteração prioritária recomendada?",
        criteria={
            "IMPLEMENT_ORACLE_SPREAD_GATE_ONLY": "IMPLEMENTAR APENAS O FILTRO DE DISCREPÂNCIA DE SPREAD ORÁCULO/BINANCE (LEAD-LAG GATE): O código de execução, Kelly e gestão de risco estão excelentes (67.9% WR). A única vulnerabilidade real revelada pelo ciclo 156 foi a distorção do strike por lag da Chainlink vs Binance na abertura. Adicionar o filtro |Binance - Chainlink| <= $50-$60 USD na largada é a melhoria cirúrgica de maior EV.",
            "NO_CODE_CHANGES_NEEDED_SYSTEM_OPTIMAL": "NENHUMA ALTERAÇÃO NECESSÁRIA: O sistema está operando no sweet-spot estatístico (WR 67.9%, lucro líquido positivo). Perdas isoladas são normais e tentar 'consertar' o código após cada derrota introduz sobreajuste (overfitting).",
            "RADICAL_OVERHAUL_NEEDED": "REFORMULAÇÃO RADICAL: O sistema necessita de uma reestruturação profunda em múltiplos módulos."
        }
    )
}

print("=" * 90)
print(" [JEV SYSTEMONE] ENVIANDO DOSSIÊ DOS CICLOS 155/156 E INICIANDO DEBATE INTELECTUAL...")
print("=" * 90)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n>>> DEBATE QUANTITATIVO COM O JEV CONCLUÍDO EM {elapsed:.2f}s <<<\n")

results = {}
for qname, ans in resp.answers.items():
    print(f"[{qname.upper()}]")
    print(f"Decisão: {ans.choice}")
    print(f"Confiança: {ans.confidence * 100:.1f}%")
    print("Probabilidades:")
    for opt, p in ans.probabilities.items():
        print(f"  * {opt}: {p:.1%}")
    print("-" * 70)
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

output_file = "jev_cycle156_debate_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Parecer do JEV gravado em '{output_file}'.")
