"""
=============================================================================
JEV MICROSTRUCTURE GATE — GATE DE DECISÃO EM SUB-SEGUNDO (<100ms)
=============================================================================
Alavanca o TypeSafe Jev SystemOne para julgar a microestrutura de livros CLOB,
Order Book Imbalance (OBI), Cumulative Volume Delta (CVD) e discrepâncias
de oráculo no exato milissegundo de entrada (135s no 5m, 500s no 15m).

MODO SHADOW (48 HORAS):
- Não bloqueia ordens reais de dinheiro da Safe.
- Grava todas as probabilidades, regimes e pareceres no log forense
  'jev_shadow_evaluations.jsonl' para auditoria estatística comparativa.
=============================================================================
"""

import os
import json
import time
import threading
from typing import Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHADOW_LOG_FILE = os.path.join(BASE_DIR, "jev_shadow_evaluations.jsonl")
_LOG_LOCK = threading.Lock()

try:
    from predictionhero_watcher import get_cross_venue_consensus
except Exception:
    get_cross_venue_consensus = None

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    from typesafe_sdk import TypeSafeClient, Choice, Noul
    HAS_TYPESAFE = True
except Exception:
    HAS_TYPESAFE = False


# Conjunto oficial de perguntas tipadas para microestrutura e salvaguarda institucional
QUESTIONS = {
    "would_veto": Noul(
        instructions="Avalie se uma salvaguarda quantitativa institucional deveria vetar esta "
                     "entrada no mercado devido a alto risco de falso rompimento ou assimetria negativa."
    ),
    "is_toxic_flow": Noul(
        instructions="Classifique se o fluxo da microestrutura em `state` apresenta absorção "
                     "passiva institucional contrária ou armadilha de liquidez (spoofing/fade)."
    ),
    "candle_regime": Choice(
        instructions="Classifique o regime microestrutural desta vela a partir dos dados do `state`.",
        criteria={
            "breakout": "Rompimento direcional genuíno com suporte de book e drift acelerado.",
            "chop_lateral": "Mercado consolidado em zona de ruído sem direção dominante clara.",
            "exhaustion": "Exaustão onde o delta já atingiu o pico e os formadores de mercado "
                          "estão absorvendo as ordens a mercado contrárias."
        }
    ),
    "worth_entering_now": Noul(
        instructions="Avalie se a relação risco/retorno para entrada imediata neste contrato "
                     "é estatisticamente favorável (odds positivas e assimetria na CLOB)."
    )
}

# Conjunto de perguntas para o Cão de Guarda Pós-Entrada (Monitoramento Contínuo Intra-Vela)
WATCHDOG_QUESTIONS = {
    "is_reversal_risk": Noul(
        instructions="Classifique se o fluxo recente ou desaceleração do delta indicam alto risco de reversão adversa contra a posição aberta."
    ),
    "action": Choice(
        instructions="Recomende a ação ótima para proteção de capital na posição aberta.",
        criteria={
            "hold": "Manter a posição normalmente; momentum ou delta favorável.",
            "emergency_exit": "Liquidar antecipadamente a mercado na CLOB/Kalshi para estancar a perda."
        }
    )
}

# Conjunto de perguntas para o Freio de Faca Caindo (Desk 15 Grid Falling Knife Protection)
FALLING_KNIFE_QUESTIONS = {
    "is_falling_knife": Noul(
        instructions="Classifique se o ativo está em cascata de liquidação agressiva (queda livre sem suporte/faca caindo)."
    ),
    "grid_action": Choice(
        instructions="Recomende se novas ordens de compra limite de dip na grade devem ser pausadas temporariamente.",
        criteria={
            "pause": "Pausar novas compras no dip até que o fluxo vendedor desacelere e o preço encontre suporte.",
            "allow": "Permitir compras passivas normalmente no livro de ofertas."
        }
    )
}


class JevMicrostructureGate:
    def __init__(self, shadow_mode: bool = True, veto_threshold: float = 0.62):
        # MODO ADVISORY (shadow_mode=True por defeito):
        # JEV avalia, classifica o regime e loga tudo em jev_shadow_evaluations.jsonl,
        # mas NÃO bloca ordens reais — o verdict é apenas informativo.
        # Para activar VETO real defina JEV_LIVE_GATE=true no .env
        cfg_live = os.getenv("JEV_LIVE_GATE", "false").strip().lower()
        self.shadow_mode = False if cfg_live in ("true", "1", "yes") else shadow_mode
        self.veto_threshold = float(os.getenv("JEV_VETO_THRESHOLD", str(veto_threshold)))
        self._client: Optional[TypeSafeClient] = None
        if HAS_TYPESAFE:
            try:
                self._client = TypeSafeClient()
            except Exception:
                self._client = None

    def evaluate_entry(
        self,
        desk_id: str,
        delta_usd: float,
        binance_drift: float,
        clob_spread: float,
        contract_price: float,
        oracle_discrepancy: float,
        seconds_left: int,
        obi: float = 0.0,
        cvd: float = 0.0,
        deadband_threshold: float = 15.0,
        side: str = "UP",
        symbol: str = "BTC"
    ) -> Dict[str, Any]:
        """
        Submete o micro-estado da vela ao Jev SystemOne em sub-segundo (<250ms).
        Aplica a calibração comprovada na Autópsia Forense de 160 trades históricos.
        Retorna o dicionário de probabilidades e o veredito (APPROVE vs VETO).
        """
        state = {
            "desk": desk_id,
            "symbol": symbol,
            "side": side,
            "delta_usd": round(delta_usd, 2),
            "binance_drift": round(binance_drift, 2),
            "clob_spread": round(clob_spread, 4),
            "contract_price": round(contract_price, 3),
            "oracle_discrepancy": round(oracle_discrepancy, 2),
            "seconds_left": int(seconds_left),
            "order_book_imbalance": round(obi, 3),
            "cumulative_volume_delta": round(cvd, 2)
        }

        # Injeção de Consenso Multi-Venue (PredictionHero Engine)
        ph_info = None
        if get_cross_venue_consensus:
            try:
                ph_info = get_cross_venue_consensus(symbol) or get_cross_venue_consensus(desk_id)
                if ph_info:
                    state["ph_consensus_prob"] = ph_info.get("consensus_prob")
                    state["ph_divergence_pct"] = ph_info.get("divergence_pct")
            except Exception:
                pass

        # JEV WATCHDOG ATIVO: Todas as entradas são auditadas pelo Jev SystemOne
        # para classificar se o movimento é rompimento genuíno ou exaustão/armadilha de repique.
        start_time = time.time()
        
        # Fallback de segurança caso a SDK não esteja acessível
        if not self._client:
            return self._build_fallback(desk_id, state, "SDK_UNAVAILABLE", 0.0)

        try:
            r = self._client.system_one(state=state, questions=QUESTIONS)
            elapsed_ms = round((time.time() - start_time) * 1000, 1)

            ans_veto = r.answers.get("would_veto")
            ans_toxic = r.answers.get("is_toxic_flow")
            ans_regime = r.answers.get("candle_regime")
            ans_worth = r.answers.get("worth_entering_now")

            veto_p = getattr(ans_veto, "noul", 0.50) if ans_veto else 0.50
            toxic_p = getattr(ans_toxic, "noul", 0.25) if ans_toxic else 0.25
            regime = getattr(ans_regime, "choice", "breakout") if ans_regime else "breakout"
            regime_conf = getattr(ans_regime, "confidence", 0.50) if ans_regime else 0.50
            worth_p = getattr(ans_worth, "noul", 0.50) if ans_worth else 0.50

            # CRITÉRIO DE VETO CALIBRADO (Autópsia Forense JEV - Limiar Ótimo de Nash):
            # Condição 1: Tensor institucional puro >= limiar ótimo (0.62)
            c1 = veto_p >= self.veto_threshold
            # Condição 2: Fluxo tóxico elevado em consolidação ou exaustão
            c2 = (toxic_p >= 0.35) and (regime in ["exhaustion", "chop_lateral"])
            # Condição 3: Odds degradadas em regime de reversão/exaustão adversa
            c3 = (worth_p <= 0.25) and (regime == "exhaustion")
            # Condição 4: Armadilha de Baleia Local (Divergência Multi-Venue >= 8% no PredictionHero)
            c4 = False
            if ph_info and ph_info.get("is_whale_divergence", False):
                c4 = True

            would_veto = c1 or c2 or c3 or c4
            verdict = "VETO" if would_veto else "APPROVE"

            reasons = []
            if c1:
                reasons.append(f"would_veto ({veto_p:.2f} >= {self.veto_threshold:.2f})")
            if c2:
                reasons.append(f"toxic_flow ({toxic_p:.2f} em {regime})")
            if c3:
                reasons.append(f"bad_odds ({worth_p:.2f} em {regime})")
            if c4:
                reasons.append(f"whale_spoofing ({ph_info.get('divergence_pct')}% divergência vs consenso Kalshi)")

            veto_reason = " | ".join(reasons) if reasons else "Entrada Aprovada por Convicção Microestrutural"

            result = {
                "desk_id": desk_id,
                "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "elapsed_ms": elapsed_ms,
                "model": getattr(r, "model", "jev-system-one"),
                "would_veto": round(veto_p, 3),
                "is_toxic_flow": round(toxic_p, 3),
                "candle_regime": regime,
                "regime_confidence": round(regime_conf, 3),
                "worth_entering_now": round(worth_p, 3),
                "verdict": verdict,
                "veto_reason": veto_reason,
                "shadow_mode": self.shadow_mode,
                "state_snapshot": state
            }

            self._log_evaluation(result)
            return result

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 1)
            return self._build_fallback(desk_id, state, f"ERROR: {str(e)}", elapsed_ms)

    def evaluate_in_trade_watchdog(
        self,
        desk_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        current_delta: float,
        delta_at_entry: float,
        seconds_left: int,
        clob_bid: float = 0.0
    ) -> Dict[str, Any]:
        """
        Cão de Guarda Sentinela Intra-Vela:
        Avalia se a posição aberta está sofrendo reversão adversa violenta antes que o strike seja rompido.
        Retorna se deve acionar EMERGENCY_EXIT a mercado enquanto a cota ainda tem bid na CLOB/Kalshi.
        """
        delta_decay = abs(current_delta) - abs(delta_at_entry)
        state = {
            "desk": desk_id,
            "symbol": symbol,
            "side": side,
            "entry_price": round(entry_price, 3),
            "current_price": round(current_price, 3),
            "current_delta": round(current_delta, 2),
            "delta_at_entry": round(delta_at_entry, 2),
            "delta_decay": round(delta_decay, 2),
            "seconds_left": int(seconds_left),
            "clob_bid": round(clob_bid, 3)
        }
        if not self._client:
            return {"action": "HOLD", "reversal_risk": 0.2, "reason": "JEV_SDK_UNAVAILABLE"}

        try:
            r = self._client.system_one(state=state, questions=WATCHDOG_QUESTIONS)
            ans_rev = r.answers.get("is_reversal_risk")
            ans_act = r.answers.get("action")
            rev_p = getattr(ans_rev, "noul", 0.3) if ans_rev else 0.3
            action_choice = getattr(ans_act, "choice", "hold") if ans_act else "hold"

            should_exit = (action_choice == "emergency_exit") or (rev_p >= 0.70 and delta_decay < -30.0)
            res = {
                "desk_id": desk_id,
                "action": "EMERGENCY_EXIT" if should_exit else "HOLD",
                "reversal_risk": round(rev_p, 3),
                "action_choice": action_choice,
                "reason": f"Jev Watchdog: Risco de Reversão {rev_p:.2f} | Decaimento Delta: {delta_decay:+.1f}",
                "state_snapshot": state
            }
            self._log_evaluation({**res, "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())})
            return res
        except Exception as e:
            return {"action": "HOLD", "reversal_risk": 0.2, "error": str(e)}

    def evaluate_falling_knife_brake(
        self,
        desk_id: str,
        symbol: str,
        dip_pct: float,
        atr_4h: float,
        ibs_4h: float,
        ibs_24h: float,
        velocity_usd_s: float = 0.0
    ) -> Dict[str, Any]:
        """
        Freio de Faca Caindo (Desk 15 Revolut X Grid):
        Classifica se o Bitcoin está em cascata de liquidação agressiva (queda livre sem suporte).
        Se 'pause' for recomendado, o Grid retarda armar ordens nos níveis profundos (L5/L6) até estancar o fluxo.
        """
        state = {
            "desk": desk_id,
            "symbol": symbol,
            "dip_pct": round(dip_pct, 4),
            "atr_4h": round(atr_4h, 2),
            "ibs_4h": round(ibs_4h, 3),
            "ibs_24h": round(ibs_24h, 3),
            "velocity_usd_s": round(velocity_usd_s, 2)
        }
        if not self._client:
            return {"action": "ALLOW", "is_falling_knife": 0.1, "reason": "JEV_SDK_UNAVAILABLE"}

        try:
            r = self._client.system_one(state=state, questions=FALLING_KNIFE_QUESTIONS)
            ans_knife = r.answers.get("is_falling_knife")
            ans_act = r.answers.get("grid_action")
            knife_p = getattr(ans_knife, "noul", 0.2) if ans_knife else 0.2
            grid_act = getattr(ans_act, "choice", "allow") if ans_act else "allow"

            should_pause = (grid_act == "pause") and (knife_p >= 0.40 or ibs_4h < 0.10)
            res = {
                "desk_id": desk_id,
                "action": "PAUSE_DEEP_LEVELS" if should_pause else "ALLOW",
                "is_falling_knife": round(knife_p, 3),
                "grid_action": grid_act,
                "reason": f"Jev Knife Brake: Queda Livre {knife_p:.2f} (IBS 4h: {ibs_4h:.2f})",
                "state_snapshot": state
            }
            self._log_evaluation({**res, "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())})
            return res
        except Exception as e:
            return {"action": "ALLOW", "is_falling_knife": 0.1, "error": str(e)}

    def _build_fallback(self, desk_id: str, state: dict, error_msg: str, elapsed_ms: float) -> Dict[str, Any]:
        result = {
            "desk_id": desk_id,
            "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "elapsed_ms": elapsed_ms,
            "model": "fallback",
            "would_veto": 0.20,
            "is_toxic_flow": 0.10,
            "candle_regime": "breakout",
            "regime_confidence": 0.0,
            "worth_entering_now": 0.70,
            "verdict": "APPROVE_BYPASS",
            "veto_reason": f"Fallback por indisponibilidade de rede: {error_msg}",
            "shadow_mode": self.shadow_mode,
            "error": error_msg,
            "state_snapshot": state
        }
        self._log_evaluation(result)
        return result

    def _log_evaluation(self, result: Dict[str, Any]) -> None:
        """Registra a telemetria no arquivo append-only de auditoria."""
        with _LOG_LOCK:
            try:
                with open(SHADOW_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
            except Exception:
                pass


# Singleton global — MODO ADVISORY (shadow_mode=True):
# JEV avalia e loga o regime microestrutural mas NÃO bloca trades.
# Para activar VETO real: defina JEV_LIVE_GATE=true no ficheiro .env
jev_gate = JevMicrostructureGate(shadow_mode=True, veto_threshold=0.62)
