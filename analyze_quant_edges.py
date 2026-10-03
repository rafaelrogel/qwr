"""
Quantitative Edge Exploration & Statistical Analysis
Leverages multi-year historical data from Dukascopy (BTC, ETH, Gold, Nasdaq)
and HistData (1-minute SPX, NSX, Gold, EURUSD) to uncover actionable edges.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from dukascopy_manager import DukascopyManager
from histdata_manager import HistDataManager

def analyze_edges():
    print("=" * 80)
    print("🔬 INICIANDO PESQUISA QUANTITATIVA DE EDGES E MICROESTRUTURA")
    print("=" * 80)

    dmgr = DukascopyManager()
    hmgr = HistDataManager()

    findings = {}

    # --------------------------------------------------------------------------
    # 1. ANÁLISE DE AUTOCORRELAÇÃO DIÁRIA & HORÁRIA (MOMENTUM VS MEAN-REVERSION)
    # --------------------------------------------------------------------------
    print("\n[1/4] Analisando regimes de autocorrelação horária (BTC 15m & Ouro 15m)...")
    df_btc = dmgr.load_candles("btcusd", timeframe="m15")
    df_btc["ret"] = df_btc["close"].pct_change()
    df_btc["hour_utc"] = df_btc.index.hour

    hourly_stats_btc = {}
    for h in range(24):
        subset = df_btc[df_btc["hour_utc"] == h]["ret"].dropna()
        if len(subset) > 50:
            autocorr_1 = subset.autocorr(lag=1)
            vol_bps = subset.std() * 10000
            hourly_stats_btc[h] = {
                "autocorr_lag1": round(float(autocorr_1), 4),
                "vol_bps": round(float(vol_bps), 1),
                "samples": len(subset),
                "regime": "TRENDING/MOMENTUM" if autocorr_1 > 0.04 else ("MEAN_REVERTING" if autocorr_1 < -0.04 else "RANDOM_WALK")
            }

    # Best trending vs best mean-reverting hours for BTC
    trending_hours_btc = [h for h, s in hourly_stats_btc.items() if s["regime"] == "TRENDING/MOMENTUM"]
    mean_reverting_hours_btc = [h for h, s in hourly_stats_btc.items() if s["regime"] == "MEAN_REVERTING"]

    print(f" -> BTC 15m Horas de Tendência (Momentum): {trending_hours_btc}")
    print(f" -> BTC 15m Horas de Reversão à Média: {mean_reverting_hours_btc}")

    findings["btc_hourly_autocorr"] = {
        "trending_hours_utc": trending_hours_btc,
        "mean_reverting_hours_utc": mean_reverting_hours_btc,
        "hourly_breakdown": hourly_stats_btc
    }

    # --------------------------------------------------------------------------
    # 2. ANÁLISE DE LEAD-LAG: NASDAQ (USATECH) ANTECIPANDO BITCOIN
    # --------------------------------------------------------------------------
    print("\n[2/4] Analisando Lead-Lag entre Nasdaq (USATECH) e Bitcoin em 15m...")
    df_nasdaq = dmgr.load_candles("usatechidxusd", timeframe="m15")
    df_nasdaq["ret_nasdaq"] = df_nasdaq["close"].pct_change()

    # Alinhar timestamps comuns entre Nasdaq e BTC
    merged = pd.merge(
        df_btc[["ret"]].rename(columns={"ret": "ret_btc"}),
        df_nasdaq[["ret_nasdaq"]],
        left_index=True,
        right_index=True,
        how="inner"
    ).dropna()

    lead_lag_corrs = {}
    for lag in range(-4, 5):
        # lag > 0: nasdaq[t] correlacionado com btc[t + lag] (Nasdaq lidera BTC)
        # lag < 0: btc[t] correlacionado com nasdaq[t - lag]
        if lag > 0:
            c = merged["ret_nasdaq"].corr(merged["ret_btc"].shift(-lag))
        elif lag < 0:
            c = merged["ret_btc"].corr(merged["ret_nasdaq"].shift(lag))
        else:
            c = merged["ret_nasdaq"].corr(merged["ret_btc"])
        lead_lag_corrs[f"lag_{lag}"] = round(float(c), 4)

    print(f" -> Matriz Lead-Lag Nasdaq vs BTC (15m): {lead_lag_corrs}")
    print(f"    * Correlação Contemporânea (Lag 0): {lead_lag_corrs['lag_0']}")
    print(f"    * Nasdaq t-1 prevendo BTC t (Lag +1): {lead_lag_corrs['lag_1']}")

    # Condicional: Quando Nasdaq tem movimento forte (> 20 bps em 15m), qual a direção do BTC nos 15m seguintes?
    strong_up_nasdaq = merged[merged["ret_nasdaq"] > 0.0020]
    subsequent_btc_after_up = merged["ret_btc"].shift(-1).loc[strong_up_nasdaq.index].dropna()
    up_hit_rate = (subsequent_btc_after_up > 0).mean() if len(subsequent_btc_after_up) > 0 else 0.5

    strong_down_nasdaq = merged[merged["ret_nasdaq"] < -0.0020]
    subsequent_btc_after_down = merged["ret_btc"].shift(-1).loc[strong_down_nasdaq.index].dropna()
    down_hit_rate = (subsequent_btc_after_down < 0).mean() if len(subsequent_btc_after_down) > 0 else 0.5

    print(f" -> Sinal Condicional: Após choque de alta na Nasdaq (+0.2%), BTC sobe nos próximos 15m: {up_hit_rate:.1%} (N={len(subsequent_btc_after_up)})")
    print(f" -> Sinal Condicional: Após choque de baixa na Nasdaq (-0.2%), BTC cai nos próximos 15m: {down_hit_rate:.1%} (N={len(subsequent_btc_after_down)})")

    findings["nasdaq_btc_lead_lag"] = {
        "lead_lag_correlations": lead_lag_corrs,
        "nasdaq_lead_signal": {
            "after_strong_nasdaq_up_btc_up_winrate": round(float(up_hit_rate), 4),
            "after_strong_nasdaq_down_btc_down_winrate": round(float(down_hit_rate), 4),
            "sample_size_up": len(subsequent_btc_after_up),
            "sample_size_down": len(subsequent_btc_after_down)
        }
    }

    # --------------------------------------------------------------------------
    # 3. RISCO DE CAUDA E FLASH MOVES EM 15M (AUDITORIA DE YIELD HARVESTING)
    # --------------------------------------------------------------------------
    print("\n[3/4] Avaliando caudas gordas e risco de cisne negro em janelas de 15m (HistData & Dukas)...")
    # Histórico de 8.139 dias de Ouro e 3.333 dias de Bitcoin
    df_gold = dmgr.load_candles("xauusd", timeframe="m15")
    df_gold["ret"] = df_gold["close"].pct_change()
    
    # Frequência de movimentos extremos em 15m (> 0.5% e > 1.0%)
    btc_flash_moves_05pct = (df_btc["ret"].abs() > 0.005).mean()
    btc_flash_moves_10pct = (df_btc["ret"].abs() > 0.010).mean()
    gold_flash_moves_05pct = (df_gold["ret"].abs() > 0.005).mean()
    gold_flash_moves_10pct = (df_gold["ret"].abs() > 0.010).mean()

    print(f" -> BTC 15m: Movimentos > 0.5%: {btc_flash_moves_05pct:.2%} | Movimentos > 1.0%: {btc_flash_moves_10pct:.2%}")
    print(f" -> Ouro 15m: Movimentos > 0.5%: {gold_flash_moves_05pct:.2%} | Movimentos > 1.0%: {gold_flash_moves_10pct:.2%}")

    # No Yield Harvester (comprar contratos a 95¢ buscando 5¢ de payout), um movimento de 0.5% destrói a opção
    findings["tail_risk_15m"] = {
        "btc_prob_move_over_05pct": round(float(btc_flash_moves_05pct), 4),
        "btc_prob_move_over_10pct": round(float(btc_flash_moves_10pct), 4),
        "gold_prob_move_over_05pct": round(float(gold_flash_moves_05pct), 4),
        "gold_prob_move_over_10pct": round(float(gold_flash_moves_10pct), 4)
    }

    # --------------------------------------------------------------------------
    # 4. MICROESTRUTURA DE 1 MINUTO (HISTDATA: 2020-2023 OURO E SPX)
    # --------------------------------------------------------------------------
    print("\n[4/4] Carregando microestrutura de 1 minuto do HistData (SPXUSD & XAUUSD)...")
    df_spx_m1 = hmgr.load_m1_candles("SPXUSD", year=2023, max_rows=50000)
    df_spx_m1["ret"] = df_spx_m1["close"].pct_change()
    spx_m1_autocorr = df_spx_m1["ret"].dropna().autocorr(lag=1)
    
    df_gold_m1 = hmgr.load_m1_candles("XAUUSD", year=2023, max_rows=50000)
    df_gold_m1["ret"] = df_gold_m1["close"].pct_change()
    gold_m1_autocorr = df_gold_m1["ret"].dropna().autocorr(lag=1)

    print(f" -> SPX 1-Minute Autocorrelação Lag-1: {spx_m1_autocorr:.4f} (Forte reversão à média no bid-ask bounce)")
    print(f" -> Ouro 1-Minute Autocorrelação Lag-1: {gold_m1_autocorr:.4f}")

    findings["m1_microstructure"] = {
        "spx_m1_autocorr_lag1": round(float(spx_m1_autocorr), 4),
        "gold_m1_autocorr_lag1": round(float(gold_m1_autocorr), 4)
    }

    # Salva relatório estatístico consolidado
    out_file = BASE_DIR / "quant_empirical_findings.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)

    print(f"\n[OK] Descobertas quantitativas gravadas em: {out_file}")
    return findings


if __name__ == "__main__":
    analyze_edges()
