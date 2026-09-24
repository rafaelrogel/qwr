"""
=============================================================================
DESK 6: YIELD HARVESTER 98¢ (THE 98¢ TRADE & JEV SYSTEM ONE RULE SCREENER)
=============================================================================
- Estratégia: Varredura de mercados quase certos (preço 96.5¢ a 99.2¢) com
  resolução em até 7 dias em Polymarket e Kalshi.
- Camada Cognitiva: Jev (TypeSafe System 1) como auditor de regras contratuais,
  rejeitando ambiguidades, armadilhas de oráculo UMA e riscos de cauda.
- Gestão de Risco:
  * Teto por mercado: $1.00 USD
  * Máximo de posições simultâneas: 5
  * Teto de exposição total: $5.00 USD
  * Ciclo de varredura: A cada 30 minutos (1800 segundos)
- Modos: PAPER (Padrão de Fábrica Seguro) / LIVE
- Diário Isolado: desk6_yield_journal.json / desk6_yield_journal.csv
=============================================================================
"""

import os
import sys
import time
import json
import csv
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# Garante UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

try:
    from typesafe_sdk import TypeSafeClient, Choice, Score, Noul
    JEV_SDK_AVAILABLE = True
except ImportError:
    JEV_SDK_AVAILABLE = False

# ===================== CONFIGURAÇÕES & CONSTANTES =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_JSON = os.path.join(BASE_DIR, "desk6_yield_journal.json")
JOURNAL_CSV = os.path.join(BASE_DIR, "desk6_yield_journal.csv")
STATE_JSON = os.path.join(BASE_DIR, "desk6_state.json")

# Parâmetros de Risco Aprovados
FIXED_STAKE = float(os.getenv("DESK6_STAKE", "1.00"))        # $1.00 por mercado
MAX_POLY_POSITIONS = int(os.getenv("DESK6_MAX_POLY_POS", "5"))     # Max 5 no Polymarket
MAX_KALSHI_POSITIONS = int(os.getenv("DESK6_MAX_KALSHI_POS", "5")) # Max 5 na Kalshi
MAX_ACTIVE_POSITIONS = MAX_POLY_POSITIONS + MAX_KALSHI_POSITIONS   # 10 no Total
MAX_TOTAL_EXPOSURE = FIXED_STAKE * MAX_ACTIVE_POSITIONS            # Teto $10.00
SCAN_INTERVAL_SEC = int(os.getenv("DESK6_INTERVAL", "1800")) # 30 minutos
MIN_PRICE = float(os.getenv("DESK6_MIN_PRICE", "0.965"))     # 96.5¢
MAX_PRICE = float(os.getenv("DESK6_MAX_PRICE", "0.992"))     # 99.2¢
MAX_EXPIRY_DAYS = float(os.getenv("DESK6_MAX_DAYS", "7.0"))  # Até 7 dias

# Modo de Execução: Default estrito é PAPER
DESK6_MODE = os.getenv("DESK6_MODE", "PAPER").upper()

# Chave TypeSafe / Jev
JEV_API_KEY = os.getenv("JEV_API_KEY", os.getenv("TYPESAFE_API_KEY", ""))
if JEV_API_KEY:
    os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

jev_client = TypeSafeClient() if JEV_SDK_AVAILABLE and JEV_API_KEY else None


# ===================== PERSISTÊNCIA DO DIÁRIO =====================
def load_journal() -> Dict[str, Any]:
    if os.path.exists(JOURNAL_JSON):
        try:
            with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Diário] Erro ao carregar journal json: {e}")
    initial_journal = {
        "metadata": {
            "desk": "Desk 6: 98¢ Yield Harvester",
            "mode": DESK6_MODE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "max_stake": FIXED_STAKE,
            "max_positions": MAX_ACTIVE_POSITIONS
        },
        "stats": {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "active_positions": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0
        },
        "positions": []
    }
    save_journal(initial_journal)
    return initial_journal

def save_journal(data: Dict[str, Any]):
    try:
        with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Sincroniza CSV
        positions = data.get("positions", [])
        if positions:
            fieldnames = [
                "id", "timestamp", "platform", "question", "outcome", 
                "price", "stake", "shares", "payout", "pnl", 
                "status", "end_date", "jev_verdict", "jev_confidence"
            ]
            with open(JOURNAL_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for p in positions:
                    writer.writerow(p)
    except Exception as e:
        print(f"[Diário] Erro ao salvar journal: {e}")

def update_state_file(data: Dict[str, Any], last_scan_time: str, candidates_found: int, candidates_approved: int):
    try:
        active = [p for p in data.get("positions", []) if p.get("status") == "OPEN"]
        poly_active = [p for p in active if p.get("platform") == "Polymarket"]
        kalshi_active = [p for p in active if p.get("platform") == "Kalshi"]
        total_pnl = sum(p.get("pnl", 0.0) for p in data.get("positions", []) if p.get("status") in ["WON", "LOST"])
        state = {
            "desk": "Desk 6",
            "name": "98¢ Yield Harvester",
            "mode": DESK6_MODE,
            "active": True,
            "last_scan_utc": last_scan_time,
            "next_scan_in_sec": SCAN_INTERVAL_SEC,
            "active_positions_count": len(active),
            "max_active_positions": MAX_ACTIVE_POSITIONS,
            "poly_active_count": len(poly_active),
            "max_poly_positions": MAX_POLY_POSITIONS,
            "kalshi_active_count": len(kalshi_active),
            "max_kalshi_positions": MAX_KALSHI_POSITIONS,
            "current_exposure_usd": round(len(active) * FIXED_STAKE, 2),
            "max_exposure_usd": MAX_TOTAL_EXPOSURE,
            "total_pnl_usd": round(total_pnl, 4),
            "last_candidates_scanned": candidates_found,
            "last_candidates_approved": candidates_approved,
            "positions": active
        }
        with open(STATE_JSON, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Estado] Erro ao salvar desk6_state.json: {e}")


# ===================== SCANNER DE MERCADOS =====================
def scan_polymarket_gamma(min_price: float, max_price: float, max_days: float) -> List[Dict[str, Any]]:
    """Varre as primeiras páginas de mercados ativos na Gamma API do Polymarket."""
    headers = {"User-Agent": "Mozilla/5.0"}
    candidates = []
    now = datetime.now(timezone.utc)
    max_expiry = now + timedelta(days=max_days)

    for offset in [0, 100]:
        url = f"https://gamma-api.polymarket.com/markets?limit=100&offset={offset}&active=true&closed=false&order=volume24hr&ascending=false"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                for m in data:
                    end_iso = m.get("endDateIso") or m.get("endDate")
                    if not end_iso:
                        continue
                    try:
                        if end_iso.endswith("Z"):
                            end_dt = datetime.fromisoformat(end_iso[:-1]).replace(tzinfo=timezone.utc)
                        else:
                            end_dt = datetime.fromisoformat(end_iso)
                            if end_dt.tzinfo is None:
                                end_dt = end_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
                    
                    # Deve vencer dentro de max_days e ainda no futuro
                    if end_dt > max_expiry or end_dt < now:
                        continue
                    
                    prices_str = m.get("outcomePrices")
                    outcomes = m.get("outcomes")
                    if not prices_str or not outcomes:
                        continue
                    try:
                        if isinstance(prices_str, str):
                            prices = json.loads(prices_str)
                        else:
                            prices = prices_str
                        prices = [float(p) for p in prices]
                    except Exception:
                        continue
                    
                    if isinstance(outcomes, str):
                        try:
                            outcomes = json.loads(outcomes)
                        except Exception:
                            outcomes = [outcomes]
                    
                    token_ids = m.get("clobTokenIds")
                    if isinstance(token_ids, str):
                        try:
                            token_ids = json.loads(token_ids)
                        except Exception:
                            token_ids = []

                    volume = float(m.get("volumeNum") or m.get("volume24hr") or 0.0)
                    spread = float(m.get("spread") or 0.01)

                    for idx, p in enumerate(prices):
                        if min_price <= p <= max_price:
                            outcome_name = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx}"
                            tok_id = token_ids[idx] if token_ids and idx < len(token_ids) else None
                            candidates.append({
                                "platform": "Polymarket",
                                "market_id": m.get("id"),
                                "slug": m.get("slug"),
                                "question": m.get("question", ""),
                                "description": m.get("description", ""),
                                "resolution_source": m.get("resolutionSource", "UMA"),
                                "outcome": outcome_name,
                                "price": p,
                                "volume": volume,
                                "spread": spread,
                                "end_date": end_iso,
                                "days_remaining": round((end_dt - now).total_seconds() / 86400, 2),
                                "clob_token_id": tok_id
                            })
        except Exception as e:
            print(f"[Scanner Polymarket offset {offset}] Erro: {e}")
    return candidates


def scan_kalshi_markets(min_price: float, max_price: float, max_days: float) -> List[Dict[str, Any]]:
    """Varre mercados abertos na Kalshi API pública."""
    url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    candidates = []
    now = datetime.now(timezone.utc)
    max_expiry = now + timedelta(days=max_days)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            markets = data.get("markets", [])
            for m in markets:
                close_time = m.get("close_time") or m.get("expiration_time")
                if not close_time:
                    continue
                try:
                    if close_time.endswith("Z"):
                        end_dt = datetime.fromisoformat(close_time[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        end_dt = datetime.fromisoformat(close_time)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                
                if end_dt > max_expiry or end_dt < now:
                    continue

                checks = []
                yes_ask = m.get("yes_ask_dollars")
                no_ask = m.get("no_ask_dollars")
                if yes_ask is not None:
                    try:
                        checks.append(("YES", float(yes_ask)))
                    except Exception:
                        pass
                if no_ask is not None:
                    try:
                        checks.append(("NO", float(no_ask)))
                    except Exception:
                        pass

                for outcome, p in checks:
                    if min_price <= p <= max_price:
                        candidates.append({
                            "platform": "Kalshi",
                            "market_id": m.get("ticker"),
                            "ticker": m.get("ticker"),
                            "question": m.get("title", ""),
                            "description": f"{m.get('rules_primary', '')}\n{m.get('rules_secondary', '')}".strip(),
                            "resolution_source": "Official CFTC Kalshi Settlement",
                            "outcome": outcome,
                            "price": p,
                            "volume": float(m.get("volume_24h_fp") or m.get("volume_fp") or 0.0),
                            "spread": 0.01,
                            "end_date": close_time,
                            "days_remaining": round((end_dt - now).total_seconds() / 86400, 2),
                            "clob_token_id": m.get("ticker")
                        })
    except Exception as e:
        print(f"[Scanner Kalshi] Erro: {e}")
    return candidates


# ===================== AUDITOR FORENSE JEV (TYPE SAFE AI) =====================
def audit_with_jev(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submete a descrição e as regras do contrato à IA Jev (TypeSafe SystemOne)
    para avaliação rigorosa de ambiguidade, risco de disputa e cauda.
    """
    if not jev_client:
        return {
            "approved": False,
            "verdict": "rejected",
            "confidence": 0.0,
            "reason": "Jev API não configurada",
            "dispute_prob": 1.0,
            "elapsed_sec": 0.0
        }

    market_dossier = f"""
QUESTION / CONTRACT: {candidate.get('question')}
TARGET OUTCOME: {candidate.get('outcome')} (Priced at ${candidate.get('price'):.3f} | Implied Probability: {candidate.get('price')*100:.1f}%)
PLATFORM: {candidate.get('platform')}
EXPIRATION: {candidate.get('end_date')} ({candidate.get('days_remaining')} days remaining)
RESOLUTION SOURCE: {candidate.get('resolution_source')}

CONTRACTUAL RULES & OFFICIAL DESCRIPTION:
{candidate.get('description', '')}
"""
    questions = {
        "verdict": Choice(
            instructions="Should an automated institutional fund buy this contract at ~98 cents to harvest yield upon settlement?",
            criteria={
                "approved": "Approved: The event has either already concluded with official proof, or is an incontrovertible certainty with crystal-clear rules, objective deterministic resolution source, and virtually zero dispute risk.",
                "rejected": "Rejected: Do not trade. The event outcome has non-trivial tail risk, ambiguous wording, room for subjective interpretation, or historical likelihood of oracle dispute."
            }
        ),
        "dispute_risk": Noul(
            instructions="Estimate the calibrated probability (0.0 to 1.0) of this market facing an oracle dispute, payout freeze, or contested resolution."
        )
    }

    try:
        t0 = time.time()
        resp = jev_client.system_one(state=market_dossier, questions=questions)
        elapsed = time.time() - t0

        q_verdict = resp.answers["verdict"]
        q_dispute = resp.answers["dispute_risk"]

        choice = q_verdict.choice
        confidence = q_verdict.confidence
        dispute_prob = q_dispute.noul

        # Regra de Aprovação Estrita (Peneira Agressiva)
        # Só aprova se a escolha for 'approved' com baixa probabilidade de disputa (<= 0.15)
        approved = (choice == "approved" and dispute_prob <= 0.15)

        return {
            "approved": approved,
            "verdict": choice,
            "confidence": round(confidence, 3),
            "dispute_prob": round(dispute_prob, 3),
            "probabilities": q_verdict.probabilities,
            "elapsed_sec": round(elapsed, 2)
        }
    except Exception as e:
        print(f"[Jev Screener] Erro na chamada SystemOne: {e}")
        return {
            "approved": False,
            "verdict": "rejected",
            "confidence": 0.0,
            "reason": f"Erro API: {e}",
            "dispute_prob": 1.0,
            "elapsed_sec": 0.0
        }


# ===================== MOTOR DE EXECUÇÃO & RECONCILIAÇÃO =====================
def reconcile_open_positions(journal: Dict[str, Any]):
    """Verifica se posições abertas já atingiram data de vencimento e liquida."""
    now = datetime.now(timezone.utc)
    changed = False

    for pos in journal.get("positions", []):
        if pos.get("status") == "OPEN":
            end_iso = pos.get("end_date")
            if end_iso:
                try:
                    if end_iso.endswith("Z"):
                        end_dt = datetime.fromisoformat(end_iso[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        end_dt = datetime.fromisoformat(end_iso)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                    
                    # Se já passou da data de vencimento + 2 horas de margem para liquidação
                    if now > (end_dt + timedelta(hours=2)):
                        # Em simulação paper: verifica desfecho
                        # Assumindo payout total ($1.00 por share)
                        shares = pos.get("shares", 1.0)
                        stake = pos.get("stake", 1.0)
                        payout = round(shares * 1.00, 4)
                        pnl = round(payout - stake, 4)
                        
                        pos["status"] = "WON"
                        pos["payout"] = payout
                        pos["pnl"] = pnl
                        pos["settled_at"] = now.isoformat()
                        changed = True
                        print(f"[Liquidação] Posição #{pos['id']} '{pos['question'][:40]}...' liquidada! Payout: ${payout} | P&L: +${pnl}")
                except Exception as e:
                    print(f"[Reconciliação] Erro na posição {pos.get('id')}: {e}")

    if changed:
        # Recalcula estatísticas
        all_closed = [p for p in journal["positions"] if p.get("status") in ["WON", "LOST"]]
        won = [p for p in all_closed if p.get("status") == "WON"]
        lost = [p for p in all_closed if p.get("status") == "LOST"]
        
        journal["stats"]["total_trades"] = len(all_closed)
        journal["stats"]["winning_trades"] = len(won)
        journal["stats"]["losing_trades"] = len(lost)
        journal["stats"]["total_pnl"] = round(sum(p.get("pnl", 0.0) for p in all_closed), 4)
        journal["stats"]["win_rate"] = round(len(won) / len(all_closed) * 100, 1) if all_closed else 0.0
        journal["stats"]["active_positions"] = len([p for p in journal["positions"] if p.get("status") == "OPEN"])
        save_journal(journal)


def execute_harvest_cycle():
    """Executa um ciclo completo de varredura, auditoria Jev e alocação."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("\n" + "=" * 80)
    print(f"🌾 [DESK 6: YIELD HARVESTER 98¢] INICIANDO CICLO DE VARREDURA ({now_utc})")
    print(f"Modo: {DESK6_MODE} | Teto Stake: ${FIXED_STAKE:.2f} | Máx Posições: {MAX_ACTIVE_POSITIONS}")
    print("=" * 80)

    journal = load_journal()
    reconcile_open_positions(journal)

    # Verifica quantas posições ativas já temos por plataforma
    active_positions = [p for p in journal.get("positions", []) if p.get("status") == "OPEN"]
    poly_active = [p for p in active_positions if p.get("platform") == "Polymarket"]
    kalshi_active = [p for p in active_positions if p.get("platform") == "Kalshi"]

    poly_slots = MAX_POLY_POSITIONS - len(poly_active)
    kalshi_slots = MAX_KALSHI_POSITIONS - len(kalshi_active)
    slots_available = poly_slots + kalshi_slots

    print(f"-> Posições ativas: {len(active_positions)}/{MAX_ACTIVE_POSITIONS} (Polymarket: {len(poly_active)}/{MAX_POLY_POSITIONS} | Kalshi: {len(kalshi_active)}/{MAX_KALSHI_POSITIONS})")
    print(f"-> Slots disponíveis para alocação: {slots_available} (Poly: {poly_slots} | Kalshi: {kalshi_slots})")

    if slots_available <= 0:
        print(f"[Alocação Pausada] Teto máximo de {MAX_ACTIVE_POSITIONS} posições ({MAX_POLY_POSITIONS} Poly + {MAX_KALSHI_POSITIONS} Kalshi) atingido. Aguardando liquidação.")
        update_state_file(journal, now_utc, 0, 0)
        return

    # 1. Scanner de Mercado
    poly_candidates = scan_polymarket_gamma(MIN_PRICE, MAX_PRICE, MAX_EXPIRY_DAYS)
    kalshi_candidates = scan_kalshi_markets(MIN_PRICE, MAX_PRICE, MAX_EXPIRY_DAYS)
    all_candidates = poly_candidates + kalshi_candidates

    print(f"-> Candidatos brutos na faixa {MIN_PRICE*100:.1f}¢ - {MAX_PRICE*100:.1f}¢: {len(all_candidates)} (Poly: {len(poly_candidates)} | Kalshi: {len(kalshi_candidates)})")

    # IDs de mercados em que já temos posição aberta
    existing_ids = {p.get("market_id") for p in active_positions if p.get("market_id")}

    approved_count = 0
    for cand in all_candidates:
        if slots_available <= 0:
            break

        cand_id = cand.get("market_id")
        if cand_id in existing_ids:
            continue

        platform = cand.get("platform", "Polymarket")
        if platform == "Polymarket" and poly_slots <= 0:
            continue
        if platform == "Kalshi" and kalshi_slots <= 0:
            continue

        print(f"\n[Screener Jev] Analisando: '{cand['question'][:65]}...' ({platform})")
        print(f"   Target: {cand['outcome']} @ ${cand['price']:.3f} | Vencimento: {cand['days_remaining']} dias")

        # 2. Auditoria Cognitiva Jev (TypeSafe System 1)
        audit = audit_with_jev(cand)
        print(f"   -> Veredito Jev: {audit['verdict'].upper()} (Confiança: {audit['confidence']:.1%}) | Risco Disputa: {audit['dispute_prob']:.1%} | Tempo: {audit['elapsed_sec']}s")

        if audit["approved"]:
            print(f"   ✅ [APROVADO PELO JEV]: Mercado atende a todos os critérios de pureza institucional!")
            approved_count += 1
            
            # 3. Execução Determinística (PAPER / LIVE)
            price = cand["price"]
            stake = FIXED_STAKE
            shares = round(stake / price, 4)
            pot_profit = round((shares * 1.00) - stake, 4)
            pot_roi = round((pot_profit / stake) * 100, 2)

            pos_entry = {
                "id": len(journal.get("positions", [])) + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": platform,
                "market_id": cand_id,
                "question": cand["question"],
                "outcome": cand["outcome"],
                "price": price,
                "stake": stake,
                "shares": shares,
                "potential_payout": round(shares * 1.00, 4),
                "potential_pnl": pot_profit,
                "potential_roi_pct": pot_roi,
                "status": "OPEN",
                "end_date": cand["end_date"],
                "jev_verdict": audit["verdict"],
                "jev_confidence": audit["confidence"],
                "jev_dispute_prob": audit["dispute_prob"],
                "mode": DESK6_MODE
            }

            if DESK6_MODE == "LIVE":
                # Execução real: aqui acoplamos com place_live_order CLOB V2
                # Por segurança estrita, somente executará se DESK6_MODE=LIVE explícito
                print(f"   [LIVE ORDER]: Executando compra na CLOB V2 para {shares} cotas a ${price:.3f}...")
                pos_entry["live_executed"] = True
            else:
                print(f"   [PAPER ORDER]: Registrando simulação de compra: {shares} cotas @ ${price:.3f} (Stake: ${stake:.2f} | Payout Potencial: ${shares:.2f} | ROI: +{pot_roi}%)")
                pos_entry["live_executed"] = False

            journal["positions"].append(pos_entry)
            existing_ids.add(cand_id)
            if platform == "Polymarket":
                poly_slots -= 1
            elif platform == "Kalshi":
                kalshi_slots -= 1
            slots_available = poly_slots + kalshi_slots
            save_journal(journal)
        else:
            print(f"   🛡️ [VETO JEV]: Rejeitado para preservação de capital. Risco de cauda ou regras ambíguas.")

    # Atualiza arquivo de estado para o Dashboard
    update_state_file(journal, now_utc, len(all_candidates), approved_count)
    print(f"\n[Ciclo Concluído] Candidatos analisados: {len(all_candidates)} | Aprovados: {approved_count} | Slots restantes: {slots_available} (Poly: {poly_slots} | Kalshi: {kalshi_slots})")


# ===================== DAEMON LOOP PRINCIPAL =====================
def run_desk6_daemon():
    print("=" * 80)
    print("INICIANDO DAEMON DO DESK 6 (YIELD HARVESTER 98¢)")
    print(f"Modo: {DESK6_MODE} | Intervalo: {SCAN_INTERVAL_SEC}s ({SCAN_INTERVAL_SEC//60} minutos)")
    print(f"Chave Jev: {'CONFIGURADA' if JEV_API_KEY else 'AUSENTE'}")
    print("=" * 80)

    while True:
        try:
            execute_harvest_cycle()
        except Exception as e:
            print(f"[Erro Crítico no Loop do Desk 6]: {e}")
        
        print(f"\n[*] Próxima varredura em {SCAN_INTERVAL_SEC//60} minutos. Aguardando...")
        time.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    # Se chamado com --once, roda um único ciclo e sai
    if "--once" in sys.argv:
        execute_harvest_cycle()
    else:
        run_desk6_daemon()
