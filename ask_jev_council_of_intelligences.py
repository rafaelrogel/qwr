# -*- coding: utf-8 -*-
"""
CONSELHO DE INTELIGÊNCIAS QUANTITATIVAS COM A IA JEV (TYPESAFE SYSTEMONE)
Missão: Mapear, Auditar e Selecionar os Próximos Desks Operacionais para atingir
a meta consistente de +$10 USD/dia na Polymarket e na Kalshi com micro-apostas ($0.50 - $1.00).
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

with open("realistic_candidate_desks_summary.json", "r", encoding="utf-8") as f:
    cand_metrics = json.load(f)

dossier = f"""
====================================================================================================
DOSSIÊ OFICIAL DO CONSELHO DE INTELIGÊNCIAS QUANTITATIVAS (JEV SYSTEMONE)
Data: 2026-09-26
Objetivo Estratégico do Trader:
- Construir um ecossistema de múltiplos desks algorítmicos descorrelacionados
- Operar exclusivamente com micro-apostas ($0.50 a $1.00 USD por contrato)
- Meta de Retorno: Lucro líquido consolidado de +$10.00 USD/dia (~$300 USD/mês)
- Proteção Máxima: Zero risco de ruína da banca (banca atual ~$30 USD, crescendo organicamente)

1. DESKS ATUALMENTE EM OPERAÇÃO:
   • Desk 1: Polymarket BTC 5m (LIVE, 71% WR em 131 ciclos, motor TWAP recém-atualizado)
   • Desk 2: Polymarket SOL 5m (LIVE, 100% WR em 3 ciclos)
   • Desk 3: Kalshi BTC 15m (LIVE, 100% WR em 2 ciclos)
   • Desk 4: Kalshi NatGas EIA Storage (STANDBY Quarta/Quinta, Sharpe 2.46 no backtest de 13 anos)
   • Desk 5: Kalshi NatGas 15m (PAPER, 93.8% WR em 16 ciclos reais, +$7.58 USD gerados)
   • Desk 6: Kalshi Yield Harvester 98¢ (PAPER, screener de cauda)
   • Desk 7: Cross-Market Polymarket x Kalshi (RADAR de Arbitragem)

2. CANDIDATOS TESTADOS NO BACKTEST FORENSE (SEM LOOKAHEAD BIAS - 1.000 MINUTOS REAIS):
   • ETH 5m (Polymarket): 12 trades, 100% WR, EV +$9.99/trade (em $10 stake), Sharpe 535.9
   • ETH 15m (Kalshi KXETH15M): 4 trades, 100% WR, EV +$9.58/trade, Sharpe 252.8
   • Gold 15m (Kalshi KXGOLD15M): 3 trades, 100% WR, EV +$9.99/trade, Sharpe 228.5 (Zero correlação com Cripto!)
   • SOL 5m (Polymarket): 14 trades, 92.86% WR, EV +$7.55/trade, Sharpe 104.3
   • SOL 15m (Kalshi KXSOL15M): 10 trades, 90.0% WR, EV +$7.97/trade, Sharpe 122.1
   • XRP 5m (Polymarket): 6 trades, 100% WR, EV +$10.41/trade, Sharpe 476.0
   • BTC 5m (Polymarket): 12 trades, 83.33% WR, EV +$6.52/trade, Sharpe 55.1

3. DILEMAS E QUESTÕES ESTRATÉGICAS SUBMETIDAS AO CONSELHO JEV:
   - Dilema A: A inclusão do ETH 5m (com gatilho de Lead-Lag do BTC) é o passo mais rápido e seguro?
   - Dilema B: O Ouro 15m (Kalshi KXGOLD15M) oferece a melhor diversificação não-correlacionada com cripto?
   - Dilema C: Qual o risco de dispersão de atenção e capital ao rodar 5 ou 6 desks com banca pequena?
   - Dilema D: Como atingir os $10/dia com segurança sem sobre-alavancagem?
====================================================================================================
"""

questions = {
    "council_verdict_eth_5m": Choice(
        instructions="JEV e Conselho Quant: Você aprova a criação imediata do 'Desk ETH 5m' (Polymarket eth-updown-5m) utilizando confirmação de momentum e Lead-Lag do BTC?",
        criteria={
            "STRONGLY_APPROVED_IMMEDIATE": "Aprovado com Louvor: Ethereum tem altíssima liquidez na Polymarket, espelha a infraestrutura pronta do Desk 1/2 e adiciona de 4 a 8 oportunidades de micro-lucro diário com correlação benéfica.",
            "APPROVE_ONLY_ON_15M": "Aprovar apenas no 15m da Kalshi (KXETH15M) devido a menor ruído.",
            "REJECT_REDUNDANT": "Rejeitar: Redundante com o Desk 1 de Bitcoin."
        }
    ),
    "council_verdict_gold_15m": Choice(
        instructions="JEV e Conselho Quant: Qual o parecer sobre a criação do 'Desk Gold 15m' (Kalshi KXGOLD15M) como âncora de descorrelação física contra quedas do mercado cripto?",
        criteria={
            "APPROVED_EXCELLENT_DIVERSIFICATION": "Aprovado como Âncora Macroeconômica: Ouro tem volatilidade suave, oráculo de alta precisão (CME/LBMA), sem caudas explosivas de dutos como NatGas e funciona em regime 24/5 não-correlacionado ao Bitcoin.",
            "MODERATE_VALUE": "Valor Moderado: Operar apenas se os spreads do livro da Kalshi forem inferiores a 3 centavos.",
            "REJECT_TOO_SLOW": "Rejeitar: Ouro tem baixa volatilidade intradiária para opções binárias de 15 minutos."
        }
    ),
    "council_verdict_xrp_or_sol15m": Choice(
        instructions="JEV e Conselho Quant: Entre XRP 5m (Polymarket) e Solana 15m (Kalshi KXSOL15M), qual ativo oferece melhor alpha complementar?",
        criteria={
            "PREFER_KALSHI_SOL15M": "Preferir Kalshi SOL 15m (KXSOL15M): A Solana possui volatilidade direcional limpa e 15m na Kalshi evita as armadilhas de reversão de 5m.",
            "PREFER_POLYMARKET_XRP5M": "Preferir Polymarket XRP 5m: O livro de ofertas do XRP tem forte assimetria de varejo.",
            "NEITHER_STICK_TO_MAJORS": "Nenhum dos dois: Manter foco estrito em BTC, ETH e Ouro."
        }
    ),
    "swarm_capital_safety": Choice(
        instructions="Com uma banca real de ~$30 USD, rodar um enxame de 4 a 5 desks com apostas de $0.50 a $1.00 USD é matematicamente seguro contra risco de ruína?",
        criteria={
            "MATHEMATICALLY_SOUND_LOW_RUIN": "Matematicamente Seguro e Ótimo: Com apostas de $0.50 a $1.00 isoladas por Shards independentes, Take-Profit a 88¢ e Stop-Loss proativo, o risco de ruína é < 0.1%, enquanto a taxa de aprendizado e giro de capital é máxima.",
            "BORDERLINE_RISK": "Risco Limítrofe: Recomendado reduzir para no máximo 3 desks até a banca atingir $50 USD.",
            "DANGEROUS_OVEREXPOSURE": "Perigoso: A banca é muito pequena para mais de 2 desks."
        }
    ),
    "roadmap_to_10_usd_daily": Choice(
        instructions="Qual é a rota quantitativa mais rápida, consistente e profissional para o trader alcançar a meta de +$10 USD líquidos por dia?",
        criteria={
            "TRIFECTA_PLUS_COMMODITIES": "A Tríade Cripto (BTC 5m + ETH 5m + SOL 5m) gerando $4-$6/dia + As Duas Commodities Kalshi (NatGas 15m + Ouro 15m) gerando $4-$6/dia = Meta de $10/dia atingida com 5 fontes independentes de alpha.",
            "CONCENTRATE_ON_BTC_ONLY": "Concentrar tudo no Bitcoin aumentando o stake para $5 por trade.",
            "WAIT_FOR_MORE_CAPITAL": "Não expandir até aportar $500 USD adicionais."
        }
    ),
    "council_overall_score": Score(
        instructions="Forneça a nota final do Conselho JEV (1.0 a 5.0) para a arquitetura do ecossistema multi-desk com micro-apostas para meta de $10/dia.",
        criteria=[
            "1.0 - Estrutura amadora com alto risco de ruína",
            "2.0 - Estrutura funcional mas com gargalos severos",
            "3.0 - Estrutura quantitativa sólida",
            "4.0 - Arquitetura de nível institucional: diversificação ótima, gestão de risco rigorosa e expectativas realistas",
            "5.0 - Masterclass de Finanças Quantitativas: Enxame descorrelacionado perfeito com payoff assimétrico positivo"
        ]
    )
}

print("=" * 95)
print("  🏛️ ENVIANDO DOSSIÊ COMPLETO PARA O CONSELHO DE INTELIGÊNCIAS QUANTITATIVAS JEV...")
print("=" * 95)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[+] Veredito do Conselho JEV recebido em {elapsed:.2f}s!\n")

council_results = {}
for q_name, ans in resp.answers.items():
    if hasattr(ans, "choice"):
        print(f"📌 {q_name}:")
        print(f"   Decisão do Conselho: {ans.choice} (Confiança: {ans.confidence:.1%})")
        print("   Probabilidades:")
        for opt, p in ans.probabilities.items():
            print(f"     - {opt}: {p:.1%}")
        print()
        council_results[q_name] = {
            "verdict": ans.choice,
            "confidence": ans.confidence,
            "probabilities": ans.probabilities
        }
    elif hasattr(ans, "score"):
        print(f"⭐ {q_name}: {ans.score:.2f} / 5.00 (Confiança: {ans.confidence:.1%})")
        print("   Probabilidades do Score:")
        for k, p in ans.probabilities.items():
            print(f"     - Nível {k}: {p:.1%}")
        print()
        council_results[q_name] = {
            "score": ans.score,
            "confidence": ans.confidence,
            "probabilities": ans.probabilities
        }

with open("jev_council_of_intelligences_verdict.json", "w", encoding="utf-8") as f:
    json.dump(council_results, f, indent=2)

print("[✓] Parecer oficial do Conselho JEV gravado com sucesso em jev_council_of_intelligences_verdict.json!")
