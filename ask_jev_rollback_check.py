# -*- coding: utf-8 -*-
"""
CONSULTA DIRETA AO JEV (TypeSafe SystemOne):
Pergunta explícita: O JEV recomenda voltar atrás em alguma alteração ou código recente?
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
QUESTIONAMENTO EXPLÍCITO DO USUÁRIO:
"O JEV recomenda voltarmos atrás em alguma coisa do código?"

ESTADO ATUAL DO SISTEMA:
1. Desk 1 (Polymarket BTC 5m LIVE):
   - 102 Vitórias / 47 Derrotas (68.5% Win Rate real). Saldo $25.79 USDC.
   - Filtros: Deadband $15, Drift Binance >= -5, Spread <= 0.06, Microprice ponderado, Sweeper 255s-285s.
2. Desk 2 (Polymarket SOL 5m LIVE):
   - Pyth Network + Binance SOLUSDT, deadband 5.0 bps.
3. Desk 3 (Kalshi BTC 15m LIVE):
   - Conexão RSA-PSS oficial CFTC, Shard 2.
4. Desk 4 & 5 (Kalshi NatGas EIA + 15m LIVE):
   - EIA Shield na quarta-feira, modelo físico NOAA/GFS HDD/CDD.
5. Desk 6 (Yield Harvester 98¢ + LP Rewards 2.0 PAPER):
   - Adicionada fórmula lihanyu81/polymarket_lp_tool (S = ((v-s)/v)^2 * size).
   - Scanner de 87 mercados de incentivo oficial da Polymarket.
6. Desk 7 (Cross-Market Macro Arbitrageur RADAR):
   - Adicionada matriz de taxas exatas do HarrierOnChain (CFTC parabólica Kalshi + 20 bps taker Poly).
7. Desk 11 (Kalshi S&P 500 15m Momentum PAPER):
   - KXINX15M / KXINXU com filtro de delta mínimo 5.0 pts.
8. Desk 12 (Weather & METAR Airport Arbitrage PAPER):
   - Monitoramento ASOS NOAA a cada 60s em Austin (KAUS) e Miami (KMIA).
   - Separação estrita entre Máxima Diária monotônica e contratos horários (exige timestamp report_time >= close_time).
9. Whale Flow Monitor (Whale Radar):
   - Escuta trades CLOB a cada 6s, categoriza ordens >= $200 / $1000.
10. Infraestrutura:
    - 13 processos ativos em segundo plano no Windows.
    - DuckDB HTTPFS para consultas em streaming sobre 216 GB do Hugging Face.
"""

questions = {
    "recommend_any_rollback": Choice(
        instructions="Com base no rigor quantitativo e na preservação de capital, você recomenda reverter ou desativar alguma das implementações recentes?",
        criteria={
            "no_rollback_recommended": "Nenhuma reversão recomendada: Todos os 13 processos possuem papéis complementares bem definidos, salvaguardas fail-closed estritas, stakes controlados ($1.00) e os desks novos estão em modo PAPER ou RADAR, não colocando em risco o capital real.",
            "partial_rollback_or_trim": "Reversão parcial ou pausa preventiva recomendada: Algum componente específico apresenta risco desnecessário ou consome recursos sem gerar alpha suficiente.",
            "urgent_full_rollback": "Reversão urgente necessária: Há falha estrutural que ameaça o saldo real da conta."
        }
    ),
    "component_to_watch_most": Choice(
        instructions="Se houvesse algum componente que merecesse a maior cautela operacional ou ajuste fino no futuro imediato, qual seria?",
        criteria={
            "keep_running_as_is": "Manter tudo rodando como está: O equilíbrio atual entre Desks LIVE (1, 2, 3, 5) e Desks PAPER/RADAR (4, 6, 7, 8, 9, 11, 12, Whale) é ideal.",
            "monitor_system_load": "Atenção à carga do sistema: 13 processos paralelos em Python no Windows exigem verificar se o uso de CPU/RAM permanece baixo.",
            "tighten_whale_radar_coupling": "Cuidado com acoplamento do Whale Radar: Garantir que os alertas de baleia continuem apenas informativos e nunca interfiram na execução em microsegundos do Desk 1.",
            "desk12_basis_risk_tuning": "Calibração fina do Desk 12: Monitorar a liquidação dos primeiros contratos de clima para confirmar 100% de convergência entre ASOS e The Weather Company."
        }
    )
}

print("=" * 80)
print("🤖 CONSULTANDO JEV: O JEV RECOMENDA VOLTAR ATRÁS EM ALGUMA COISA?")
print("=" * 80)

t0 = time.time()
try:
    resp = client.system_one(state=dossier, questions=questions)
    elapsed = time.time() - t0
    print(f"\n[OK] Resposta recebida do JEV em {elapsed:.2f} segundos!")
    print("=" * 80)

    for qname, ans in resp.answers.items():
        print(f"\n📌 PERGUNTA: {qname.upper()}")
        print(f"   ESCOLHA DO JEV: {ans.choice.upper()}")
        print(f"   CONFIANÇA: {ans.confidence * 100:.1f}%")
        print(f"   PROBABILIDADES:")
        for opt, prob in ans.probabilities.items():
            print(f"     • {opt}: {prob * 100:.1f}%")

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_rollback_recommendation_verdict.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.time(),
            "elapsed_sec": round(elapsed, 2),
            "results": {k: {"choice": v.choice, "confidence": round(v.confidence, 3), "probabilities": {p_k: round(p_v, 3) for p_k, p_v in v.probabilities.items()}} for k, v in resp.answers.items()}
        }, f, indent=2, ensure_ascii=False)
    print(f"\n[SALVO] Veredito do JEV salvo em: {output_path}")

except Exception as e:
    print(f"[ERRO] {e}")
    sys.exit(1)
