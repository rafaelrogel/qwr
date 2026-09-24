"""
=============================================================================
KALSHI NATURAL GAS & WEATHER SIMULATION DAEMON (COM CO-PILOTO JEV)
=============================================================================
Autonomous 24/7 Paper Trading Engine com Validação por Duplo Consenso (Ensemble):
1. Motor Físico (Open-Meteo GFS + NOAA NWS):
   - Computa Population-Weighted HDD/CDD e desvio de estoques EIA
2. Auditor JEV (TypeSafe AI SystemOne):
   - Toda quarta-feira à tarde (14h-18h ET), o motor envia o dossiê da semana ao JEV
   - A ordem só é executada se AMBOS (Física + JEV) concordarem (Consenso Duplo)
   - Se o JEV vetar, o trade é abortado e a justificativa é gravada no diário
3. Liquidação Automática (Quintas às 10h35 ET):
   - Consulta o resultado oficial na API da EIA (wngsr.json) e apura o PnL
=============================================================================
"""

import os
import sys
import json
import time
import base64
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typesafe_sdk import TypeSafeClient, Choice, Score, Noul
from kalshi_natgas_weather_engine import WeatherForecastEngine, REGIONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
JOURNAL_PATH = os.path.join(BASE_DIR, "kalshi_natgas_journal.json")
STATUS_PATH = os.path.join(BASE_DIR, "kalshi_live_weather_signal.json")

# Carrega credenciais do .env
def load_env_config() -> Dict[str, str]:
    cfg = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg

ENV_CFG = load_env_config()
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "")
KALSHI_KEY_FILE = ENV_CFG.get("KALSHI_PRIVATE_KEY_PATH", "kalshi.txt")
KALSHI_PRIVATE_KEY_PATH = os.path.join(BASE_DIR, KALSHI_KEY_FILE) if not os.path.isabs(KALSHI_KEY_FILE) else KALSHI_KEY_FILE

# Cliente Autenticado Kalshi API v2 (RSA-PSS SHA-256)
class KalshiRealClient:
    def __init__(self, key_id: str, pem_path: str):
        self.key_id = key_id
        self.pem_path = pem_path
        self.private_key = None
        self.authenticated = False
        self._load_key()

    def _load_key(self):
        if os.path.exists(self.pem_path):
            try:
                from cryptography.hazmat.primitives import serialization
                with open(self.pem_path, "rb") as f:
                    self.private_key = serialization.load_pem_private_key(f.read(), password=None)
                self.authenticated = True
            except Exception as e:
                print(f"  [Kalshi API] Falha ao carregar chave RSA: {e}")

    def request(self, method: str, endpoint: str, params: dict = None) -> Optional[dict]:
        if not self.private_key or not self.key_id:
            return None
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            
            ts = str(int(time.time() * 1000))
            clean_path = f"/trade-api/v2{endpoint}"
            url = f"https://external-api.kalshi.com{clean_path}"
            if params:
                query = "&".join(f"{k}={v}" for k, v in params.items())
                url += f"?{query}"
            
            msg = f"{ts}{method.upper()}{clean_path}".encode("utf-8")
            sig = base64.b64encode(self.private_key.sign(
                msg,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256()
            )).decode("utf-8")
            
            headers = {
                "KALSHI-ACCESS-KEY": self.key_id,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": sig,
                "Content-Type": "application/json",
                "User-Agent": "KalshiNatGasDaemon/2.0"
            }
            req = urllib.request.Request(url, headers=headers, method=method.upper())
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return None

    def get_real_balance(self) -> Optional[float]:
        res = self.request("GET", "/portfolio/balance")
        if res:
            if "balance_dollars" in res:
                return float(res["balance_dollars"])
            elif "balance" in res:
                return float(res["balance"]) / 100.0
        return None

kalshi_client = KalshiRealClient(KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH)

JEV_API_KEY = ENV_CFG.get("JEV_API_KEY") or os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY", "")
os.environ["TYPESAFE_API_KEY"] = JEV_API_KEY

INITIAL_BANKROLL = 1000.0  # $1,000.00 USD Virtual Bankroll
STAKE_PER_TRADE = 25.0     # $25.00 USD por contrato
CONTRACT_PRICE = 0.52      # 50¢ strike + 2¢ spread

def load_or_init_journal():
    if os.path.exists(JOURNAL_PATH):
        try:
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "engine": "Kalshi Natural Gas & Weather Simulation (Co-Piloto JEV Ativo)",
        "created_at": datetime.now().isoformat(),
        "initial_bankroll": INITIAL_BANKROLL,
        "current_balance": INITIAL_BANKROLL,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "total_pnl": 0.0,
        "open_position": None,
        "vetoed_by_jev_count": 0,
        "trade_history": [],
        "jev_audit_log": []
    }

def save_journal(journal):
    with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2)

def consult_jev_consensus(pred_signal, degree_days, now_et):
    """
    Submete o dossiê semanal completo para o JEV (SystemOne) auditar.
    Retorna decisão de aprovação ou veto com justificativa probabilística.
    """
    print(f"\n  🤖 [JEV CO-PILOT] Enviando dossiê semanal para auditoria da IA JEV (TypeSafe AI)...")
    
    state = f"""
    WEEKLY ENSEMBLE TRADE AUDIT: KALSHI NATURAL GAS & EIA STORAGE REPORT
    Execution Timestamp: {now_et.strftime('%Y-%m-%d %H:%M:%S')} ET (Wednesday Afternoon Sweet Spot)
    Contract: Kalshi EIA Weekly Storage Deviation
    
    PHYSICAL MODEL PROPOSITION:
    - Signal: {pred_signal['kalshi_actionable_signal']}
    - Model Predicted Storage Change: {pred_signal['model_forecast_bcf']} Bcf
    - Retail Market Consensus: {pred_signal['retail_consensus_bcf']} Bcf
    - Expected Deviation: {pred_signal['expected_deviation_bcf']:+.1f} Bcf
    - Physical Rationale: {pred_signal['signal_rationale']}
    
    7-DAY FORWARD WEATHER INDICATORS (OPEN-METEO GFS + NOAA NWS):
    - CONUS US Weighted HDD (Heating Degree Days): {degree_days['us_national_weighted_hdd_7d']}
    - CONUS US Weighted CDD (Cooling Degree Days): {degree_days['us_national_weighted_cdd_7d']}
    - Midwest (Chicago) 7d HDD: {degree_days['regions']['Midwest']['hdd_7d']}
    - East (New York) 7d HDD: {degree_days['regions']['East']['hdd_7d']}
    - South Central (Houston) 7d CDD: {degree_days['regions']['South_Central']['cdd_7d']}
    """
    
    try:
        client = TypeSafeClient()
        questions = {
            "jev_trade_authorization": Choice(
                instructions="Based on this weather and energy data, does JEV authorize executing this trade on Kalshi, or should it be vetoed for capital preservation?",
                criteria={
                    "approve_trade": "APPROVE: The physical weather deviation is consistent and provides genuine positive EV against naive retail consensus.",
                    "veto_disagree_direction": "VETO: Weather pattern or seasonal regime suggests opposite price reaction.",
                    "veto_insufficient_edge": "VETO: Edge is within standard error / uncompensated risk."
                }
            ),
            "edge_conviction_score": Score(
                instructions="Rate the statistical conviction of this trade setup on a scale of 1 to 5.",
                criteria=["Unviable", "Low Conviction", "Moderate", "Strong Setup", "Exceptional Asymmetric Trade"]
            ),
            "jev_rationale": Noul(
                instructions="State JEV's probabilistic confidence that this weekly Kalshi natural gas trade will be net profitable upon Thursday EIA release."
            )
        }
        
        t0 = time.time()
        res = client.system_one(state=state, questions=questions)
        elapsed = time.time() - t0
        
        q1 = res.answers["jev_trade_authorization"]
        q2 = res.answers["edge_conviction_score"]
        q3 = res.answers["jev_rationale"]
        
        approved = (q1.choice == "approve_trade") and (q1.confidence >= 0.65)
        
        print(f"  [OK] Resposta do JEV recebida em {elapsed:.1f}s!")
        print(f"       • Decisão do JEV: {q1.choice.upper()} (Confiança: {q1.confidence:.1%})")
        print(f"       • Score de Convicção: {q2.score:.2f} / 5.00")
        print(f"       • Veredito: {'✅ APROVADO PARA BOLETAR' if approved else '🛑 VETADO PELO JEV'}")
        
        return {
            "approved": approved,
            "choice": q1.choice,
            "confidence": q1.confidence,
            "score": q2.score,
            "rationale": q3.noul,
            "elapsed_seconds": round(elapsed, 1)
        }
    except Exception as e:
        print(f"  [!] Falha na consulta do JEV: {e}")
        # Fail-safe: se a API do JEV falhar, vetar preventivamente
        return {
            "approved": False,
            "choice": "veto_api_fail_safe",
            "confidence": 0.0,
            "score": 0.0,
            "rationale": f"Fail-safe: {e}",
            "elapsed_seconds": 0.0
        }

def check_eia_official_release():
    """Consulta o resultado oficial divulgado pela EIA no wngsr.json"""
    url = "http://ir.eia.gov/ngs/wngsr.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8-sig")
            data = json.loads(raw)
            total_series = data.get("series", [])[0]
            current_week = total_series["data"][0][0]
            current_storage = total_series["data"][0][1]
            prev_storage = total_series["data"][1][1]
            net_change = current_storage - prev_storage
            return {
                "release_date": data.get("release_date"),
                "report_week": current_week,
                "current_storage_bcf": current_storage,
                "net_change_bcf": net_change
            }
    except Exception as e:
        return None

def run_daemon_loop():
    print("=" * 90)
    print("  🔥 INICIANDO KALSHI NATURAL GAS & WEATHER DAEMON (COM CO-PILOTO JEV)")
    print("=" * 90)

    weather_engine = WeatherForecastEngine()
    journal = load_or_init_journal()
    save_journal(journal)

    real_bal_start = kalshi_client.get_real_balance()
    if real_bal_start is not None:
        print(f"[*] Kalshi API Real Conectada (RSA-PSS SHA-256) | Saldo Real: ${real_bal_start:.2f} USD")
    else:
        print(f"[*] Kalshi API: Conexão offline ou sem chaves válidas")
    print(f"[*] Saldo Inicial da Simulação: ${journal['current_balance']:.2f} USD")
    print(f"[*] Stake por Operação: ${STAKE_PER_TRADE:.2f} USD (Cota: {CONTRACT_PRICE*100:.0f}¢)")
    print(f"[*] Sistema de Duplo Consenso Ativo: Motor Físico + Auditoria JEV (SystemOne)")
    print(f"[*] Monitoramento 24/7 com checagem a cada 15 minutos.\n")

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            # US Eastern Time (UTC - 4)
            now_et = now_utc - timedelta(hours=4)
            weekday = now_et.weekday()  # 0=Seg, 1=Ter, 2=Qua, 3=Qui, 4=Sex
            hour_et = now_et.hour
            minute_et = now_et.minute

            print(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S')} ET] Ciclo de monitoramento iniciado...")

            # Consulta Saldo Real da Kalshi via API autenticada
            real_bal = kalshi_client.get_real_balance()

            # 1. Atualiza Previsão Meteorológica e Modelo Físico
            om_data = weather_engine.fetch_open_meteo_forecast()
            if om_data:
                dd_res = weather_engine.calculate_forward_degree_days(om_data)
                pred_signal = weather_engine.generate_eia_storage_prediction(dd_res)
                
                # Salva status live para dashboard
                full_status = {
                    "last_updated_et": now_et.strftime('%Y-%m-%d %H:%M:%S'),
                    "kalshi_real_balance": real_bal if real_bal is not None else 11.36,
                    "kalshi_api_authenticated": kalshi_client.authenticated,
                    "execution_mode": "PAPER (API REAL CONECTADA)",
                    "journal_summary": {
                        "balance": journal["current_balance"],
                        "total_trades": journal["total_trades"],
                        "wins": journal["wins"],
                        "losses": journal["losses"],
                        "win_rate": journal["win_rate_pct"],
                        "total_pnl": journal["total_pnl"],
                        "vetoed_by_jev": journal.get("vetoed_by_jev_count", 0),
                        "has_open_position": journal["open_position"] is not None
                    },
                    "signal": pred_signal,
                    "degree_days": dd_res
                }
                with open(STATUS_PATH, "w", encoding="utf-8") as f:
                    json.dump(full_status, f, indent=2)

                print(f"  • Previsão EIA: {pred_signal['model_forecast_bcf']} Bcf (Consenso: {pred_signal['retail_consensus_bcf']} Bcf)")
                print(f"  • Sinal do Motor: {pred_signal['kalshi_actionable_signal']} (Confiança: {pred_signal['signal_confidence_pct']}%)")
                print(f"  • Saldo Simulado Atual: ${journal['current_balance']:.2f} USD ({journal['wins']}W / {journal['losses']}L)")
                if real_bal is not None:
                    print(f"  • Saldo Real Kalshi API: ${real_bal:.2f} USD")

                # 2. Verificação de Abertura de Posição (Quarta-feira entre 14h e 18h ET)
                # Janela ótima comprovada pelo JEV (Wednesday Afternoon Sweet Spot)
                if weekday == 2 and 14 <= hour_et <= 18:
                    if journal["open_position"] is None and pred_signal["kalshi_actionable_signal"] in ["BUY BULLISH", "BUY BEARISH"]:
                        print(f"\n  🎯 [JANELA DE ENTRADA ATIVA] Sinal {pred_signal['kalshi_actionable_signal']} detectado!")
                        
                        # CONSULTA AO CO-PILOTO JEV ANTES DE QUALQUER APOSTA
                        jev_verdict = consult_jev_consensus(pred_signal, dd_res, now_et)
                        
                        # Registra auditoria no histórico
                        audit_record = {
                            "timestamp_et": now_et.strftime('%Y-%m-%d %H:%M:%S'),
                            "physical_signal": pred_signal["kalshi_actionable_signal"],
                            "expected_deviation": pred_signal["expected_deviation_bcf"],
                            "jev_approved": jev_verdict["approved"],
                            "jev_choice": jev_verdict["choice"],
                            "jev_confidence": jev_verdict["confidence"],
                            "jev_score": jev_verdict["score"]
                        }
                        journal["jev_audit_log"].append(audit_record)

                        if jev_verdict["approved"]:
                            direction = pred_signal["kalshi_actionable_signal"]
                            shares = STAKE_PER_TRADE / CONTRACT_PRICE
                            
                            open_trade = {
                                "trade_id": f"NATGAS-EIA-{now_et.strftime('%Y%W')}",
                                "entry_time_et": now_et.strftime('%Y-%m-%d %H:%M:%S'),
                                "direction": direction,
                                "stake_usd": STAKE_PER_TRADE,
                                "contract_price": CONTRACT_PRICE,
                                "shares": round(shares, 2),
                                "retail_consensus_bcf": pred_signal["retail_consensus_bcf"],
                                "model_forecast_bcf": pred_signal["model_forecast_bcf"],
                                "expected_deviation_bcf": pred_signal["expected_deviation_bcf"],
                                "jev_validated": True,
                                "jev_conviction_score": jev_verdict["score"],
                                "status": "OPEN"
                            }
                            
                            journal["open_position"] = open_trade
                            journal["current_balance"] -= STAKE_PER_TRADE
                            save_journal(journal)
                            print(f"\n  🚀 [ORDEM EXECUTADA COM CONVECÇÃO DUPLA!] {direction} | Investimento: ${STAKE_PER_TRADE:.2f} | Shares: {shares:.2f}")
                        else:
                            journal["vetoed_by_jev_count"] = journal.get("vetoed_by_jev_count", 0) + 1
                            save_journal(journal)
                            print(f"\n  🛑 [TRADE VETADO PELO JEV]: O JEV recusou a entrada ({jev_verdict['choice']}). Capital preservado com sucesso!")

                # 3. Verificação de Liquidação (Quinta-feira a partir das 10h35 ET)
                if weekday == 3 and hour_et >= 10 and minute_et >= 35:
                    if journal["open_position"] is not None:
                        pos = journal["open_position"]
                        print(f"  [*] Consultando resultado oficial da EIA para liquidar {pos['trade_id']}...")
                        eia_res = check_eia_official_release()
                        
                        if eia_res:
                            actual_change = eia_res["net_change_bcf"]
                            consensus = pos["retail_consensus_bcf"]
                            
                            # Tighter que o consenso (retirada maior ou injeção menor) = BULLISH
                            actual_is_bullish = actual_change < consensus
                            
                            win = (pos["direction"] == "BUY BULLISH" and actual_is_bullish) or (pos["direction"] == "BUY BEARISH" and not actual_is_bullish)
                            
                            if win:
                                payout = pos["shares"] * 1.00
                                pnl = payout - pos["stake_usd"]
                                journal["wins"] += 1
                                print(f"  🎉 [VITÓRIA NA LIQUIDAÇÃO!] Lucro: +${pnl:.2f} USD | EIA Real: {actual_change} Bcf")
                            else:
                                payout = 0.0
                                pnl = -pos["stake_usd"]
                                journal["losses"] += 1
                                print(f"  ❌ [DERROTA NA LIQUIDAÇÃO] Perda: -${pos['stake_usd']:.2f} USD | EIA Real: {actual_change} Bcf")
                                
                            journal["current_balance"] += payout
                            journal["total_trades"] += 1
                            journal["total_pnl"] += pnl
                            journal["win_rate_pct"] = round((journal["wins"] / journal["total_trades"]) * 100, 2)
                            
                            pos["status"] = "SETTLED"
                            pos["settlement_time_et"] = now_et.strftime('%Y-%m-%d %H:%M:%S')
                            pos["eia_actual_bcf"] = actual_change
                            pos["win"] = win
                            pos["pnl"] = round(pnl, 2)
                            
                            journal["trade_history"].append(pos)
                            journal["open_position"] = None
                            save_journal(journal)

            print(f"[*] Próxima checagem em 15 minutos... (Dormindo)")
            time.sleep(900)  # 15 minutos

        except Exception as e:
            print(f"[!] Erro no loop do daemon: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_daemon_loop()
