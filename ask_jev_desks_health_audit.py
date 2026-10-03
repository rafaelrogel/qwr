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
AUDITORIA OPERACIONAL E FORENSE COMPLETA: 12 DESKS ATIVAS + RADAR WHALE NO AGY SYSTEM
Data/Hora: 2026-09-29 06:35 UTC (02:35 ET)
Tempo Contínuo em Execução: 7 horas e 40 minutos (Iniciado em 28/09/2026 23:54 UTC)

1. ARQUITETURA DE EXECUÇÃO E PROCESSOS:
   - Todos os 14 processos Python permanecem ativos e saudáveis (0 crashes, 0 exceptions não tratadas).
   - Dashboard Server Web (PID 3772): Agregando dados em tempo real a cada 15s.
   - PnL Polymarket Real: Depósito $21.00 -> Saldo Atual $25.79 (+22.8% lucro real acumulado).
   - PnL Kalshi Real: Shard 0 ($1.31) + Shard 2 ($9.05) = $10.36 caixa + $5.87 posições = $16.23 valor consolidado.

2. ESTADO OPERACIONAL POR DESK:
   [Desk 1 - Polymarket BTC 5m LIVE]:
     - Status: Ativo em cada vela de 5 minutos.
     - Proteções Ativas: Deadband dinâmico scale-invariant (2.1 bps), Convergência Binance Drift, TWAP Oracle Trap Shield, Filtro L2 CLOB Spread (<= 0.06), Book Imbalance, Teto de Preço ($0.55), CVD Watcher, Cascata de Liquidações.
     - Histórico: 152 ciclos. Última operação com dinheiro real em 28/09 17:03 acionou Defesa (Stop Loss antecipado no CLOB a $0.25), salvando capital ($6.21 resgatados). Zero operações forçadas durante a noite devido à filtragem rigorosa de ruído.

   [Desk 2 - Polymarket SOL 5m LIVE]:
     - Status: Ativo no ciclo 5m.
     - Estado Atual: Delta intra-vela no ruído (+$0.010 < Deadband $0.060).
     - Comportamento: Preservando capital rigorosamente sem forçar ordens no ruído de topo de livro.

   [Desk 3 - Kalshi BTC 15m LIVE]:
     - Status: Ativo no ciclo 15m. Market discovery reparado com sucesso (query primária status=open).
     - Estado Atual: Ticker KXBTC15M identificado. Avalia aos 450s.
     - Gargalo Histórico: Ficou 6 dias sem operar porque REQUIRE_PRIOR_CANDLE_TREND veta entradas quando a vela 15m anterior da Binance fecha no sentido oposto. Na vela atual (06:30-06:44), o BTC sobe +$73 (UP), mas a vela anterior (06:15-06:29) fechou em -1.3 bps (-$10.95), configurando ruído plano que ainda assim aciona o veto estrito.

   [Desk 4 - Kalshi NatGas EIA Semanal PAPER]:
     - Status: Daemon ativo calculando inventário EIA e graus-dia HDD/CDD. Aguardando relatório semanal EIA de quinta-feira.

   [Desk 5 - Kalshi NatGas 15m LIVE]:
     - Status: Ativo e avaliando Henry Hub NYMEX a cada 15m. Delta atual $0.0029 dentro da deadband de $0.0040. Preservando capital.

   [Desk 6 - Yield Harvester PAPER]:
     - Status: Ativo varrendo a cada 600s oportunidades de LP rewards e spread theta em Polymarket.

   [Desk 7 - Cross-Arb Macro Scanner RADAR]:
     - Status: Ativo varrendo divergências macro entre Polymarket e Kalshi a cada ciclo.

   [Desk 8 - Polymarket ETH 5m PAPER]:
     - Status: Ativo monitorando ciclo 5m ETH. Delta $2.67 em deadband $2.16, aguardando liquidez CLOB.

   [Desk 9 - Kalshi Gold 15m PAPER]:
     - Status: Ativo monitorando ouro 15m (COMEX/Pyth).

   [Desk 11 - Kalshi SPX 15m PAPER]:
     - Status: AGUARDANDO ABERTURA DE MERCADO. O mercado à vista do S&P 500 (NYSE/CBOE) opera apenas das 09:30 às 16:00 ET. Às 02:35 ET o mercado cash está fechado.

   [Desk 12 - Weather METAR 14 Aeroportos PAPER]:
     - Status: Ativo varrendo 14 aeroportos a cada 300s. Horário da madrugada nos EUA (02:35 ET), onde temperaturas estão nas mínimas noturnas e não nas máximas diurnas (que ocorrem entre 15h e 17h locais).

   [Radar Whale Flow]:
     - Status: Ativo em streaming CLOB. 105 baleias detectadas, $172,172 USD rastreados, viés institucional monitorado.
================================================================================
"""

questions = {
    "system_health_consensus": Choice(
        instructions="Com base nos logs e telemetria de 7h40m ininterruptas, todos os 12 desks e o radar whale estão funcionando rigorosamente como deveriam do ponto de vista quantitativo?",
        criteria={
            "all_functioning_as_intended": "Todos Funcionando Como Deveriam: A aparente 'inatividade' de trades noturnos é o funcionamento perfeito dos filtros fail-closed (deadband dinâmico, regime noturno de baixa volatilidade, mercados fechados como SPX e madrugada nas estações METAR). O capital está 100% protegido e os daemons estão vivos.",
            "critical_flaw_detected": "Falha Crítica Detectada: Há um travamento ou deadlock que impede a execução mesmo quando as condições seriam favoráveis.",
            "unbalanced_risk": "Risco Desbalanceado: Algum desk está exposto a risco desnecessário."
        }
    ),
    "desk3_prior_candle_calibration": Choice(
        instructions="No Desk 3 (Kalshi BTC 15m LIVE), o filtro Jev de Vela Anterior vetou trades por 6 dias e vetará uma alta de +$73 porque a vela anterior caiu apenas -1.3 bps (-$10). Qual é a calibração quantitativa ótima para este filtro?",
        criteria={
            "apply_minimum_bps_threshold": "Adotar Piso Mínimo de Ruído (Threshold de 3 a 5 bps): Não vetar se a vela anterior foi essencialmente plana (|retorno| < 3.0 bps). Tratar velas de -1.3 bps como ruído neutro e permitir que o drift intra-vela forte (> 40 bps) prevaleça.",
            "keep_strict_binary_direction": "Manter Direção Binária Estrita: Manter veto absoluto se Open > Close por qualquer fração de centavo, priorizando 100% win rate mesmo que passe semanas sem operar.",
            "disable_filter_completely": "Desativar o Filtro: Remover completamente o filtro de vela anterior e confiar unicamente no deadband."
        }
    ),
    "market_hours_and_seasonal_justification": Choice(
        instructions="A inatividade atual do Desk 11 (SPX 15m) e do Desk 12 (Weather METAR) durante a madrugada nos EUA é justificada?",
        criteria={
            "structurally_justified": "Estruturalmente Justificada: SPX cash só tem liquidação e liquidez em horário regular NYSE (13:30-20:00 UTC), e as quebras de temperatura máxima nos 14 aeroportos ocorrem no aquecimento solar das 19:00-23:00 UTC. Tentar forçar trades na madrugada seria alucinação algorítmica.",
            "unjustified_bug": "Injustificada: Os robôs deveriam estar negociando mesmo fora dos horários de pico."
        }
    ),
    "capital_preservation_score": Score(
        instructions="Avalie de 1.0 a 5.0 o rigor e a eficácia da governança de preservação de capital do sistema (deadbands dinâmicos, stop-loss no CLOB, filtros L2 e salvaguarda fail-closed).",
        criteria=[
            "1.0 - Fraco: Sistema quebra facilmente por slippage.",
            "2.0 - Básico: Apenas stop-loss simples.",
            "3.0 - Razoável: Deadband fixo.",
            "4.0 - Robusto: Deadband dinâmico com convergência multi-feed.",
            "5.0 - Nível Institucional Excelente: Fail-closed, microestrutura L2, TWAP anti-trap, CVD, regime diurno e proteção matemática de banca."
        ]
    ),
    "priority_action_recommendation": Choice(
        instructions="Qual é a principal recomendação prática e imediata para otimização do sistema neste momento?",
        criteria={
            "calibrate_desk3_noise_threshold": "Calibrar Filtro de Ruído no Desk 3: Implementar o piso de 3-5 bps na vela anterior para destravar entradas com alto drift sem abrir mão da proteção contra exaustão, mantendo os outros 11 desks como estão.",
            "change_nothing_let_it_run": "Não Alterar Nada: Deixar o sistema exatamente como está e aguardar o horário nobre dos mercados americanos (13:30 UTC para SPX e 19:00 UTC para METAR).",
            "increase_stakes": "Aumentar Stakes: Dobrar o tamanho das apostas nos desks ao vivo."
        }
    )
}

print("=" * 80)
print("ENVIANDO AUDITORIA DOS 12 DESKS PARA O JEV SYSTEMONE...")
print("=" * 80)

t0 = time.time()
res = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n[OK] Parecer e Consenso do JEV recebido em {elapsed:.2f}s!\n")

out = {
    "timestamp": time.time(),
    "elapsed_sec": round(elapsed, 2),
    "q1_health": {"choice": res.answers["system_health_consensus"].choice, "confidence": res.answers["system_health_consensus"].confidence, "probs": res.answers["system_health_consensus"].probabilities},
    "q2_desk3": {"choice": res.answers["desk3_prior_candle_calibration"].choice, "confidence": res.answers["desk3_prior_candle_calibration"].confidence, "probs": res.answers["desk3_prior_candle_calibration"].probabilities},
    "q3_hours": {"choice": res.answers["market_hours_and_seasonal_justification"].choice, "confidence": res.answers["market_hours_and_seasonal_justification"].confidence, "probs": res.answers["market_hours_and_seasonal_justification"].probabilities},
    "q4_score": {"score": res.answers["capital_preservation_score"].score, "confidence": res.answers["capital_preservation_score"].confidence},
    "q5_priority": {"choice": res.answers["priority_action_recommendation"].choice, "confidence": res.answers["priority_action_recommendation"].confidence, "probs": res.answers["priority_action_recommendation"].probabilities}
}

with open("jev_desks_health_verdict.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2))
