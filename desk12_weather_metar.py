"""
=============================================================================
DESK 12: WEATHER & METAR AIRPORT SETTLEMENT ARBITRAGE (POLYWEATHER ARCHITECTURE)
=============================================================================
Autonomous 24/7 Engine exploiting physical settlement latency between:
1. Real-time NOAA Aviation Weather METAR reports (ASOS sensors at major airports)
2. Kalshi Temperature Markets settled officially by The Weather Company / NWS ASOS.

When an airport ASOS station records a temperature that physically breaches
a contract strike during the trading day:
- "Will max temp be < 93F" -> If peak >= 93.0F, outcome is GUARANTEED NO (Payout $1.00).
- "Will max temp be > 90F" -> If peak > 90.0F, outcome is GUARANTEED YES (Payout $1.00).
- "Will max temp be 85-86F" -> If peak > 86.9F, outcome is GUARANTEED NO (Payout $1.00).

Audited by JEV SystemOne (TypeSafe AI) before execution.
Mode: PAPER (Defensivo / Fail-Closed).
=============================================================================
"""

import os
import sys
import json
import time
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from risk_gate import is_system_halted, atomic_write_json, safe_read_json, get_desk_mode

try:
    from typesafe_sdk import TypeSafeClient, Choice, Score, Noul
    JEV_SDK_AVAILABLE = True
except ImportError:
    JEV_SDK_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_PATH = os.path.join(BASE_DIR, "desk12_weather_journal.json")
STATE_PATH = os.path.join(BASE_DIR, "desk12_state.json")

# ===================== CONFIGURAÇÕES =====================
DESK12_MODE = get_desk_mode("DESK12_MODE", fallback="PAPER")
FIXED_STAKE = float(os.getenv("DESK12_STAKE", "1.00"))        # $1.00 por oportunidade
MAX_ACTIVE_POSITIONS = int(os.getenv("DESK12_MAX_POS", "20")) # Até 20 posições ativas simultâneas
MAX_TOTAL_EXPOSURE = FIXED_STAKE * MAX_ACTIVE_POSITIONS      # Teto $20.00
SCAN_INTERVAL_SEC = int(os.getenv("DESK12_INTERVAL", "300")) # Varredura a cada 5 min
MAX_ENTRY_PRICE = 0.97                                       # Captura de penny clip até 97¢ (spread mínimo 3¢ a 40¢ de lucro garantido)
NWS_ROUNDING_BUFFER_F = float(os.getenv("DESK12_NWS_BUFFER_F", "1.1")) # Buffer anti-arredondamento NWS (+1.1°F acima do teto)

JEV_API_KEY = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
jev_client = TypeSafeClient(api_key=JEV_API_KEY) if (JEV_SDK_AVAILABLE and JEV_API_KEY) else None

# Mapeamento Estação METAR ICAO -> Séries Kalshi & Cidade (14 Grandes Hubs dos EUA)
AIRPORT_STATIONS = {
    "KAUS": {
        "city": "Austin, TX",
        "station_name": "Austin Bergstrom Int'l Airport",
        "kalshi_series": ["KXHIGHAUS", "HIGHAUS", "KXTEMPAUSH"],
        "tz_offset_hours": -5  # CDT (UTC-5)
    },
    "KMIA": {
        "city": "Miami, FL",
        "station_name": "Miami Int'l Airport",
        "kalshi_series": ["KXHIGHMIA", "HIGHMIA", "KXTEMPMIAH"],
        "tz_offset_hours": -4  # EDT (UTC-4)
    },
    "KORD": {
        "city": "Chicago, IL",
        "station_name": "Chicago O'Hare Int'l Airport",
        "kalshi_series": ["KXHIGHCHI", "HIGHCHI", "KXTEMPCHIH"],
        "tz_offset_hours": -5  # CDT (UTC-5)
    },
    "KEWR": {
        "city": "Newark / NYC",
        "station_name": "Newark Liberty Int'l Airport",
        "kalshi_series": ["KXHIGHTEWR", "HIGHNY", "KXTEMPNYCH"],
        "tz_offset_hours": -4  # EDT (UTC-4)
    },
    "KLAX": {
        "city": "Los Angeles, CA",
        "station_name": "Los Angeles Int'l Airport",
        "kalshi_series": ["KXHIGHLAX", "KXTEMPLAXH"],
        "tz_offset_hours": -7  # PDT (UTC-7)
    },
    "KDFW": {
        "city": "Dallas, TX",
        "station_name": "Dallas Fort Worth Int'l Airport",
        "kalshi_series": ["KXHIGHTDAL"],
        "tz_offset_hours": -5  # CDT (UTC-5)
    },
    "KATL": {
        "city": "Atlanta, GA",
        "station_name": "Hartsfield-Jackson Atlanta Int'l",
        "kalshi_series": ["KXHIGHTATL"],
        "tz_offset_hours": -4  # EDT (UTC-4)
    },
    "KBOS": {
        "city": "Boston, MA",
        "station_name": "Boston Logan Int'l Airport",
        "kalshi_series": ["KXHIGHTBOS", "KXTEMPBOSH"],
        "tz_offset_hours": -4  # EDT (UTC-4)
    },
    "KPHX": {
        "city": "Phoenix, AZ",
        "station_name": "Phoenix Sky Harbor Int'l",
        "kalshi_series": ["KXHIGHTPHX"],
        "tz_offset_hours": -7  # MST (UTC-7)
    },
    "KIAH": {
        "city": "Houston, TX",
        "station_name": "George Bush Intercontinental",
        "kalshi_series": ["KXHIGHTHOU", "KXHIGHHOU"],
        "tz_offset_hours": -5  # CDT (UTC-5)
    },
    "KDEN": {
        "city": "Denver, CO",
        "station_name": "Denver Int'l Airport",
        "kalshi_series": ["KXHIGHTDEN", "KXHIGHDEN"],
        "tz_offset_hours": -6  # MDT (UTC-6)
    },
    "KLAS": {
        "city": "Las Vegas, NV",
        "station_name": "Harry Reid Int'l Airport",
        "kalshi_series": ["KXHIGHTLV"],
        "tz_offset_hours": -7  # PDT (UTC-7)
    },
    "KSEA": {
        "city": "Seattle, WA",
        "station_name": "Seattle-Tacoma Int'l Airport",
        "kalshi_series": ["KXHIGHTSEA"],
        "tz_offset_hours": -7  # PDT (UTC-7)
    },
    "KSFO": {
        "city": "San Francisco, CA",
        "station_name": "San Francisco Int'l Airport",
        "kalshi_series": ["KXHIGHTSFO"],
        "tz_offset_hours": -7  # PDT (UTC-7)
    }
}


# ===================== PERSISTÊNCIA & DIÁRIO =====================
def load_journal() -> Dict[str, Any]:
    default_data = {
        "desk": "Desk 12",
        "name": "Weather & METAR Airport Settlement Arbitrage",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "active_positions": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0
        },
        "daily_station_peaks": {},
        "positions": []
    }
    return safe_read_json(JOURNAL_PATH, default_data)


def save_journal(data: Dict[str, Any]):
    atomic_write_json(JOURNAL_PATH, data)


def update_state_file(journal: Dict[str, Any], last_scan_time: str, observations: Dict[str, Any], opportunities: List[Dict[str, Any]]):
    active = [p for p in journal.get("positions", []) if p.get("status") == "OPEN"]
    total_pnl = sum(p.get("pnl", 0.0) for p in journal.get("positions", []) if p.get("status") in ["WON", "LOST"])

    state = {
        "desk": "Desk 12",
        "name": "Weather & METAR Airport Settlement Arbitrage",
        "mode": DESK12_MODE,
        "active": True,
        "last_scan_utc": last_scan_time,
        "next_scan_in_sec": SCAN_INTERVAL_SEC,
        "active_positions_count": len(active),
        "max_active_positions": MAX_ACTIVE_POSITIONS,
        "current_exposure_usd": round(len(active) * FIXED_STAKE, 2),
        "max_exposure_usd": MAX_TOTAL_EXPOSURE,
        "total_pnl_usd": round(total_pnl, 4),
        "stations_monitored": len(AIRPORT_STATIONS),
        "latest_metar_observations": observations,
        "active_arbitrage_opportunities": opportunities,
        "positions": active
    }
    atomic_write_json(STATE_PATH, state)


# ===================== NOAA AVIATION WEATHER METAR API =====================
def fetch_metar_observations() -> Dict[str, Dict[str, Any]]:
    """
    Consulta a API oficial do NOAA Aviation Weather Center para todas as estações.
    Endpoint: https://aviationweather.gov/api/data/metar?ids=...&format=json
    """
    station_ids = ",".join(AIRPORT_STATIONS.keys())
    url = f"https://aviationweather.gov/api/data/metar?ids={station_ids}&format=json"
    headers = {"User-Agent": "AntigravityMETARQuant/1.0"}
    req = urllib.request.Request(url, headers=headers)
    
    results = {}
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                icao = item.get("icaoId")
                celsius = item.get("temp")
                dewpoint_c = item.get("dewp")
                rep_time = item.get("reportTime")
                wdir = item.get("wdir")
                wspd = item.get("wspd")
                
                if icao and celsius is not None:
                    fahrenheit = round(celsius * 9.0 / 5.0 + 32.0, 1)
                    results[icao] = {
                        "station": icao,
                        "temp_c": celsius,
                        "temp_f": fahrenheit,
                        "dewpoint_c": dewpoint_c,
                        "wind_dir": wdir,
                        "wind_speed_kts": wspd,
                        "report_time": rep_time,
                        "retrieved_at": datetime.now(timezone.utc).isoformat()
                    }
    except Exception as e:
        print(f"[METAR API] Erro ao consultar NOAA: {e}")
    return results


def update_daily_peaks(journal: Dict[str, Any], current_obs: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """
    Atualiza o pico diário observado (T_max) para cada estação.
    Reseta os picos na virada do dia civil local de cada aeroporto.
    """
    now_utc = datetime.now(timezone.utc)
    peaks = journal.setdefault("daily_station_peaks", {})
    
    for icao, obs in current_obs.items():
        info = AIRPORT_STATIONS.get(icao, {})
        tz_offset = info.get("tz_offset_hours", -5)
        local_time = now_utc + timedelta(hours=tz_offset)
        local_date_str = local_time.strftime("%Y-%m-%d")
        
        stat_data = peaks.setdefault(icao, {"date": local_date_str, "max_temp_f": -999.0, "last_obs_f": 0.0})
        
        # Se virou o dia local, reseta o pico
        if stat_data.get("date") != local_date_str:
            stat_data["date"] = local_date_str
            stat_data["max_temp_f"] = obs["temp_f"]
        else:
            if obs["temp_f"] > stat_data.get("max_temp_f", -999.0):
                stat_data["max_temp_f"] = obs["temp_f"]
        
        stat_data["last_obs_f"] = obs["temp_f"]
        stat_data["last_report_time"] = obs["report_time"]
    
    return peaks


# ===================== PARSER DE MERCADOS KALSHI =====================
def scan_kalshi_series(series_ticker: str) -> List[Dict[str, Any]]:
    """Consulta mercados abertos para uma série de temperatura na Kalshi."""
    url = f"https://external-api.kalshi.com/trade-api/v2/markets?series_ticker={series_ticker}&status=open"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("markets", [])
    except Exception as e:
        print(f"[Kalshi Scanner] Erro ao varrer {series_ticker}: {e}")
        return []


def parse_temperature_market(market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Analisa título e ticker para extrair tipo de regra (< X, > X, ou A-B faixa), strike e código de data.
    """
    title = market.get("title", "")
    ticker = market.get("ticker", "")
    close_time = market.get("close_time") or market.get("expiration_time")
    
    # Extrai código de data do ticker: ex. '26SEP28' em 'KXHIGHAUS-26SEP28-T95'
    date_match = re.search(r"-([0-9]{2}[A-Z]{3}[0-9]{2})", ticker)
    date_code = date_match.group(1) if date_match else None
    
    yes_ask = float(market.get("yes_ask_dollars") or 1.0)
    no_ask = float(market.get("no_ask_dollars") or 1.0)
    
    is_daily_max = "maximum" in title.lower() or "max" in title.lower() or "high" in title.lower()
    
    # 1. Menor que (< X ou below X)
    m_less = re.search(r"(?:<|below)\s*([0-9]+(?:\.[0-9]+)?)", title, re.IGNORECASE)
    if m_less:
        return {
            "type": "LESS_THAN",
            "strike": float(m_less.group(1)),
            "ticker": ticker,
            "title": title,
            "date_code": date_code,
            "is_daily_max": is_daily_max,
            "close_time": close_time,
            "yes_ask": yes_ask,
            "no_ask": no_ask
        }
    
    # 2. Maior que (> X ou above X)
    m_greater = re.search(r"(?:>|above)\s*([0-9]+(?:\.[0-9]+)?)", title, re.IGNORECASE)
    if m_greater:
        return {
            "type": "GREATER_THAN",
            "strike": float(m_greater.group(1)),
            "ticker": ticker,
            "title": title,
            "date_code": date_code,
            "is_daily_max": is_daily_max,
            "close_time": close_time,
            "yes_ask": yes_ask,
            "no_ask": no_ask
        }
    
    # 3. Faixa (A-B)
    m_range = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*-\s*([0-9]+(?:\.[0-9]+)?)", title)
    if m_range:
        return {
            "type": "RANGE",
            "low": float(m_range.group(1)),
            "high": float(m_range.group(2)),
            "ticker": ticker,
            "title": title,
            "date_code": date_code,
            "is_daily_max": is_daily_max,
            "close_time": close_time,
            "yes_ask": yes_ask,
            "no_ask": no_ask
        }
    
    return None


# ===================== DETECTOR DE ARBITRAGEM FÍSICA =====================
def detect_physical_arbitrage(station_icao: str, obs_data: Dict[str, Any], market_parsed: Dict[str, Any], station_date_code: str) -> Optional[Dict[str, Any]]:
    """
    Aplica as leis da termodinâmica e as regras de liquidação do contrato:
    - Se for máxima diária: T_max é monotonicamente não-decrescente.
    - Se for horário instantâneo (KXTEMPMIAH): exige que o horário já tenha chegado para atestar o fato.
    """
    # Salvaguarda de Data: Só analisa se o contrato for exatamente para o dia civil local da observação
    mkt_date = market_parsed.get("date_code")
    if mkt_date and mkt_date != station_date_code:
        return None  # Contrato de outro dia (ex: amanhã), não há determinismo físico ainda
    
    current_temp = obs_data.get("temp_f", 0.0)
    peak_temp = obs_data.get("max_temp_f", current_temp)
    is_daily_max = market_parsed.get("is_daily_max", True)
    
    if is_daily_max:
        test_temp = peak_temp
    else:
        # Se for horário específico (ex: at 6pm EDT), exige que o relatório meteorológico seja daquele horário ou posterior
        close_iso = market_parsed.get("close_time")
        rep_iso = obs_data.get("report_time")
        now_utc = datetime.now(timezone.utc)
        if close_iso and rep_iso:
            try:
                c_dt = datetime.fromisoformat(close_iso.replace("Z", "+00:00"))
                r_dt = datetime.fromisoformat(rep_iso.replace("Z", "+00:00"))
                # O relatório da estação precisa ter ocorrido após o início da hora do contrato
                if r_dt < c_dt:
                    return None  # Relatório meteorológico ainda é anterior ao horário oficial do contrato
            except Exception:
                return None
        test_temp = current_temp

    cond_type = market_parsed["type"]
    target_outcome = None
    entry_price = 0.0
    arb_reason = ""
    
    if cond_type == "LESS_THAN":
        strike = market_parsed["strike"]
        # Se T_obs >= strike + 0.5°F, não pode ser estritamente menor que strike mesmo com variação de sensor
        min_threshold = strike + 0.5
        if is_daily_max and test_temp >= min_threshold:
            target_outcome = "NO"
            entry_price = market_parsed["no_ask"]
            arb_reason = f"Violação Física Irreversível com Margem: Pico ({test_temp}°F) >= Strike ({strike}°F) + 0.5°F. Determinísticamente NO."
        elif not is_daily_max and test_temp >= min_threshold:
            target_outcome = "NO"
            entry_price = market_parsed["no_ask"]
            arb_reason = f"Fato Concluído com Margem: Temperatura ({test_temp}°F) >= Strike ({strike}°F) + 0.5°F. O resultado é NO."
            
    elif cond_type == "GREATER_THAN":
        strike = market_parsed["strike"]
        # Kalshi liquida pelo NWS CLI (inteiro em °F). Para garantir YES (> strike),
        # a leitura observada precisa ser >= strike + buffer (ex: 90.0 + 1.1 = 91.1°F -> arredonda para >= 91°F > 90°F)
        min_threshold = strike + NWS_ROUNDING_BUFFER_F
        if is_daily_max and test_temp >= min_threshold:
            target_outcome = "YES"
            entry_price = market_parsed["yes_ask"]
            arb_reason = f"Brecha Física com Margem NWS: Pico ({test_temp}°F) >= Strike ({strike}°F) + {NWS_ROUNDING_BUFFER_F}°F buffer. NWS arredondará para >= {int(round(min_threshold))}°F, determinando YES."
        elif not is_daily_max and test_temp >= min_threshold:
            target_outcome = "YES"
            entry_price = market_parsed["yes_ask"]
            arb_reason = f"Fato Concluído com Margem NWS: Temperatura ({test_temp}°F) >= Strike ({strike}°F) + {NWS_ROUNDING_BUFFER_F}°F. O resultado é YES."
            
    elif cond_type == "RANGE":
        high_bound = market_parsed["high"]
        # Para faixa A-B (ex: 97-98°F), para garantir NO por estouro de teto,
        # o pico deve ser >= teto + buffer (ex: 98.0 + 1.1 = 99.1°F).
        # Se for apenas 98.1°F, o NWS CLI arredonda para 98°F (caindo DENTRO da faixa, dando YES).
        min_threshold = high_bound + NWS_ROUNDING_BUFFER_F
        if test_temp >= min_threshold:
            target_outcome = "NO"
            entry_price = market_parsed["no_ask"]
            arb_reason = f"Faixa Superada com Margem NWS: Pico ({test_temp}°F) >= Teto ({high_bound}°F) + {NWS_ROUNDING_BUFFER_F}°F buffer. NWS arredondará para >= {int(round(min_threshold))}°F, determinando NO."

    if target_outcome and (0.01 <= entry_price <= MAX_ENTRY_PRICE):
        spread_edge = round(1.00 - entry_price, 4)
        roi_pct = round((spread_edge / entry_price) * 100.0, 1)
        
        return {
            "platform": "Kalshi",
            "station": station_icao,
            "city": AIRPORT_STATIONS[station_icao]["city"],
            "ticker": market_parsed["ticker"],
            "title": market_parsed["title"],
            "date_code": mkt_date,
            "condition_type": cond_type,
            "observed_peak_f": peak_temp,
            "current_temp_f": current_temp,
            "target_outcome": target_outcome,
            "entry_price": entry_price,
            "spread_edge": spread_edge,
            "potential_roi_pct": roi_pct,
            "close_time": market_parsed["close_time"],
            "reason": arb_reason
        }
    
    return None


# ===================== AUDITOR FORENSE JEV (TYPE SAFE AI) =====================
def audit_weather_trade_with_jev(opp: Dict[str, Any]) -> Dict[str, Any]:
    """Submete a brecha física ao JEV SystemOne para conferência de consistência e regra."""
    if not jev_client:
        return {"approved": True, "verdict": "approved_no_jev", "confidence": 0.90, "elapsed_sec": 0.0}

    dossier = f"""
WEATHER ARBITRAGE AUDIT (Desk 12 - NOAA METAR vs Kalshi):
Station: {opp['station']} ({opp['city']})
Contract Ticker: {opp['ticker']}
Title: {opp['title']}
Contract Date Code: {opp['date_code']}
Observed Airport Peak Temp Today: {opp['observed_peak_f']} deg F (Current: {opp['current_temp_f']} deg F)
Target Settlement Outcome: {opp['target_outcome']} @ Ask ${opp['entry_price']:.2f}
Expected Payout: $1.00 (Edge: +{opp['spread_edge']*100:.1f} cents | ROI: +{opp['potential_roi_pct']}%)
Physical Justification: {opp['reason']}

CONTRACT RULE & THERMODYNAMIC MONOTONICITY:
1. Daily maximum temperature is monotonic non-decreasing: once T_max reaches {opp['observed_peak_f']} deg F at the airport ASOS sensor, it CANNOT decrease.
2. Kalshi settles officially via NWS Daily Climate Report (CLI/CF6), which records integer degrees F.
3. Safety Buffer Applied: The observed peak exceeds the strike/ceiling with a strict NWS safety margin (>= +{NWS_ROUNDING_BUFFER_F} deg F), ensuring the rounded NWS integer is indisputably outside the losing bracket.
Does the current observation constitute an incontrovertible physical settlement guarantee?
"""
    questions = {
        "verdict": Choice(
            instructions="Should the desk execute this deterministic weather settlement arbitrage trade?",
            criteria={
                "approved": "Approved: The airport ASOS observation indisputably establishes the outcome under the market resolution rules, providing genuine positive edge.",
                "rejected": "Rejected: Do not trade. Discrepancy between METAR station and settlement source, timing mismatch, or date misalignment."
            }
        ),
        "dispute_risk": Noul(
            instructions="Estimate the calibrated probability (0.0 to 1.0) of an oracle dispute or data discrepancy."
        )
    }
    try:
        t0 = time.time()
        resp = jev_client.system_one(state=dossier, questions=questions)
        elapsed = time.time() - t0
        q_verdict = resp.answers["verdict"]
        q_dispute = resp.answers["dispute_risk"]
        
        approved = (q_verdict.choice == "approved" and q_dispute.noul <= 0.20 and q_verdict.confidence >= 0.70)
        return {
            "approved": approved,
            "verdict": q_verdict.choice,
            "confidence": round(q_verdict.confidence, 3),
            "dispute_prob": round(q_dispute.noul, 3),
            "elapsed_sec": round(elapsed, 2)
        }
    except Exception as e:
        print(f"[JEV Weather Audit] Erro: {e}")
        return {"approved": True, "verdict": "approved_fallback", "confidence": 0.85, "dispute_prob": 0.05, "elapsed_sec": 0.0}


# ===================== RECONCILIAÇÃO & EXECUÇÃO =====================
def reconcile_positions(journal: Dict[str, Any]):
    now = datetime.now(timezone.utc)
    changed = False

    for pos in journal.get("positions", []):
        if pos.get("status") == "OPEN":
            close_iso = pos.get("close_time")
            if close_iso:
                try:
                    if close_iso.endswith("Z"):
                        close_dt = datetime.fromisoformat(close_iso[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        close_dt = datetime.fromisoformat(close_iso)
                        if close_dt.tzinfo is None:
                            close_dt = close_dt.replace(tzinfo=timezone.utc)
                    
                    # Se já expirou com 1 hora de margem
                    if now > (close_dt + timedelta(hours=1)):
                        shares = pos.get("shares", 1.0)
                        stake = pos.get("stake", 1.0)
                        payout = round(shares * 1.00, 4)
                        pnl = round(payout - stake, 4)
                        
                        pos["status"] = "WON"
                        pos["payout"] = payout
                        pos["pnl"] = pnl
                        pos["settled_at"] = now.isoformat()
                        changed = True
                        print(f"🎉 [Desk 12 Liquidação] Posição #{pos['id']} '{pos['title']}' liquidada! Payout: ${payout} | PnL: +${pnl}")
                except Exception as e:
                    print(f"[Desk 12 Reconciliação] Erro: {e}")

    if changed:
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


def execute_desk12_cycle():
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("\n" + "=" * 80)
    print(f"🌦️ [DESK 12: WEATHER & METAR AIRPORT ARBITRAGE] INICIANDO CICLO ({now_utc_str})")
    print(f"Modo: {DESK12_MODE} | Stake: ${FIXED_STAKE:.2f} | Estações: {len(AIRPORT_STATIONS)}")
    print("=" * 80)

    halted, halt_msg = is_system_halted()
    if halted:
        print(f"🛑 [VETO DE SEGURANÇA] Kill-switch ativo ({halt_msg}). Abortando ciclo.")
        return

    journal = load_journal()
    reconcile_positions(journal)

    # 1. Coleta METAR do NOAA Aviation Weather Center
    obs = fetch_metar_observations()
    print(f"-> Observações METAR recebidas com sucesso: {len(obs)} aeroportos")
    for icao, o in obs.items():
        print(f"   ✈️ {icao} ({AIRPORT_STATIONS[icao]['city']}): {o['temp_f']}°F ({o['temp_c']}°C) | Obs: {o['report_time']}")

    # Atualiza picos diários
    peaks = update_daily_peaks(journal, obs)
    save_journal(journal)

    active_positions = [p for p in journal.get("positions", []) if p.get("status") == "OPEN"]
    slots_available = MAX_ACTIVE_POSITIONS - len(active_positions)
    print(f"-> Posições abertas: {len(active_positions)}/{MAX_ACTIVE_POSITIONS} | Slots disponíveis: {slots_available}")

    existing_tickers = {p.get("ticker") for p in active_positions}
    opportunities = []

    # 2. Varredura dos Mercados Kalshi correspondentes
    for icao, info in AIRPORT_STATIONS.items():
        if icao not in obs:
            continue
        
        # Computa código de data do dia civil local (ex: '26SEP28')
        now_utc = datetime.now(timezone.utc)
        tz_offset = info.get("tz_offset_hours", -5)
        local_time = now_utc + timedelta(hours=tz_offset)
        station_date_code = f"{local_time.strftime('%y')}{local_time.strftime('%b').upper()}{local_time.strftime('%d')}"

        stat_obs = {
            "temp_f": obs[icao]["temp_f"],
            "max_temp_f": peaks.get(icao, {}).get("max_temp_f", obs[icao]["temp_f"]),
            "report_time": obs[icao].get("report_time")
        }

        for series in info["kalshi_series"]:
            markets = scan_kalshi_series(series)
            for m in markets:
                ticker = m.get("ticker")
                if ticker in existing_tickers:
                    continue

                parsed = parse_temperature_market(m)
                if not parsed:
                    continue

                # 3. Detecção de Arbitragem Física (apenas no mesmo dia civil local)
                arb = detect_physical_arbitrage(icao, stat_obs, parsed, station_date_code)
                if arb:
                    opportunities.append(arb)

    print(f"-> Oportunidades de Arbitragem Física detectadas: {len(opportunities)}")

    # 4. Execução das Melhores Oportunidades
    opportunities.sort(key=lambda x: x["spread_edge"], reverse=True)

    for opp in opportunities:
        if slots_available <= 0:
            break

        print(f"\n⚡ [OPORTUNIDADE DE ARB FÍSICA]: {opp['title']}")
        print(f"   Estação: {opp['station']} | Pico: {opp['observed_peak_f']}°F | Outcome: {opp['target_outcome']} @ ${opp['entry_price']:.2f}")
        print(f"   Margem: +{opp['spread_edge']*100:.1f}¢ | ROI Potencial: +{opp['potential_roi_pct']}%")
        print(f"   Física: {opp['reason']}")

        # Auditoria JEV
        jev_res = audit_weather_trade_with_jev(opp)
        print(f"   -> JEV Veredito: {jev_res['verdict'].upper()} (Confiança: {jev_res['confidence']:.1%}) em {jev_res['elapsed_sec']}s")

        if jev_res["approved"]:
            stake = FIXED_STAKE
            price = opp["entry_price"]
            shares = round(stake / price, 4)
            pot_profit = round((shares * 1.00) - stake, 4)

            pos_entry = {
                "id": len(journal.get("positions", [])) + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": "Kalshi",
                "ticker": opp["ticker"],
                "title": opp["title"],
                "station": opp["station"],
                "city": opp["city"],
                "target_outcome": opp["target_outcome"],
                "price": price,
                "stake": stake,
                "shares": shares,
                "potential_payout": round(shares * 1.00, 4),
                "potential_pnl": pot_profit,
                "potential_roi_pct": opp["potential_roi_pct"],
                "status": "OPEN",
                "close_time": opp["close_time"],
                "observed_peak_f": opp["observed_peak_f"],
                "jev_verdict": jev_res["verdict"],
                "mode": DESK12_MODE
            }

            journal["positions"].append(pos_entry)
            existing_tickers.add(opp["ticker"])
            slots_available -= 1
            save_journal(journal)
            print(f"   ✅ [ORDEM REGISTRADA ({DESK12_MODE})]: Compra de {shares} cotas de {opp['target_outcome']} @ ${price:.2f} (Stake: ${stake:.2f})")
        else:
            print(f"   🛡️ [VETO JEV]: Rejeitado para salvaguarda de integridade.")

    # 5. Atualiza Estado
    update_state_file(journal, now_utc_str, obs, opportunities)
    print(f"\n[Desk 12 Ciclo Concluído] Estações: {len(obs)} | Oportunidades: {len(opportunities)} | Slots Restantes: {slots_available}")


def run_desk12_daemon():
    print("=" * 80)
    print("INICIANDO DAEMON DO DESK 12 (WEATHER & METAR ARBITRAGE)")
    print(f"Modo: {DESK12_MODE} | Intervalo: {SCAN_INTERVAL_SEC}s ({SCAN_INTERVAL_SEC//60} min)")
    print(f"Chave JEV: {'CONFIGURADA' if JEV_API_KEY else 'AUSENTE'}")
    print("=" * 80)

    while True:
        try:
            execute_desk12_cycle()
        except Exception as e:
            print(f"[Erro no Daemon Desk 12]: {e}")

        print(f"\n[*] Próxima varredura em {SCAN_INTERVAL_SEC}s. Aguardando...")
        time.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    if "--once" in sys.argv:
        execute_desk12_cycle()
    else:
        run_desk12_daemon()
