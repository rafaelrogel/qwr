# -*- coding: utf-8 -*-
"""
CONSULTA QUANTITATIVA AO JEV (TypeSafe SystemOne):
Auditoria Forense Sistemática de Todos os Desks em Modo Paper e Live:
Desk 4 (NatGas EIA), Desk 5 (NatGas 15m), Desk 6 (Yield Harvester), Desk 8 (ETH 5m),
Desk 9 (Gold 15m), Desk 11 (SPX 15m), Desk 12 (Weather METAR).

Investigação:
1. Propagação do bug de paginação reversa da Kalshi API v2 para Desks 5, 9 e 11.
2. Armadilha do 'floor_strike=None' em contratos 'initialized' (Delta travado em 0.0).
3. Bug de indentação/escopo na Desk 8 (ETH 5m: UnboundLocalError em best_ask).
4. Limitações de varredura na Desk 6 (Kalshi status=open sem cursor).
5. Parecer e consenso de engenharia para correção padronizada.
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
DOSSIÊ FORENSE: DOUBLE-CHECK SISTEMÁTICO DE TODOS OS DESKS (PAPER & LIVE) & DEBATE COM O JEV
====================================================================================================
Após identificarmos o bug de paginação reversa e cegueira funcional no Desk 3 (Kalshi BTC 15m),
realizamos uma auditoria minuciosa em TODOS os demais desks do ecossistema.

DESCOBERTA CRÍTICA: O PROBLEMA SE REPETE SISTEMATICAMENTE EM MÚLTIPLOS DESKS!

1. DESK 9 (Kalshi Gold 15m - Paper / kalshi_gold_trader_15m.py):
   - Consulta: self.request("GET", "/markets", params={"series_ticker": "KXGOLD15M", "limit": 20})
   - Auditoria do estado ao vivo (kalshi_gold_15m_live_state.json):
     * Ticker selecionado: KXGOLD15M-26OCT011915-15 (vencimento às 19:15 ET de hoje!)
     * Tempo restante reportado: 56.951 segundos (15,8 HORAS no futuro)!
     * Delta: $0.00 | Total de Trades no histórico: 0.
   - Diagnóstico: O robô está preso monitorando um contrato que só vence daqui a 16 horas. 100% TRAVADO/CEGO!

2. DESK 5 (Kalshi NatGas 15m - Live / kalshi_natgas_trader_15m.py):
   - Consulta: self.request("GET", "/markets", params={"series_ticker": "KXNATGAS15M", "limit": 100})
   - Diagnóstico Forense:
     * A consulta com limit=100 retorna contratos futuros com status 'initialized'.
     * Em contratos 'initialized', a Kalshi NÃO publica o strike inicial ('floor_strike': None, sub: 'Target price: TBD').
     * O código faz: strike_price = float(floor_strike or spot_now) -> strike_price assume o spot_now!
     * Logo, delta = spot_now - strike_price = 0.0 SEMPRE!
     * O filtro de Deadband é acionado a cada 15 minutos: 'FILTRO DEADBAND: Drift $+0.0000 na zona morta (< $0.0040)'.
     * Resultado: 0 trades no histórico. 100% TRAVADO/CEGO!

3. DESK 11 (Kalshi SPX 500 15m - Paper / kalshi_spx_trader_15m.py):
   - Consulta: series_ticker="KXINX15M", que tem COUNT = 0 na Kalshi (série inexistente ou inativa).
   - O fallback KXINXHUD consulta limit=10 sem filtro de min_close_ts, trazendo contratos encerrados de ontem.
   - Resultado: 0 trades no histórico. 100% TRAVADO!

4. DESK 8 (Polymarket ETH 5m - Paper / eth_trader_5m.py):
   - O mercado existe na Polymarket CLOB ('eth-updown-5m-{window_ts}').
   - Porém, nas linhas 446-448:
       if spread_ok:
           best_ask = book["best_ask"]
       if PRIMARY_MIN_PRICE <= best_ask <= PRIMARY_MAX_PRICE:  # <-- INDENTAÇÃO ERRADA!
   - Se spread_ok for False (spread > 0.050), 'best_ask' não é definido e a linha seguinte gera UnboundLocalError!
   - Além disso, a verificação de preço tenta executar mesmo quando o spread gate falhou.

5. DESK 6 (Yield Harvester 98¢ - Paper / desk6_yield_harvester.py):
   - Linha 326: url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
   - Varre apenas os primeiros 100 mercados sem paginação cursor, ignorando milhares de contratos da Kalshi.

6. DESK 4 (Kalshi NatGas EIA Semanal) & DESK 12 (Weather METAR):
   - Desk 4: Modelo físico ativo. 20 vetos legítimos do JEV Co-Pilot ontem (não é bug de código).
   - Desk 12: Modelo METAR operando perfeitamente, aguardando pico térmico da tarde (14h-17h local).

====================================================================================================
"""

questions = {
    "dilemma1_systematic_kalshi_15m_refactor": Choice(
        instructions="JEV, avalie o Dilema 1: Devemos aplicar imediatamente a mesma arquitetura de descoberta em 3 camadas (Filtro Temporal min_close_ts + Ticker Determinístico ET) nas Desks 5 (NatGas 15m) e 9 (Gold 15m)?",
        criteria={
            "APPLY_3_LAYER_DISCOVERY_SYSTEMATICALLY": "APLICAR IMEDIATAMENTE EM TODOS OS DESKS KALSHI 15M: A falha é estrutural e idêntica à do Desk 3. Padronizar a descoberta com filtro temporal estrito (min_close_ts/max_close_ts) e ticker determinístico elimina a cegueira funcional em NatGas e Ouro de forma definitiva.",
            "APPLY_ONLY_TO_GOLD": "APLICAR APENAS AO OURO: Manter NatGas como está.",
            "MAINTAIN_CURRENT_WAIT_FOR_MARKET_OPEN": "NÃO ALTERAR: Aguardar a abertura dos mercados sem alterar os códigos."
        }
    ),
    "dilemma2_floor_strike_none_trap": Choice(
        instructions="JEV, avalie o Dilema 2: Como solucionar matematicamente a armadilha do 'floor_strike=None' em contratos 'initialized' na Kalshi, que zera o Delta (Delta=0) e bloqueia as entradas?",
        criteria={
            "REQUIRE_ACTIVE_STATUS_AND_VALID_STRIKE": "EXIGIR STATUS ATIVO E STRIKE VÁLIDO: Nunca permitir que strike_price assuma spot_now por default em contratos intradiários. Se floor_strike for None (mercado ainda não aberto ou strike não fixado), abortar a entrada e aguardar o início efetivo da vela para ler o strike oficial da Kalshi.",
            "USE_PREVIOUS_CANDLE_CLOSE_AS_STRIKE": "USAR FECHAMENTO DA VELA ANTERIOR COMO STRIKE ESTIMADO: Se floor_strike for None, assumir o fechamento da vela anterior da Binance/Yahoo como strike substituto.",
            "IGNORE_STRIKE_TRADE_ON_CVD_ONLY": "IGNORAR O STRIKE: Operar puramente pelo fluxo de ordens (CVD) sem comparar com o strike."
        }
    ),
    "dilemma3_desk8_eth_indentation_fix": Choice(
        instructions="JEV, avalie o Dilema 3: Qual é o parecer sobre a correção de indentação e escopo da Desk 8 (Polymarket ETH 5m)?",
        criteria={
            "FIX_INDENTATION_NEST_INSIDE_SPREAD_GATE": "CORRIGIR IMEDIATAMENTE (ANINHAR DENTRO DO SPREAD GATE): A verificação de preço deve estar estritamente aninhada dentro de 'if spread_ok:', evitando UnboundLocalError e garantindo que ordens só sejam avaliadas se o spread do livro for <= 0.050.",
            "LEAVE_AS_IS": "MANTER COMO ESTÁ: O impacto é irrelevante.",
            "DISABLE_DESK8": "DESATIVAR DESK 8: Concentrar exclusivamente em BTC e SOL."
        }
    ),
    "dilemma4_global_prioritization": Choice(
        instructions="JEV, qual é o plano de ação global prioritário para restabelecer a operação plena de todos os desks auditados?",
        criteria={
            "CORRECT_ALL_AFFECTED_DESKS_SYSTEMATICALLY": "CORREÇÃO SISTEMÁTICA INTEGRAL: 1) Atualizar Desk 9 (Ouro 15m) e Desk 5 (NatGas 15m) com Descoberta em 3 camadas e blindagem contra floor_strike nulo; 2) Corrigir indentação na Desk 8 (ETH 5m); 3) Ajustar Desk 11 para usar KXINXHUD com filtro min_close_ts. Isso restaura a saúde de 100% da frota algorítmica.",
            "FIX_ONLY_PAPER_DESKS": "CORRIGIR APENAS DESKS EM PAPER: Deixar desks live intactas.",
            "POSTPONE_CHANGES": "ADIAR CORREÇÕES: Aguardar 24 horas de observação."
        }
    )
}

print("=" * 90)
print(" [JEV SYSTEMONE] ENVIANDO AUDITORIA GLOBAL DA FROTA E INICIANDO DEBATE INTELECTUAL...")
print("=" * 90)

t0 = time.time()
resp = client.system_one(state=dossier, questions=questions)
elapsed = time.time() - t0

print(f"\n>>> PARECER QUANTITATIVO DO JEV EMITIDO EM {elapsed:.2f}s <<<\n")

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

output_file = "jev_systematic_fleet_audit_verdict.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2)

print(f"\n[SUCESSO] Parecer do JEV gravado em '{output_file}'.")
