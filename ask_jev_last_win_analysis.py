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

key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
client = TypeSafeClient(api_key=key)

dossier = """
================================================================================
AUDITORIA QUANTITATIVA FORENSE: ÚLTIMA VITÓRIA REAL NO DESK 1 (POLYMARKET BTC 5M)
Data/Hora da Operação: 2026-09-29 12:20:00 às 12:25:10 UTC (08:20 - 08:25 ET)
Ciclo: #153 | Série Oficial: btc-updown-5m-1790680800
Modo: DINHEIRO REAL (LIVE TRADING NA REDE POLYGON)

1. PARÂMETROS DE MERCADO & ORÁCULOS:
   - Strike K (Chainlink): $83,990.07
   - Spot no Ponto de Decisão (135s): $84,015.50 (Delta: +$25.43 acima do strike)
   - Deadband Dinâmico Aplicado: 2.1 bps (~$17.64) -> Delta (+25.43) superou deadband
   - Convergência Binance: Drift positivo confirmado (sem divergência adversa)
   - Oráculo TWAP: Acumulado positivo (+21.37 final), sem armadilha de reversão

2. ENTRADA PRIMÁRIA SNIPER (135s):
   - Token Selecionado: UP (Yes)
   - Preço de Execução no CLOB: $0.40 (40¢) por cota
   - Enquadramento de Preço: Perfeito dentro do canal Sniper ($0.35 a $0.55)
   - Dimensionamento Fractional Kelly (25% Kelly): $2.06 USD para banca de $25.79
   - Quantidade Comprada: 5.15 cotas
   - Transação de Compra na Polygon: 0x596c4f36e5bde010c8ab0f50f345e02d7d7edfc5c02bf2e54cb797b20da02f08

3. GESTÃO SIRMARTINGALE TAKE-PROFIT ANTECIPADO (170s+):
   - O preço do spot continuou em alta atingindo $84,025.61
   - O Best Bid no livro L2 da Polymarket disparou para $0.97 (97¢)
   - Gatilho Take-Profit disparado (regra >= 86¢)
   - Ação do Robô: Venda limite agressiva antecipada a $0.97 no book
   - Cotas Vendidas: 5.15 cotas @ $0.97
   - Payout Resgatado Antecipadamente: $5.00 USD
   - Transação de Venda na Polygon: 0x557f5a4498eba2a1643b0afc63025b19da103387e127262ee93647faf1e661e6

4. RESULTADO FINANCEIRO & PAYOFF:
   - Custo Total (Stake): $2.06 USD
   - Retorno Bruto (Payout): $5.00 USD
   - Lucro Líquido Real (PnL): +$2.94 USD
   - ROI Percentual do Trade: +142.7% em menos de 4 minutos
   - Nova Banca Polymarket: $28.6279 USD (Lucro líquido acumulado: +$7.63 USD / +36.3% sobre depósito de $21.00)
   - Resolução Oficial do Oráculo (300s): UP venceu (Strike 83.990 vs Spot 84.025 / TWAP 84.011)
================================================================================
"""

questions = {
    "execution_quality_rating": Choice(
        instructions="Qual é a avaliação do JEV sobre a qualidade técnica de execução dessa operação (Entrada a 40¢ com 25% Kelly e Saída Take-Profit a 97¢ no CLOB)?",
        criteria={
            "flawless_institutional_execution": "Execução Institucional Impecável: Entrada na assimetria favorável (40¢ = EV positivo), dimensionamento matemático exato de Kelly, e saída antecipada a 97¢ travando +142.7% sem correr o risco de cauda dos últimos segundos.",
            "suboptimal_early_exit": "Saída Precipitada: Deveria ter esperado o settlement final a $1.00 para capturar os 3¢ restantes.",
            "excessive_risk": "Risco Excessivo: A aposta de $2.06 foi grande demais para a banca de $25.79."
        }
    ),
    "take_profit_efficiency_score": Score(
        instructions="Avalie de 1.0 a 5.0 a eficiência matemática de realizar o Take-Profit a 97¢ (capturando 97% do payout máximo) vs segurar a cota até os 300s sujeita a um flash crash de oráculo.",
        criteria=[
            "1.0 - Péssimo: Deixou dinheiro na mesa sem justificativa.",
            "2.0 - Fraco: Lucro reduzido.",
            "3.0 - Razoável: Proteção básica.",
            "4.0 - Muito Bom: Boa relação de proteção.",
            "5.0 - Ótimo Teórico (Sharpe Máximo): Capturar 97% do upside eliminando 100% da variância final maximiza a taxa de crescimento logarítmico da banca (Kelly Criterion)."
        ]
    ),
    "kelly_sizing_safety": Choice(
        instructions="O dimensionamento de $2.06 USD (8.0% da banca de $25.79) utilizando 25% Fractional Kelly respeitou adequadamente os guardrails de risco de ruína?",
        criteria={
            "optimal_fractional_kelly": "Ótimo e Seguro: 25% Kelly com piso de $1.00 e teto de $2.50 previne drawdown catastrófico enquanto acelera o efeito dos juros compostos em vitórias consecutivas.",
            "too_aggressive": "Muito Agressivo: Deveria ter apostado no máximo $1.00 (stake fixo estrito).",
            "too_conservative": "Muito Conservador: Deveria ter alocado mais capital dada a alta convicção."
        }
    ),
    "impact_on_long_term_ev": Score(
        instructions="De 1.0 a 5.0, qual é o impacto a longo prazo dessa estrutura de trade (+142.7% de ganho vs stop-loss de -48% como o de ontem) na expectativa matemática do sistema?",
        criteria=[
            "1.0 - Negativo: Relação risco/retorno invertida.",
            "2.0 - Marginal: Mal cobre os custos de transação.",
            "3.0 - Positivo Simples: Lucro modesto.",
            "4.0 - Robusto: Payoff assimétrico sustentável.",
            "5.0 - Dominante / Alfa Superior: Ganhos médios de +140% combinados com defesas onde se resgata 50% do capital geram uma curva de capital convexa de alto Sharpe."
        ]
    )
}

print("=" * 80)
print("ENVIANDO DADOS DO TRADE #153 (+142.7% ROI) PARA AUDITORIA DA IA JEV...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer oficial do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_execution": {
        "choice": res.answers["execution_quality_rating"].choice,
        "confidence": res.answers["execution_quality_rating"].confidence,
        "probs": res.answers["execution_quality_rating"].probabilities
    },
    "q2_take_profit_score": {
        "score": res.answers["take_profit_efficiency_score"].score,
        "confidence": res.answers["take_profit_efficiency_score"].confidence
    },
    "q3_kelly": {
        "choice": res.answers["kelly_sizing_safety"].choice,
        "confidence": res.answers["kelly_sizing_safety"].confidence,
        "probs": res.answers["kelly_sizing_safety"].probabilities
    },
    "q4_long_term_ev": {
        "score": res.answers["impact_on_long_term_ev"].score,
        "confidence": res.answers["impact_on_long_term_ev"].confidence
    }
}

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_last_win_audit_verdict.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
