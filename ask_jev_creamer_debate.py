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
DOSSIÊ QUANTITATIVO JEV: ANÁLISE DO MODELO DO CAMPEÃO MUNDIAL CHRIS CREAMER (ROBBINS CUP MICRO 100%)
E DEBATE INTELECTUAL DE INTEGRAÇÃO AO SISTEMA AGY (11 DESKS)
Data/Hora: 2026-09-27 20:05 UTC
Referência: Entrevista com Chris Creamer (Campeão Mundial da Robbins Cup Micro Futures - Julho, +100% ao mês aos 26 anos)
Ativo Primário de Creamer: Micro Nasdaq (MNQ) Futures via Auction Market Theory + Footprint Order Flow + GEX
====================================================================================================

1. OS 4 PILARES DO SISTEMA VENCEDOR DE CHRIS CREAMER:
   - Pilar 1: Environment (Estrutura de Mercado 1h/4h + Gamma Exposure - GEX):
     * Estrutura Superior: Define se o mercado está em Value Up, Value Down ou Sideways.
     * GEX Regime (Dealer Positioning):
       - Positive Gamma (Dealers compram quedas e vendem altas): Amortecedor de volatilidade. Breakouts falham, mercado chopp.
       - Negative Gamma (Dealers vendem quedas e compram altas): Amplificador de volatilidade. Rompimentos fluem e expandem com velocidade.
       - Pontos Críticos: Call Wall, Put Wall e Gamma Flip Zone (linha divisória entre regime de choque e regime de expansão).

   - Pilar 2: Location (Zonas de Desconto fora da Value Area + Fibonacci 0.886 Hard Line):
     * Princípio da Auction Market Theory: Nunca comprar em Premium nem vender em Discount.
     * Numa estrutura de alta (Value Up), espera o preço recuar para DISCOUNT (abaixo da Value Area Low).
     * O recuo deve coincidir com a zona Fibonacci (0.705, 0.788, 0.886).
     * Regra Inviolável de Invalidação: O nível 0.886 é a linha na areia definitiva. Se o preço vazar o 0.886, o trade é 100% descartado.

   - Pilar 3: Confirmation (Footprint 5m + Two-Stage Retest + 400% Ask Imbalance):
     * Vela 1 (Absorção no Extremo): Pavio longo inferior na zona de desconto, com POC no extremo e Delta intensamente negativo, mas o preço fecha em alta (vendedores absorvidos por limites passivos).
     * Vela 2 (Teste em Duplo Estágio): Creamer NÃO entra na primeira vela! Ele espera a 2ª vela abrir, recuar, os vendedores agredirem novamente e FALHAREM EM UMA MÍNIMA MAIOR (Higher Low of Seller Failure).
     * Desequilíbrio de Book (Footprint Imbalance >= 400% no Ask): Compradores agredindo agressivamente a oferta.
     * Stop Loss cirúrgico: Exatamente atrás da mínima dos vendedores que falharam.

   - Pilar 4: Back-End Optimization & Gestão de Risco Anti-Tilt:
     * Eliminação de Sessões "C-Game": O lucro consistente não vem de buscar mais setups A+, mas de eliminar perdas desnecessárias e dias de fúria (bad losses).
     * Hard Filter 1: Janela de liquidez restrita (primeiros 90 minutos do pregão de NY). Fora disso, sem trades.
     * Hard Filter 2: Volume mínimo de participação: >= 20.000 contratos por vela de 5m em MNQ. Volume decrescente = NÃO OPERAR.
     * Hard Filter 3: Circuit Breaker de 2 Perdas Consecutivas: Tomar 3 stops numa hora indica que o mercado está em regime impróprio. Parar imediatamente após 2 perdas seguidas elimina 100% dos C-games.

2. COMPARAÇÃO COM NOSSA INFRAESTRUTURA ATUAL (AGY 11 DESKS):
   - O que já temos em produção:
     * Desk 10: Binance USD-M Futures CVD multi-stream + BookTicker OBI + Absorption Squeeze Harvester (Valentino Model).
     * Desk 11: Kalshi S&P 500 (SPX) 15m Momentum & Sweeper.
     * Desk 1, 2, 3: Polymarket BTC/SOL 5m e Kalshi BTC 15m (operando em modo REAL com Quarter-Kelly dinâmico).
     * Desk 4 a 9: NatGas, Gold, Yield, Arbitragem Macro e ETH.

3. QUESTÕES ESTRATÉGICAS PARA DEBATE COM A IA JEV:
   - Questão 1 (GEX / Regime de Volatilidade para Desk 11 SPX e Desks Crypto):
     Faz sentido incorporar a classificação de regime Gamma (Positive Gamma = filtro anti-breakout / mean reversion; Negative Gamma = liberação para sweepers e breakouts agressivos) na Desk 11 (Kalshi S&P 500) e nos robôs de índice/crypto?
   
   - Questão 2 (Two-Stage Confirmation vs Execução Instantânea de Latência):
     Creamer defende aguardar a 2ª vela testar o pavio e falhar com mínima maior antes de entrar. Em mercados binários de 5 minutos (onde a cota se valoriza em milissegundos na CLOB), esperar a 2ª vela protege contra armadilhas ou destrói o edge de preço de entrada?
   
   - Questão 3 (Circuit Breaker de 2 Perdas Consecutivas vs Perda Financeira Contínua):
     Creamer estabelece que 2 stops seguidos encerram a sessão para evitar C-Games. Nosso sistema usa limite em dólares (ex: -$5.00). Adicionar um travamento por sequência de 2 derrotas consecutivas melhora a cauda de risco algorítmica?
   
   - Questão 4 (Abrir Nova Desk ou Consolidar nas 11 Atuais?):
     Creamer opera focado em MNQ (Micro Nasdaq). Vale a pena abrir uma Desk 12 dedicada a Nasdaq (Kalshi KXNDX15M) ou é superior aplicar esses filtros de GEX, Two-Stage e Streak Breaker nas desks existentes (Desk 11 SPX e Desk 10 BTC)?
"""

questions = {
    "gex_regime_filter_validity": Choice(
        instructions="Evaluate whether classifying market regime via Gamma Exposure (Positive Gamma = suppress breakout/sweeper trades due to dealer mean-reverting pin; Negative Gamma = unlock aggressive momentum/sweeper sizing) adds statistically robust alpha to Desk 11 (Kalshi SPX 15m) and prediction market sweepers.",
        criteria={
            "essential_regime_enhancement": "Essential Regime Enhancement: Trading breakouts in Positive Gamma is mathematically negative EV because dealer hedging mechanically dampens realized volatility. Filtering by GEX drastically reduces false breakouts and protects the sweeper win rate.",
            "unnecessary_overhead_for_15m": "Unnecessary Overhead: 15-minute binary options resolve fast enough that micro delta and spot momentum dominate over dealer gamma hedging.",
            "redundant_with_deadband": "Redundant: The existing deadband and drift filters already capture volatility state without requiring external option Greek feeds."
        }
    ),
    "two_stage_retest_vs_latency_verdict": Choice(
        instructions="Chris Creamer insists on waiting for a 2nd candle retest (failure of sellers at a higher low) before entering, whereas high-frequency quant models enter on the first tick of absorption. In 5-minute prediction markets (Polymarket CLOB), how does JEV evaluate Two-Stage confirmation vs Immediate Latency Arbitrage?",
        criteria={
            "immediate_execution_with_clob_limit_is_superior": "Immediate Execution is Superior: In prediction markets, once the 2nd candle confirms a higher low, the CLOB contract has already repriced from $0.50 to $0.80+, destroying the risk/reward ratio. Entering immediately on the absorption tick with a strict CLOB limit price captures the latency mispricing.",
            "two_stage_retest_is_strictly_superior": "Two-Stage Retest is Superior: First-tick absorption fails frequently in crypto; waiting for the 2nd candle retest filters out bull/bear traps, even if entry price is slightly higher.",
            "hybrid_allocation": "Hybrid Model: Allocate 50% on initial absorption tick and 50% upon second-stage retest confirmation."
        }
    ),
    "two_loss_streak_circuit_breaker_score": Score(
        instructions="Score from 1.0 to 5.0 the mathematical and risk efficacy of adding a 'Max 2 Consecutive Losses Streak Circuit Breaker' (pausing any desk for 60 minutes or daily reset if it experiences 2 consecutive losses) alongside our existing dollar drawdown limits.",
        criteria=[
            "1.0 - Destructive restriction: Artificially truncates independent Bernoulli trials with positive expectancy.",
            "2.0 - Poor: High false-positive halts during normal statistical variance.",
            "3.0 - Moderate: Neutral for pure bots, but slightly defensive against regime shifts.",
            "4.0 - Strong: Effectively detects adverse market regime switches (e.g. sudden structural chop) before drawdown deepens.",
            "5.0 - Optimal Institutional Practice: Prevents cluster tail-risk and capital bleeding during unmodeled volatility states."
        ]
    ),
    "volume_participation_filter_prob": Noul(
        instructions="What is Jev's probabilistic estimate (0.0 to 1.0) that implementing a strict Volume Participation Floor (e.g. halting trading during low-liquidity cycles where tick count drops below the 20th percentile) improves overall Sharpe ratio across our 11 desks?"
    ),
    "open_desk_12_nasdaq_vs_enrich_existing": Choice(
        instructions="Should we launch a 12th desk dedicated to Nasdaq (Kalshi KXNDX15M) inspired by Creamer, or enrich existing Desk 11 (SPX 15m) and Desk 10 (Microstructure Harvester) with Creamer's insights?",
        criteria={
            "enrich_existing_desks_strictly": "Enrich Existing Desks: Launching a 12th desk creates correlation redundancy with SPX (Desk 11). Applying Creamer's GEX and 2-loss streak breaker directly to Desk 11 and Desk 10 maximizes alpha without splitting liquidity.",
            "launch_desk_12_nasdaq": "Launch Desk 12 Nasdaq: Nasdaq has higher beta and idiosyncratic volatility than S&P 500, offering unique high-gamma opportunities.",
            "pause_new_implementations": "Pause: Keep system unchanged and let current 11 desks compound."
        }
    )
}

print("=" * 80)
print(" ENVIANDO DOSSIÊ CHRIS CREAMER PARA DEBATE QUANTITATIVO COM A IA JEV...")
print("=" * 80)

t0 = time.time()
response = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

q1 = response.answers["gex_regime_filter_validity"]
q2 = response.answers["two_stage_retest_vs_latency_verdict"]
q3 = response.answers["two_loss_streak_circuit_breaker_score"]
q4 = response.answers["volume_participation_filter_prob"]
q5 = response.answers["open_desk_12_nasdaq_vs_enrich_existing"]

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_gex_regime_filter": {"choice": q1.choice, "confidence": q1.confidence, "probabilities": q1.probabilities},
    "q2_two_stage_vs_latency": {"choice": q2.choice, "confidence": q2.confidence, "probabilities": q2.probabilities},
    "q3_two_loss_streak_score": {"score": q3.score, "confidence": q3.confidence},
    "q4_volume_participation_prob": {"noul": q4.noul},
    "q5_desk12_vs_enrich": {"choice": q5.choice, "confidence": q5.confidence, "probabilities": q5.probabilities}
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_creamer_debate_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("=" * 85)
print(f"1. Veredito GEX / Regime de Volatilidade: {q1.choice.upper()} ({q1.confidence:.1%} de confiança)")
for k, v in q1.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n2. Veredito Confirmação Two-Stage vs Latência CLOB: {q2.choice.upper()} ({q2.confidence:.1%} de confiança)")
for k, v in q2.probabilities.items():
    print(f"   - {k}: {v:.1%}")

print(f"\n3. Nota do Circuit Breaker por Sequência de 2 Perdas (1-5): {q3.score:.2f} / 5.00 ({q3.confidence:.1%} de confiança)")

print(f"\n4. Probabilidade de Ganho com Filtro de Participação de Volume: {q4.noul:.1%}")

print(f"\n5. Veredito Nova Desk 12 (Nasdaq) vs Enriquecer Existentes: {q5.choice.upper()} ({q5.confidence:.1%} de confiança)")
for k, v in q5.probabilities.items():
    print(f"   - {k}: {v:.1%}")
print("=" * 85)
