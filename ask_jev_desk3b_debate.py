import os
import json
import time
from dotenv import load_dotenv

load_dotenv(".env")
from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

with open("desk3b_btc15m_paper_journal.json", "r", encoding="utf-8") as f:
    journal = json.load(f)

with open("desk3b_btc15m_paper_state.json", "r", encoding="utf-8") as f:
    state = json.load(f)

dossier = f"""
AUDITORIA QUANTITATIVA E FORENSE DO DESK 3B (BTC 15M POLYMARKET PAPER)
Data: 2026-10-01 19:20 UTC
Modo: PAPER HYPER-REALISTA (CLOB V2 ORDER BOOK REAL)

DESEMPENHO OBSERVADO:
- Total de Trades: {journal['total_trades']}
- Vitórias: {journal['wins']}
- Derrotas: {journal['losses']}
- Taxa de Acerto (Win Rate): {journal['win_rate']}%
- P&L Acumulado: ${journal['total_pnl']:.4f} USDC (Saldo: ${journal['current_balance']:.4f} vs $100.00 inicial)

DETALHAMENTO HISTÓRICO DAS OPERAÇÕES:
1. Trade #1 (09:45 UTC): Entrada UP @ $0.825 -> Payout $1.00 -> Lucro +$0.2121 (Delta +46.35) [VITÓRIA]
2. Trade #2 (13:15 UTC): Entrada DOWN @ $0.995 -> Payout $1.00 -> Lucro +$0.0050 (Delta -225.76) [VITÓRIA]
3. Trade #3 (15:15 UTC): Entrada DOWN @ $0.600 -> Payout $0.00 -> Prejuízo -$1.0000 (Delta -88.98) [DERROTA]
4. Trade #4 (15:45 UTC): Entrada DOWN @ $0.955 -> Payout $1.00 -> Lucro +$0.0471 (Delta -169.96) [VITÓRIA]
5. Trade #5 (16:58 UTC): Entrada DOWN @ $0.855 -> Payout $0.994 -> Lucro +$0.1626 (Delta -233.71) [VITÓRIA_TP]

PARADOXO MATEMÁTICO IDENTIFICADO:
- Apesar de 80% de Win Rate (4 vitórias em 5 trades), o P&L líquido é NEGATIVO (-$0.5732).
- Razão Estrutural: 3 das 4 vitórias compraram contratos caríssimos ($0.825, $0.855, $0.955 e $0.995).
  O retorno médio por vitória foi de apenas +$0.1067 (+10.6%), enquanto a única perda (Trade #3) custou -$1.0000 (-100%).
- Relação Risco/Retorno (Payoff Ratio): 1 perda apaga o lucro de ~9 a 10 vitórias seguidas a $0.95.
- Timing: Entrada ocorre em 700s (11m40s da vela de 15m), onde contratos vencedores já estão inflados pela CLOB.
- Defesa Inexistente no Trade #3: Ao comprar a $0.60, o robô não executou Stop-Loss quando o Delta reverteu, segurando a posição até a perda total ($0.00).
"""

client = TypeSafeClient()

questions = {
    "asymmetry_paradox_verdict": Choice(
        instructions="Avalie a gravidade do paradoxo matemático do Desk 3B (80% Win Rate com P&L negativo de -$0.57 devido a compras a preços inflados entre $0.85 e $0.995).",
        criteria={
            "critical_negative_expectancy": "CRÍTICO: Assimetria convexa reversa ('catar moedas na frente de um rolo compressor'). Mesmo com 80% ou 85% de win rate, a expectativa matemática a longo prazo é negativa.",
            "moderate_acceptable_friction": "MODERADO: O modelo está acertando a direção, precisando apenas de ajustes finos de spread.",
            "benign_sample_size_bias": "BENIGNO: Apenas ruído de amostragem curta de 5 trades."
        }
    ),
    "price_ceiling_recommendation": Choice(
        instructions="Qual deve ser a política de teto de preço (PRIMARY_MAX_PRICE) para o Desk 3B no ponto de entrada de 15m?",
        criteria={
            "strict_cap_0_65": "TETO ESTRITO $0.65: Limita entradas entre $0.35 e $0.65 (mesma regra do Desk 1), garantindo payoff mínimo de +$0.53 a +$1.85 por dólar arriscado.",
            "moderate_cap_0_75": "TETO MODERADO $0.75: Permite entradas até $0.75 se houver forte confirmação de delta (> 80 pts), garantindo ao menos +$0.33 de lucro por vitória.",
            "high_cap_0_88": "TETO ALTO $0.88: Aceita comprar contratos até $0.88 desde que haja Stop-Loss ativo.",
            "unrestricted": "SEM TETO: Continua comprando a $0.95-$0.99."
        }
    ),
    "timing_entry_optimization": Choice(
        instructions="O Desk 3B atualmente entra aos 700s (11m40s de 15m / 77% da vela). Como deve ser otimizado o timing de entrada?",
        criteria={
            "shift_earlier_450s_to_540s": "ANTECIPAR PARA 450s-540s (7m30s a 9m00s / 50-60% da vela): Permite capturar o contrato antes que a probabilidade seja totalmente precificada pela CLOB a 90c+, pagando preços mais justos ($0.45-$0.65).",
            "keep_700s_with_strict_price": "MANTER 700s COM TETO DE PREÇO: Continua aos 700s (alta certeza direcional), mas rejeita sumariamente qualquer contrato com ask > $0.65.",
            "two_stage_sniper": "ENTRADA EM DUAS ETAPAS (450s Primária + 720s Sweeper): Entrada inicial mais barata e reforço de final de vela se o delta confirmar."
        }
    ),
    "bonereaper_defense_requirement": Choice(
        instructions="Avalie a necessidade de implementar o módulo Bonereaper (Stop-Loss ativo de emergência) no Desk 3B, evitando que trades como o #3 virem $0.00.",
        criteria={
            "mandatory_bonereaper": "MANDATÓRIO: O Desk 3B precisa vender antecipadamente (liquidar a cota a $0.20-$0.40) assim que o delta reverter o sinal, resgatando 30% a 50% do capital.",
            "optional_hedging": "OPCIONAL: Hedge via compra da perna oposta é suficiente.",
            "unnecessary": "DESNECESSÁRIO: Deixar expirar a zero faz parte do modelo."
        }
    ),
    "intellectual_consensus_score": Score(
        instructions="Atribua uma nota de 1.0 (revisão superficial) a 5.0 (transformação estrutural indispensável) para a urgência de implementar Teto de Preço $0.65 + Stop-Loss Ativo no Desk 3B.",
        criteria=[
            "1.0 = Não alterar nada, continuar rodando como está.",
            "2.0 = Pequenos ajustes cosméticos no log.",
            "3.0 = Ajustar apenas o teto de preço.",
            "4.0 = Ajustar teto de preço e antecipar timing.",
            "5.0 = TRANSFORMAÇÃO ESTRUTURAL INDISPENSÁVEL: Teto $0.65 + Antecipação de timing + Stop-Loss Bonereaper para transformar win rate de 80% em P&L positivo robusto."
        ]
    ),
    "concluding_synthesis": Noul(
        instructions="Apresente uma síntese conclusiva em português resumindo os pilares do consenso quantitativo entre o JEV e o time de engenharia."
    )
}

print("-> Enviando dossiê do Desk 3B ao JEV (TypeSafe AI)...")
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

with open("desk3b_jev_debate_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("Resultados salvos em desk3b_jev_debate_results.json")
