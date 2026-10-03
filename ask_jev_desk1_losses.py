import os
import json
import time
from dotenv import load_dotenv

load_dotenv(".env")
from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

dossier = """
AUDITORIA QUANTITATIVA DAS ULTIMAS 3 DERROTAS DO DESK 1 (POLYMARKET BTC 5M LIVE)
Conta Funder Safe: 0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c
Modo: DINHEIRO REAL NA POLYGON (CLOB V2)

DETALHAMENTO FORENSE DAS 3 DERROTAS:

1. CICLO 155 (2026-09-30 09:35 UTC):
   - Strike Chainlink: $83,037.32 | Entrada: DOWN @ $0.47 | Stake: $2.11
   - Fechamento: Spot $83,100.37 (Delta +$63.05) | TWAP $83,048.77 (Delta +$11.45)
   - Vencedor Oficial Polymarket: UP
   - Resultado: DERROTA (-$2.11)
   - Causa: Reversão Direcional Forte. O BTC disparou +$63 contra a posição DOWN aos 240s-300s.
   - Falha de Defesa: Nem o Hedge Bonereaper nem o Stop-Loss foram executados; a posição segurou até 100% de perda.

2. CICLO 156 (2026-10-01 07:05 UTC):
   - Strike Chainlink: $84,255.23 | Entrada: DOWN @ $0.35 | Stake: $2.22
   - Fechamento: Spot $84,243.31 (Delta -$11.92) | TWAP $84,244.51 (Delta -$10.72)
   - Vencedor Oficial Polymarket: UP (divergência com Chainlink local por ~$11)
   - Resultado: DERROTA (-$2.22)
   - Causa: 'Photofinish' de Margem Mínima (< $12). O mercado fechou colado no strike. A amostragem do oráculo oficial da Polymarket divergiu do snapshot local por segundos.

3. CICLO 158 (2026-10-02 03:35 UTC):
   - Strike Chainlink: $84,880.36 | Entrada: UP @ $0.48 | Stake: $2.02
   - Fechamento: Spot $84,873.78 (Delta Spot -$6.58) | TWAP $84,897.46 (Delta TWAP +$17.10)
   - Vencedor Oficial Polymarket: DOWN
   - Resultado: DERROTA (-$2.02)
   - Causa: Divergência Crítica TWAP vs Spot Final. O TWAP acumulado fechou positivo (+$17.10), mas o Spot na vela fechou -$6.58 abaixo do strike no segundo final. A Polymarket resolve no Spot final.
   - Falha de Defesa: Nenhuma defesa acionada nos segundos finais (270s-295s) apesar do Spot enfraquecer.

TOTAL PERDIDO NAS 3 DERROTAS: -$6.35
PADRÃO COMUM IDENTIFICADO:
1. 2 das 3 derrotas (Ciclo 156 e 158) ocorreram em zonas de 'Photofinish' (|Delta Spot| < $12).
2. Em todas as 3 derrotas, o bot segurou a cota até virar $0.00, sem resgatar valor residual via Stop-Loss na CLOB aos 270s-290s.
3. Divergência entre TWAP e Spot Final causou o erro no Ciclo 158.
"""

client = TypeSafeClient()

questions = {
    "root_cause_diagnosis": Choice(
        instructions="Qual é a principal causa raiz estrutural das 3 derrotas do Desk 1?",
        criteria={
            "tight_photofinish_and_zero_stoploss": "ZONA DE PHOTOFINISH E FALTA DE STOP-LOSS TARDIO: 2 de 3 derrotas fecharam coladas no strike (< $12) onde TWAP e Spot divergem, e a falta de liquidação aos 275s-290s causou 100% de perda desnecessária.",
            "oracle_latency_only": "APENAS LATÊNCIA DE ORÁCULO: O oráculo da Polymarket é imprevisível.",
            "directional_bias_failure": "FALHA DE MODELO DIRECIONAL: O modelo errou completamente a tendência macro."
        }
    ),
    "bonereaper_stoploss_calibration": Choice(
        instructions="Como o Bonereaper Stop-Loss deve ser calibrado para o Desk 1 evitar perdas de 100% (-$2.00) quando o preço/delta entra em colapso aos 260s-285s?",
        criteria={
            "activate_late_sl_if_bid_above_15c": "STOP-LOSS TARDIO ATIVO (260s-285s): Se aos 260s+ o Spot reverter o delta além de -$10 ou o Best Bid cair para $0.20-$0.30, vender imediatamente a mercado para resgatar $0.80-$1.20 (reduzindo a perda de -$2.00 para -$0.80).",
            "keep_hold_to_expiration": "MANTER ATÉ A EXPIRAÇÃO: Não vender antecipado, pois pode haver reversão no último segundo.",
            "hedge_only": "USAR APENAS HEDGE NA PONTA OPOSTA: Comprar o lado oposto em vez de vender."
        }
    ),
    "spot_vs_twap_alignment_gate": Choice(
        instructions="No Ciclo 158, o TWAP era +$17 mas o Spot fechou em -$6.58 (derrota). Devemos exigir alinhamento estrito entre Spot e TWAP no fechamento?",
        criteria={
            "strict_dual_alignment_required": "ALINHAMENTO DUPLO ESTRITO: Exigir que tanto o Spot Delta quanto o TWAP Delta estejam no MESMO lado do strike aos 240s-280s, caso contrário acionar saída defensiva ou veto.",
            "rely_on_twap_only": "CONFIAR APENAS NO TWAP: O TWAP é mais estável.",
            "rely_on_spot_only": "CONFIAR APENAS NO SPOT: Ignorar o TWAP completamente."
        }
    ),
    "photofinish_risk_score": Score(
        instructions="Em uma escala de 1 a 5, quão perigoso é manter posições abertas sem hedge/saída quando |Delta Spot| é menor que $15 nos últimos 30 segundos da vela?",
        criteria=[
            "1.0 = Seguro, ruído irrelevante.",
            "2.0 = Risco baixo de descolamento.",
            "3.0 = Risco moderado.",
            "4.0 = Risco elevado de flip no oráculo.",
            "5.0 = RISCO EXTREMO DE FLIP: Em deltas < $15, a volatilidade de 5 segundos e a amostragem do oráculo UMA/Chainlink tornam o resultado uma moeda ao ar (50/50)."
        ]
    ),
    "synthesis_recommendation": Noul(
        instructions="Apresente uma síntese conclusiva com as recomendações de engenharia para o Desk 1."
    )
}

print("-> Enviando dossiê de derrotas do Desk 1 ao JEV...")
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

with open("desk1_losses_jev_audit.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("Salvo em desk1_losses_jev_audit.json")
