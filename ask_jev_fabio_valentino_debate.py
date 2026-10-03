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
DOSSIÊ QUANTITATIVO JEV: ANÁLISE DO MODELO DO CAMPEÃO MUNDIAL DA ROBBINS CUP (FABIO VALENTINO)
E DEBATE INTELECTUAL DE INTEGRAÇÃO AO SISTEMA AGY (11 DESKS)
Data/Hora: 2026-09-27 19:40 UTC
Referência: Podcast Chart Fanatics com Fabio Valentino (Top 3 Robbins World Cup >500% em Futuros)
Ativo Analisado no Podcast: E-mini / Micro Nasdaq (NQ) via Order Flow L2 + Volume Profile + AMT
====================================================================================================

1. TESE CENTRAL E PILARES DO MODELO DE FABIO VALENTINO:
   - Pilar 1: Auction Market Theory (AMT) & Market State:
     * O mercado passa 70% do tempo em Equilíbrio (Balance / Consolidação na Value Area) e 30% em Desequilíbrio (Imbalance / Out of Balance).
     * Seguir tendência dentro da Value Area tem win rate pífio (<30-40%) por reversão natural ao POC (Point of Control).
     * O modelo de tendência SÓ é ativado quando o mercado está comprovadamente "Out of Balance" (fora da Value Area).
   
   - Pilar 2: Localização por Volume Profile (LVN - Low Volume Nodes):
     * Em vez de Price Action subjetivo, mapeia Low Volume Nodes (áreas onde o book transacionou com extrema rapidez e vácuo de liquidez).
     * LVNs atuam como zonas de continuação de altíssima probabilidade ou suporte para trailing stop com zero draw down.

   - Pilar 3: Gatilho de Execução via Ordem a Mercado e Absorção (Bubbles & CVD):
     * Filtra agressões institucionais (bolhas de 30 a 100+ contratos a mercado).
     * Detecção de Absorção ("Punching the Wall"): quando agressões gigantescas de venda ocorrem mas o preço não cai (makers absorvem tudo com ordens limit).
     * Squeeze de Traders Presos: Quando os vendedores absorvidos percebem o erro e são forçados a estopar/comprar, gerando explosão de momentum com drawdown quase zero.
     * Gestão de Risco Robbins Cup:
       - Risco inicial de 0.25% a 0.5% por operação.
       - Aporte de lote/alavancagem SÓ ocorre com o LUCRO DO DIA ("House Money"). Nunca arrisca o patrimônio inicial em escaladas.
       - Stop loss rápido para o zero a zero assim que a vela de absorção confirma a rejeição.

2. COMPARAÇÃO COM NOSSA ARQUITETURA ATUAL (AGY 11 DESKS):
   - O que já temos em produção:
     * Desk 10: Binance USD-M Futures CVD multi-stream + BookTicker OBI (Order Book Imbalance) de milissegundo.
     * Hoje implementamos o VETO ANTI-ABSORÇÃO: Se compradores agridem a mercado mas OBI está negativo (absorção institucional por asks), o bot veta a compra.
     * Live Trader 5m: Quarter-Kelly (25%) e SirMartingale Take-Profit (venda no topo de liquidez a $0.86-$0.92), que gerou duas vitórias seguidas hoje (Ciclos 149 e 150, lucrando +$5.87).
     * Kalshi Desks: Filtros de continuidade de tendência macro e deadband dinâmico.

3. QUESTÕES ESTRATÉGICAS PARA DEBATE COM A IA JEV:
   - Questão 1 (Da Defesa para o Ataque - Trapped Traders Squeeze):
     Atualmente usamos a absorção apenas como VETO defensivo (cancela o trade). Valentino usa a absorção como o GATILHO OFENSIVO PRINCIPAL (se vendedores foram absorvidos e o preço rompe a máxima da agressão, ele compra o squeeze).
     Podemos transformar essa detecção de absorção em um sinal direcional ativo para a Desk 10 ou Desk 1?

   - Questão 2 (Regra de Escalada Intradiária "House Money" vs Kelly Estático):
     Valentino revelou que seu desempenho de 500% na Robbins Cup veio de usar o lucro acumulado no próprio dia para alavancar os trades subsequentes, resetando a banca todo dia.
     Faz sentido incorporar uma modulação intradiária no Kelly Fracionário que aumente a fração de 25% para 35% apenas quando estivermos operando com lucro já realizado no dia?

   - Questão 3 (Especialização em Ativo Único vs Diversificação de 11 Desks):
     Valentino afirma que operar múltiplos ativos (ex: NQ + Petróleo) destrói o foco e que dominar 1 único ativo é o "código de trapaça". Nosso sistema opera 11 desks de forma algorítmica.
     A automação algorítmica elimina a limitação humana de múltiplos ativos ou estamos dispersando a liquidez?
"""

questions = {
    "absorption_squeeze_signal_verdict": Choice(
        instructions="Evaluate whether transitioning our BookTicker/CVD absorption detection from purely a defensive VETO into an active offensive 'Trapped Traders Squeeze' signal (buying when aggressive sellers are absorbed and price reclaims the high of the absorption cluster) is mathematically robust for Desk 10 and Desk 1.",
        criteria={
            "highly_valuable_alpha_generator": "Highly Valuable Alpha: Exploits the structural forced-liquidation cascade of trapped market participants. In prediction markets with 5m-15m horizons, a trapped flow squeeze creates explosive short-term delta expansion, ideal for fast Take-Profit execution.",
            "redundant_with_existing_cvd_breakout": "Redundant: The existing CVD momentum filters already capture the aftermath of these moves without the complexity of bidirectional absorption modeling.",
            "unreliable_in_crypto": "Unreliable in Crypto: Crypto order flow has too much spoofing and wash trading for cluster absorption reversal to be statistically sound."
        }
    ),
    "intraday_house_money_kelly_score": Score(
        instructions="Score from 1.0 to 5.0 the mathematical validity of an 'Intraday House Money Ratchet' (allowing Fractional Kelly to scale from 25% to 35% exclusively when funded by intraday realized P&L, resetting daily) to accelerate compounding while strictly defending base equity.",
        criteria=[
            "1.0 - Severe Gambler's Fallacy / Path-dependent destruction",
            "2.0 - Suboptimal variance amplification",
            "3.0 - Neutral impact with added complexity",
            "4.0 - Statistically sound convex profit extraction with bounded downside",
            "5.0 - Institutional perfection: Asymmetric upside capture without exposing core principal"
        ]
    ),
    "single_asset_vs_multi_desk_verdict": Choice(
        instructions="Fabio Valentino argues that mastering a single instrument (NQ) is superior to multi-asset trading. In our quantitative algorithmic setting running 11 desks across Crypto, Equities, Commodities, and Macro, how does JEV evaluate single-asset focus vs algorithmic cross-sectional diversification?",
        criteria={
            "algorithmic_multi_desk_is_strictly_superior": "Algorithmic Multi-Desk is Superior: Human traders suffer cognitive overload across multiple assets, but deterministic algorithms execute without fatigue. Cross-sectional portfolio diversification across uncorrelated assets (Crypto, S&P 500, Gold, NatGas) flattens the equity drawdown curve and maximizes the portfolio Sharpe ratio.",
            "concentrate_on_top_3_desks": "Concentrate: 11 desks creates excess friction; consolidate strictly into the 3 most liquid desks (BTC, SOL, S&P 500).",
            "single_asset_scalping_is_best": "Single-Asset is Best: Even algorithms should focus 100% of capital on one dominant asset."
        }
    ),
    "low_volume_node_prediction_prob": Noul(
        instructions="What is Jev's probabilistic estimate (0.0 to 1.0) that implementing Low Volume Node (LVN) liquidity vacuum detection alongside our existing Chainlink Delta thresholds will increase 5m/15m directional velocity and reduce time-in-trade?"
    ),
    "top_actionable_code_recommendation": Choice(
        instructions="What is the single most actionable and mathematically rigorous enhancement from Valentino's playbook to implement in our codebase next?",
        criteria={
            "implement_absorption_squeeze_reversal_module": "Implement Absorption Squeeze Module: When aggressive taker volume fails to breach price and OBI diverges, arm an offensive entry on the breakout of the cluster.",
            "implement_intraday_house_money_ratchet": "Implement Intraday House Money Ratchet: Modulate Kelly fraction based on day's realized P&L.",
            "keep_code_untouched_and_monitor_current_run": "Keep Code Untouched: System is already on fire (+31% today), maintain active execution without introducing new variables."
        }
    )
}

print("=" * 80)
print(" ENVIANDO DOSSIÊ VALENTINO PARA DEBATE QUANTITATIVO COM A IA JEV...")
print("=" * 80)

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

q1 = response.answers["absorption_squeeze_signal_verdict"]
q2 = response.answers["intraday_house_money_kelly_score"]
q3 = response.answers["single_asset_vs_multi_desk_verdict"]
q4 = response.answers["low_volume_node_prediction_prob"]
q5 = response.answers["top_actionable_code_recommendation"]

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_absorption_squeeze": {"choice": q1.choice, "confidence": q1.confidence, "probabilities": q1.probabilities},
    "q2_intraday_house_money_score": {"score": q2.score, "confidence": q2.confidence},
    "q3_multi_desk_vs_single": {"choice": q3.choice, "confidence": q3.confidence, "probabilities": q3.probabilities},
    "q4_lvn_velocity_prob": {"noul": q4.noul},
    "q5_top_actionable_rec": {"choice": q5.choice, "confidence": q5.confidence, "probabilities": q5.probabilities}
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_valentino_debate_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("=" * 85)
print(f"1. Veredito sobre Squeeze por Absorção: {q1.choice.upper()} ({q1.confidence:.1%} de confiança)")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Nota da Gestão House Money Robbins Cup (1-5): {q2.score:.2f} / 5.00 ({q2.confidence:.1%} de confiança)")

print(f"\n3. Veredito Multi-Desk vs Ativo Único: {q3.choice.upper()} ({q3.confidence:.1%} de confiança)")
for k, v in q3.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n4. Probabilidade de Aceleração por Low Volume Nodes (LVN): {q4.noul:.1%}")

print(f"\n5. Recomendação Prática Prioritária: {q5.choice.upper()} ({q5.confidence:.1%} de confiança)")
for k, v in q5.probabilities.items():
    print(f"   - {k}: {v:.1%}")
print("=" * 85)
