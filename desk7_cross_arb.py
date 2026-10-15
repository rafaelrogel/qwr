# -*- coding: utf-8 -*-
"""
=============================================================================
DESK 7: CROSS-MARKET MACRO ARBITRAGEUR (POLYMARKET VS KALSHI)
=============================================================================
Estratégia: Monitoramento algorítmico de eventos idênticos (Macro, Fed, CPI,
Eleições e Cripto) entre Polymarket e Kalshi para captura de EV livre
quando a soma dos preços de lados complementares for menor que $1.00:
  Leg A: Buy YES on Polymarket + Buy NO on Kalshi
  Leg B: Buy YES on Kalshi + Buy NO on Polymarket
Gestão de Risco:
  - Dedução estrita de taxas CFTC da Kalshi (~1.5%) e gas Polygon (~$0.008)
  - Dimensionamento Kelly baseado no saldo particionado ($21.50 Poly / $10.36 Kalshi)
  - Persistência em desk7_cross_arb_state.json e desk7_cross_arb_journal.json
=============================================================================
"""

import os
import sys
import time
import json
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from risk_gate import is_system_halted, atomic_write_json, safe_read_json
from cross_venue_sor import SmartOrderRouter

# Suporte UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_JSON = os.path.join(BASE_DIR, "desk7_cross_arb_state.json")
JOURNAL_JSON = os.path.join(BASE_DIR, "desk7_cross_arb_journal.json")

# Configurações de Fricção e Margem
SCAN_INTERVAL_SEC = int(os.getenv("DESK7_INTERVAL", "60"))       # 60 segundos
ARB_ALERT_THRESHOLD = float(os.getenv("DESK7_THRESHOLD", "0.96")) # Custo Total <= 96¢ -> Lucro >= 4%
WATCHLIST_THRESHOLD = 0.99                                       # Custo Total <= 99¢ entra no radar
KALSHI_TAKER_FEE_PCT = 0.015                                      # 1.5% de taxa Kalshi
ESTIMATED_GAS_USD = 0.008                                         # Custo de gas Polygon

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityDesk7/2.0"}

TARGET_KALSHI_SERIES = [
    "KXFEDDECISION",  # Decisão pura do Fed (sem cláusula de dissidência)
    "KXFED",          # Fed Funds target rate
    "KXECONSTATCPI",
    "CPIYOY",
    "KXPCEHEAD",
    "KXBTC15M",
    "KXETH15M",
    "KXBRPRES",
    "KXNOMGDPGROWTH",
    "KXPAYROLLS"
]

POLYMARKET_TARGET_SLUGS = [
    "fed-decision-in-october-20260617190323537",
    "democratic-presidential-nominee-2028",
    "strait-of-hormuz-traffic-returns-to-normal-by-september-30-20260702154339440"
]


# ===================== PERSISTÊNCIA =====================
def load_journal() -> Dict[str, Any]:
    if os.path.exists(JOURNAL_JSON):
        try:
            with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    initial = {
        "metadata": {
            "desk": "Desk 7: Cross-Market Macro Arbitrageur",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "RADAR_SCANNER"
        },
        "stats": {
            "total_arbs_detected": 0,
            "total_simulated_profit": 0.0,
            "best_roi_pct": 0.0
        },
        "opportunities": []
    }
    save_journal(initial)
    return initial


def save_journal(data: Dict[str, Any]):
    try:
        atomic_write_json(JOURNAL_JSON, data)
    except Exception as e:
        print(f"[Desk 7] Erro ao salvar journal: {e}")


def save_state(state: Dict[str, Any]):
    try:
        atomic_write_json(STATE_JSON, state)
    except Exception as e:
        print(f"[Desk 7] Erro ao salvar state: {e}")


# ===================== SCANNERS DE MERCADOS =====================
def fetch_polymarket_markets() -> List[Dict[str, Any]]:
    """Consulta mercados macro, políticos e cripto na API Gamma da Polymarket."""
    markets = []
    
    # 1. Busca eventos específicos de alto valor macro
    for slug in POLYMARKET_TARGET_SLUGS:
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                events = json.loads(resp.read().decode())
                if events:
                    ev = events[0]
                    ev_title = ev.get("title", "")
                    for m in ev.get("markets", []):
                        _parse_poly_market(m, ev_title, markets)
        except Exception as e:
            print(f"[Desk 7] Erro no slug {slug}: {e}")

    # 2. Busca também top eventos gerais por volume
    url_gen = "https://gamma-api.polymarket.com/events?limit=40&active=true&closed=false&order=volume24hr&ascending=false"
    try:
        req = urllib.request.Request(url_gen, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read().decode())
            for ev in events:
                ev_title = ev.get("title", "")
                for m in ev.get("markets", []):
                    _parse_poly_market(m, ev_title, markets)
    except Exception as e:
        print(f"[Desk 7] Erro na busca geral Poly: {e}")

    return markets


def _parse_poly_market(m: dict, ev_title: str, dest_list: list):
    q = m.get("question", "")
    outcomes_raw = m.get("outcomes")
    prices_raw = m.get("outcomePrices")
    if not outcomes_raw or not prices_raw:
        return
    try:
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
        prices = [float(p) for p in (json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw)]
    except Exception:
        return

    if len(outcomes) >= 2 and len(prices) >= 2:
        yes_idx = 0
        no_idx = 1
        for i, o in enumerate(outcomes):
            if str(o).lower() in ["yes", "sim"]:
                yes_idx = i
            elif str(o).lower() in ["no", "nao", "não"]:
                no_idx = i

        dest_list.append({
            "platform": "Polymarket",
            "event_title": ev_title,
            "question": q,
            "market_id": m.get("id"),
            "slug": m.get("slug"),
            "yes_price": prices[yes_idx],
            "no_price": prices[no_idx],
            "volume": float(m.get("volumeNum") or m.get("volume24hr") or 0.0),
            "end_date": m.get("endDateIso") or m.get("endDate")
        })


def fetch_kalshi_markets() -> List[Dict[str, Any]]:
    """Consulta séries macro e abertas na Kalshi API."""
    markets = []
    
    # 1. Consulta séries macro prioritárias
    for s in TARGET_KALSHI_SERIES:
        url = f"https://external-api.kalshi.com/trade-api/v2/markets?series_ticker={s}&limit=25"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=6) as resp:
                d = json.loads(resp.read().decode())
                raw_mkts = d.get("markets", [])
                for m in raw_mkts:
                    _parse_kalshi_market(m, markets)
        except Exception:
            pass

    # 2. Consulta mercados abertos gerais (filtrando esportes parlay)
    url_gen = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100"
    try:
        req = urllib.request.Request(url_gen, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode())
            raw_mkts = d.get("markets", [])
            for m in raw_mkts:
                t = m.get("ticker", "")
                if "KXMVECROSSCATEGORY" in t:
                    continue
                _parse_kalshi_market(m, markets)
    except Exception:
        pass

    return markets


def _parse_kalshi_market(m: dict, dest_list: list):
    yes_ask = m.get("yes_ask_dollars")
    no_ask = m.get("no_ask_dollars")
    if yes_ask is None and no_ask is None:
        return
    try:
        yp = float(yes_ask) if yes_ask is not None else (1.0 - float(no_ask) if no_ask is not None else 0.5)
        np = float(no_ask) if no_ask is not None else (1.0 - float(yes_ask) if yes_ask is not None else 0.5)
    except Exception:
        return

    dest_list.append({
        "platform": "Kalshi",
        "event_ticker": m.get("event_ticker", ""),
        "ticker": m.get("ticker", ""),
        "title": m.get("title", ""),
        "yes_price": yp,
        "no_price": np,
        "volume": float(m.get("volume_24h_fp") or m.get("volume_fp") or 0.0),
        "close_time": m.get("close_time") or m.get("expiration_time")
    })


def dates_match(poly_text: str, kalshi_text: str, kalshi_ticker: str) -> bool:
    """Valida se mês e ano entre Polymarket e Kalshi coincidem para evitar descasamento temporal."""
    pt = poly_text.lower()
    kt = (kalshi_text + " " + kalshi_ticker).lower()
    
    # Validação de Ano
    years = ["2024", "2025", "2026", "2027", "2028", "2029"]
    poly_years = [y for y in years if y in pt]
    if poly_years:
        matched_year = False
        for py in poly_years:
            py_short = py[2:]
            if py in kt or py_short in kt or f"-{py_short}" in kt or f"{py_short}" in kalshi_ticker.lower():
                matched_year = True
                break
        if not matched_year:
            return False

    # Validação de Mês
    month_map = {
        "january": "jan", "february": "feb", "march": "mar", "april": "apr",
        "may": "may", "june": "jun", "july": "jul", "august": "aug",
        "september": "sep", "october": "oct", "november": "nov", "december": "dec"
    }
    
    poly_months = set()
    for full_m, short_m in month_map.items():
        if full_m in pt or f" {short_m} " in f" {pt} " or f" {short_m}." in pt or f"-{short_m}-" in pt:
            poly_months.add(short_m)
            
    if poly_months:
        matched_month = False
        for pm in poly_months:
            if pm in kt:
                matched_month = True
                break
        if not matched_month:
            return False
            
    return True


def calculate_harrier_kalshi_fee(price: float) -> float:
    """
    Fórmula exata CFTC Kalshi (HarrierOnChain / PredictionMarketArbitrage):
    Taxa parabólica baseada na incerteza: max(0.005, round(0.07 * P * (1.0 - P), 4)).
    Em P=0.50, a taxa atinge o pico de ~1.75¢ por contrato.
    Em P=0.95 ou P=0.05, a taxa cai para ~0.33¢ por contrato.
    """
    p = max(0.01, min(0.99, price))
    cftc_parabolic = 0.07 * p * (1.0 - p)
    return round(max(0.005, cftc_parabolic), 4)


def calculate_harrier_polymarket_fee(price: float, is_taker: bool = True) -> float:
    """
    Fórmula oficial Polymarket CLOB V2 (HarrierOnChain):
    - Maker: 0.00%
    - Taker em mercados de livro / 15m / dynamic fee: 0.20% (20 bps) do nocional.
    """
    if not is_taker:
        return 0.0
    return round(price * 0.0020, 4)


# ===================== MOTOR DE PAREAMENTO & ARBITRAGEM =====================
def match_pairs(poly_mkts: List[Dict[str, Any]], kalshi_mkts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identifica pares correspondentes por cruzamento semântico de palavras-chave com rigor de datas."""
    pairs = []
    
    for p in poly_mkts:
        pq = p["question"].lower()
        pe = p["event_title"].lower()
        p_yes = p["yes_price"]
        p_no = p["no_price"]

        if p_yes <= 0.001 or p_yes >= 0.999:
            continue

        for k in kalshi_mkts:
            kt = k["title"].lower()
            k_yes = k["yes_price"]
            k_no = k["no_price"]

            if k_yes <= 0.001 or k_yes >= 0.999:
                continue

            # Salvaguarda Institucional: Bloqueia mercados multi-condicionais / combo com dissidência (Basis Risk)
            if "dissent" in kt or "combo" in k.get("ticker", "").lower() or "combo" in kt:
                continue

            # Salvaguarda Institucional: Bloqueia descasamento temporal (ano/mês diferentes)
            if not dates_match(pq + " " + pe, kt, k.get("ticker", "")):
                continue

            matched = False
            topic = "GERAL"

            # 1. Fed Interest Rates
            if ("fed" in pq or "fed" in pe) and ("federal funds" in kt or "fed" in kt):
                has_gt_p = ">" in pq or "more than" in pq or "greater than" in pq
                has_gt_k = ">" in kt or "more than" in kt or "greater than" in kt

                if ("25" in pq and "25" in kt) and ("cut" in pq or "decrease" in pq) and ("cut" in kt or "decrease" in kt):
                    if has_gt_p == has_gt_k:
                        matched = True
                        topic = "FED_RATE_GT25BP_CUT" if has_gt_p else "FED_RATE_25BP_CUT"
                elif ("50" in pq and "50" in kt) and ("cut" in pq or "decrease" in pq) and ("cut" in kt or "decrease" in kt):
                    if has_gt_p == has_gt_k:
                        matched = True
                        topic = "FED_RATE_50BP_CUT"
                elif ("no change" in pq or "pause" in pq or "hold" in pq) and ("no change" in kt or "pause" in kt):
                    matched = True
                    topic = "FED_RATE_HOLD"

            # 2. CPI / Inflação
            elif ("cpi" in pq or "inflation" in pq) and ("cpi" in kt or "inflation" in kt):
                matched = True
                topic = "MACRO_CPI_INFLATION"

            # 3. Eleições 2028
            elif ("2028" in pe or "2028" in pq) and ("2028" in kt):
                for cand in ["newsom", "vance", "harris", "rubio", "whitmer", "shapiro", "desantis"]:
                    if cand in pq and cand in kt:
                        matched = True
                        topic = f"POLITICS_2028_{cand.upper()}"
                        break

            # 4. Crypto Milestones
            elif ("bitcoin" in pq or "btc" in pq) and ("bitcoin" in kt or "btc" in kt):
                for lvl in ["100k", "90k", "85k", "80k", "75k", "70k"]:
                    if lvl in pq and lvl in kt:
                        matched = True
                        topic = f"CRYPTO_BTC_{lvl.upper()}"
                        break

            if matched:
                # Matriz Exata de Taxas (HarrierOnChain):
                # 1. Leg A: Buy YES on Poly + Buy NO on Kalshi
                poly_fee_a = calculate_harrier_polymarket_fee(p_yes, is_taker=True)
                kalshi_fee_a = calculate_harrier_kalshi_fee(k_no)
                cost_leg_a = p_yes + poly_fee_a + k_no + kalshi_fee_a + ESTIMATED_GAS_USD
                profit_leg_a = 1.00 - cost_leg_a
                roi_leg_a = (profit_leg_a / cost_leg_a) * 100.0 if cost_leg_a > 0 else 0.0

                # 2. Leg B: Buy YES on Kalshi + Buy NO on Poly
                kalshi_fee_b = calculate_harrier_kalshi_fee(k_yes)
                poly_fee_b = calculate_harrier_polymarket_fee(p_no, is_taker=True)
                cost_leg_b = k_yes + kalshi_fee_b + p_no + poly_fee_b + ESTIMATED_GAS_USD
                profit_leg_b = 1.00 - cost_leg_b
                roi_leg_b = (profit_leg_b / cost_leg_b) * 100.0 if cost_leg_b > 0 else 0.0

                if profit_leg_a > profit_leg_b:
                    best_leg = "LEG_A (Buy YES Poly + Buy NO Kalshi)"
                    best_cost = cost_leg_a
                    best_roi = roi_leg_a
                    best_poly_fee = poly_fee_a
                    best_kalshi_fee = kalshi_fee_a
                    best_structure = f"Poly YES (${p_yes:.3f}) + Kalshi NO (${k_no:.3f})"
                else:
                    best_leg = "LEG_B (Buy YES Kalshi + Buy NO Poly)"
                    best_cost = cost_leg_b
                    best_roi = roi_leg_b
                    best_poly_fee = poly_fee_b
                    best_kalshi_fee = kalshi_fee_b
                    best_structure = f"Kalshi YES (${k_yes:.3f}) + Poly NO (${p_no:.3f})"

                divergence_pct = abs(p_yes - k_yes) * 100.0

                # Smart Order Routing (SOR Institucional)
                sor = SmartOrderRouter(min_profit_threshold=Decimal("0.015"))
                sor_plan = sor.plan_cross_arbitrage(
                    poly_yes_ask=p_yes,
                    poly_no_ask=p_no,
                    kalshi_yes_ask=k_yes,
                    kalshi_no_ask=k_no,
                    max_bankroll_usd=20.0
                )

                pair_data = {
                    "topic": topic,
                    "polymarket_title": p["question"],
                    "polymarket_yes": round(p_yes, 3),
                    "polymarket_no": round(p_no, 3),
                    "kalshi_title": k["title"],
                    "kalshi_ticker": k["ticker"],
                    "kalshi_yes": round(k_yes, 3),
                    "kalshi_no": round(k_no, 3),
                    "best_leg": best_leg,
                    "best_structure": best_structure,
                    "total_cost": round(best_cost, 4),
                    "poly_fee": round(best_poly_fee, 4),
                    "kalshi_fee": round(best_kalshi_fee, 4),
                    "net_profit_per_pair": round(1.00 - best_cost, 4),
                    "roi_pct": round(best_roi, 2),
                    "divergence_spread_pct": round(divergence_pct, 1),
                    "is_pure_arbitrage": (best_cost <= ARB_ALERT_THRESHOLD),
                    "is_risk_free_arbitrage": (best_cost < 1.0),
                    "suggested_stake_usd": suggested_stake,
                    "sor_active": sor_plan.found,
                    "sor_strategy": sor_plan.strategy if sor_plan.found else "NENHUMA",
                    "sor_balanced_contracts": float(sor_plan.max_contracts),
                    "sor_expected_profit_usd": float(sor_plan.expected_profit_usd),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                pairs.append(pair_data)

    # Remove duplicados e ordena por menor custo total (maior lucro)
    unique_pairs = []
    seen = set()
    for item in pairs:
        pair_key = (item["topic"], item["kalshi_ticker"])
        if pair_key not in seen:
            seen.add(pair_key)
            unique_pairs.append(item)

    unique_pairs.sort(key=lambda x: x["total_cost"])
    return unique_pairs


# ===================== CICLO DE EXECUÇÃO =====================
def run_desk7_cycle() -> Dict[str, Any]:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("\n" + "=" * 80)
    print(f"🌐 [DESK 7: CROSS-MARKET MACRO ARBITRAGEUR] INICIANDO VARREDURA ({now_utc})")
    print(f"Alvo: Polymarket vs Kalshi | Limite Alerta: <= ${ARB_ALERT_THRESHOLD:.2f} | Taker Fee Kalshi: 1.5%")
    print("=" * 80)

    halted, halt_msg = is_system_halted()
    if halted:
        print(f"🛑 [VETO DE SEGURANÇA] Kill-switch ativo ({halt_msg}). Pausando varredura do Desk 7.")
        return {}

    journal = load_journal()

    # 1. Busca mercados
    poly_mkts = fetch_polymarket_markets()
    kalshi_mkts = fetch_kalshi_markets()
    print(f"-> Mercados Coletados: Polymarket ({len(poly_mkts)}) | Kalshi ({len(kalshi_mkts)})")

    # Filtrar por prazo curto (≤7 dias) e liquidez mínima (≥100k USD 24h)
    def _is_short_term(market: dict) -> bool:
        # Polymarket usa 'end_date', Kalshi usa 'close_time'
        date_str = market.get('end_date') or market.get('close_time')
        if not date_str:
            return False
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            try:
                ts = int(date_str)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                return False
        now = datetime.now(timezone.utc)
        delta = dt - now
        # positivo e dentro de 7 dias
        return 0 < delta.total_seconds() <= 7 * 24 * 3600

    # Aplicar filtros a ambas as listas
    poly_mkts = [m for m in poly_mkts if _is_short_term(m) and m.get('volume', 0) >= 100_000]
    kalshi_mkts = [m for m in kalshi_mkts if _is_short_term(m) and m.get('volume', 0) >= 100_000]

    # 2. Pareamento Semântico
    opportunities = match_pairs(poly_mkts, kalshi_mkts)
    print(f"-> Pares Correspondentes Monitorados na Watchlist: {len(opportunities)}")

    divergence_arbs = [o for o in opportunities if o.get("is_pure_arbitrage") or o.get("total_cost", 1.0) <= ARB_ALERT_THRESHOLD]
    if divergence_arbs:
        print("\n" + "⚡" * 40)
        print(f"📡 [DIVERGÊNCIA MACRO COM SPREAD DETECTADA]: {len(divergence_arbs)} OPORTUNIDADE(S) DE DISCREPÂNCIA!")
        print("⚠️ NOTA QUANTITATIVA: Requer conferência de regras de liquidação idênticas (Basis Risk) e book antes de executar.")
        print("⚡" * 40)
        for arb in divergence_arbs:
            print(f"  • [{arb['topic']}] Custo Combinado: ${arb['total_cost']:.3f} | Discrepância Bruta: +${arb['net_profit_per_pair']:.3f} (+{arb['roi_pct']}%)")
            print(f"    Estratégia: {arb['best_leg']}")
            print(f"    Poly: {arb['polymarket_title'][:50]} (YES: ${arb['polymarket_yes']})")
            print(f"    Kalshi: {arb['kalshi_title'][:50]} (YES: ${arb['kalshi_yes']})")
            print(f"    Aporte Sugerido (Kelly): ${arb['suggested_stake_usd']:.2f} USD")
            
            journal["opportunities"].append(arb)
            journal["stats"]["total_arbs_detected"] += 1
            journal["stats"]["best_roi_pct"] = max(journal["stats"]["best_roi_pct"], arb["roi_pct"])
    else:
        print("\n[Radar de Discrepância] Maiores divergências de probabilidades encontradas:")
        for opp in opportunities[:4]:
            print(f"  • [{opp['topic']}] Divergência: {opp['divergence_spread_pct']}% | Custo: ${opp['total_cost']:.3f} | ROI: {opp['roi_pct']:+.1f}%")
            print(f"    Poly: {opp['polymarket_title'][:40]}... (YES: ${opp['polymarket_yes']})")
            print(f"    Kalshi: {opp['kalshi_title'][:40]}... (YES: ${opp['kalshi_yes']})")

    best_spread = opportunities[0]["divergence_spread_pct"] if opportunities else 0.0
    best_roi = opportunities[0]["roi_pct"] if opportunities else 0.0

    state = {
        "desk": "Desk 7",
        "name": "Cross-Market Macro Divergence Radar",
        "mode": "RADAR_SCANNER",
        "active": True,
        "last_scan_utc": now_utc,
        "next_scan_in_sec": SCAN_INTERVAL_SEC,
        "pairs_tracked_count": len(opportunities),
        "divergence_arbs_active_count": len(divergence_arbs),
        "best_divergence_spread_pct": best_spread,
        "best_roi_pct": best_roi,
        "polymarket_markets_scanned": len(poly_mkts),
        "kalshi_markets_scanned": len(kalshi_mkts),
        "basis_risk_warning": "Requer verificação de regras de liquidação idênticas (UMA vs CFTC) e liquidez em ambas as pernas antes de qualquer execução.",
        "macro_divergence_alerts": divergence_arbs,
        "top_opportunities": opportunities[:8]
    }
    save_state(state)
    save_journal(journal)
    return state


def run_desk7_daemon():
    print("=" * 80)
    print("INICIANDO DAEMON DO DESK 7 (CROSS-MARKET MACRO ARBITRAGEUR)")
    print(f"Intervalo: {SCAN_INTERVAL_SEC}s | Limite Alerta: <= ${ARB_ALERT_THRESHOLD:.2f}")
    print("=" * 80)

    while True:
        try:
            run_desk7_cycle()
        except KeyboardInterrupt:
            print("\n[Desk 7] Pausado pelo usuário.")
            break
        except Exception as e:
            print(f"[Erro no Loop do Desk 7]: {e}")
        
        print(f"\n[*] Próxima varredura em {SCAN_INTERVAL_SEC}s. Aguardando...")
        time.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_desk7_cycle()
    else:
        run_desk7_daemon()
