# -*- coding: utf-8 -*-
"""
=============================================================================
ANTIGRAVITY QUANT SYSTEM — EXECUTION MATH & MICROSTRUCTURE ENGINE
=============================================================================
Implementação matemática das metodologias extraídas de bots institucionais
de alta frequência (+100 bots, $50K+/mês em Polymarket) validadas pela IA JEV:
1. VWAP Book Depth: Preço médio ponderado por volume na profundidade L2.
2. Executable Net Edge: Margem líquida real após taxas, slippage e safety buffer.
3. Fractional Kelly Sizing: Dimensionamento ótimo a 25% de Kelly com salvaguardas.
4. Bayesian Fair Value: Atualização contínua com atenuação de colinearidade.
5. Cross-Market Z-Score: Detecção de divergência e lead-lag entre horizontes.
=============================================================================
"""

import math
from typing import List, Tuple, Optional, Dict, Any


def calculate_vwap_ask(
    asks: List[Tuple[float, float]],
    target_usd: float
) -> Tuple[Optional[float], float, float, float]:
    """
    Calcula o Preço Médio Ponderado por Volume (VWAP) para preencher `target_usd` no CLOB.
    
    Args:
        asks: Lista de tuplas (preço, tamanho_em_cotas).
        target_usd: Valor financeiro total que a ordem pretende comprar em USD.
        
    Returns:
        (vwap_price, total_cost, total_shares, slippage_bps)
        Se o livro não possuir profundidade suficiente para `target_usd`, vwap_price será None.
    """
    if not asks or target_usd <= 0:
        return None, 0.0, 0.0, 0.0

    # Ordena asks de forma crescente pelo preço (melhores ofertas primeiro)
    sorted_asks = sorted(asks, key=lambda x: x[0])
    best_ask = sorted_asks[0][0]

    total_cost = 0.0
    total_shares = 0.0

    for price, size in sorted_asks:
        if price <= 0 or size <= 0:
            continue
        level_cost = price * size
        remaining_usd = target_usd - total_cost

        if level_cost >= remaining_usd:
            needed_shares = remaining_usd / price
            total_shares += needed_shares
            total_cost += remaining_usd
            break
        else:
            total_shares += size
            total_cost += level_cost

    if total_cost < (target_usd - 1e-4):
        # Livro raso: liquidez insuficiente para absorver o tamanho desejado
        slippage_bps = ((best_ask - best_ask) / best_ask) * 10000.0 if best_ask > 0 else 0.0
        return None, total_cost, total_shares, slippage_bps

    vwap = total_cost / total_shares if total_shares > 0 else None
    slippage_bps = 0.0
    if vwap and best_ask > 0:
        slippage_bps = max(0.0, ((vwap - best_ask) / best_ask) * 10000.0)

    return (round(vwap, 4) if vwap else None, round(total_cost, 2), round(total_shares, 2), round(slippage_bps, 1))


def calculate_vwap_bid(
    bids: List[Tuple[float, float]],
    target_shares: float
) -> Tuple[Optional[float], float, float, float]:
    """
    Calcula o VWAP de saída para vender `target_shares` contra os bids do CLOB.
    
    Args:
        bids: Lista de tuplas (preço, tamanho_em_cotas).
        target_shares: Quantidade de cotas a liquidar.
        
    Returns:
        (vwap_price, total_proceeds, filled_shares, slippage_bps)
    """
    if not bids or target_shares <= 0:
        return None, 0.0, 0.0, 0.0

    # Ordena bids de forma decrescente pelo preço (maiores pagadores primeiro)
    sorted_bids = sorted(bids, key=lambda x: -x[0])
    best_bid = sorted_bids[0][0]

    total_proceeds = 0.0
    filled_shares = 0.0

    for price, size in sorted_bids:
        if price <= 0 or size <= 0:
            continue
        remaining_shares = target_shares - filled_shares

        if size >= remaining_shares:
            total_proceeds += remaining_shares * price
            filled_shares += remaining_shares
            break
        else:
            total_proceeds += size * price
            filled_shares += size

    if filled_shares < (target_shares - 1e-4):
        return None, total_proceeds, filled_shares, 0.0

    vwap = total_proceeds / filled_shares if filled_shares > 0 else None
    slippage_bps = 0.0
    if vwap and best_bid > 0:
        slippage_bps = max(0.0, ((best_bid - vwap) / best_bid) * 10000.0)

    return (round(vwap, 4) if vwap else None, round(total_proceeds, 2), round(filled_shares, 2), round(slippage_bps, 1))


def calculate_executable_edge(
    fair_value: float,
    expected_fill_price: float,
    trading_fee: float = 0.0,
    expected_slippage: float = 0.005,
    safety_buffer: float = 0.010
) -> Tuple[float, float, bool]:
    """
    Calcula a margem executável líquida (Net Edge).
    
    Net Edge = Gross Edge - Comissões - Derrapagem Esperada - Margem de Segurança
    
    Returns:
        (gross_edge, net_edge, is_executable)
    """
    gross_edge = fair_value - expected_fill_price
    net_edge = gross_edge - trading_fee - expected_slippage - safety_buffer
    is_executable = net_edge > 0.0
    return round(gross_edge, 4), round(net_edge, 4), is_executable


def compute_fractional_kelly_stake(
    win_probability: float,
    entry_price: float,
    bankroll: float,
    kelly_fraction: float = 0.25,
    min_stake: float = 5.0,
    max_stake: float = 30.0
) -> Tuple[float, float, str]:
    """
    Dimensionamento de posição por Kelly Fracionário (padrão 25% / Quarter-Kelly).
    
    Protege o bankroll contra ruído de parâmetros e variância em horizontes de 5m.
    
    Returns:
        (stake_usd, full_kelly_fraction, status_str)
    """
    if not (0.01 <= entry_price <= 0.99):
        return 0.0, 0.0, "INVALID_ENTRY_PRICE"
    if not (0.0 < win_probability < 1.0):
        return 0.0, 0.0, "INVALID_WIN_PROBABILITY"
    if bankroll <= 0:
        return 0.0, 0.0, "ZERO_OR_NEGATIVE_BANKROLL"

    loss_probability = 1.0 - win_probability
    net_odds = (1.0 - entry_price) / entry_price

    if net_odds <= 0:
        return 0.0, 0.0, "ZERO_ODDS"

    full_kelly = (net_odds * win_probability - loss_probability) / net_odds

    if full_kelly <= 0.0:
        return 0.0, round(full_kelly, 4), "NEGATIVE_OR_ZERO_EDGE"

    raw_fraction = full_kelly * kelly_fraction
    raw_stake = bankroll * raw_fraction

    bounded_stake = max(min_stake, min(raw_stake, max_stake))
    status = "OPTIMAL"
    if raw_stake > max_stake:
        status = "CAPPED_AT_MAX"
    elif raw_stake < min_stake:
        status = "RAISED_TO_MIN"

    return round(bounded_stake, 2), round(full_kelly, 4), status


def compute_kalshi_dynamic_contracts(
    bankroll: float,
    win_probability: float,
    entry_price_cents: int,
    available_qty: int = 1,
    delta_ratio: float = 1.0,
    min_contracts: int = 1,
    max_contracts_cap: int = 5
) -> Tuple[int, str]:
    """
    Dimensionamento de posição por Kelly Fracionário (25%) para contratos Kalshi,
    incorporando restrições de liquidez L2 e proteção de banca real (Guardrails):
    1. Saldo < $20: Máximo de 2 contratos (exposição máxima ~$1.00 - $1.20)
    2. Saldo $20 - $40: Máximo de 3 contratos (exposição máxima ~$1.50 - $1.80)
    3. Saldo >= $40: Destrava até 5 contratos (exposição ~$2.50 - $3.00)
    4. Guardrail de Super-Edge: Para escalar além de 1 contrato, exige confluência
       (delta_ratio >= 1.35x deadband e win_probability >= 0.68)
    5. Guardrail de Liquidez L2: Nunca requisita mais contratos do que a quantidade
       disponível no topo do livro naquele centavo exato.
    """
    entry_price = max(0.01, min(0.99, entry_price_cents / 100.0))
    if win_probability <= entry_price or win_probability < 0.52:
        return min_contracts, "BASELINE_MIN_CONTRACT"

    # 1. Teto de contratos modulado pelo saldo real (Bankroll Guardrail)
    if bankroll < 20.0:
        bankroll_max = 2
    elif bankroll < 40.0:
        bankroll_max = 3
    else:
        bankroll_max = min(max_contracts_cap, 5)

    # 2. Requisito de Super-Edge para sair do contrato base (Auditado JEV Round 7)
    # Para bancas pequenas (< $25, como a atual de ~$11), exige super-confluência extrema
    # (Delta Ratio >= 1.80x e Win Prob >= 78%) para blindar a banca contra risco de ruína.
    req_delta_ratio = 1.80 if bankroll < 25.0 else 1.35
    req_win_prob = 0.78 if bankroll < 25.0 else 0.68
    if delta_ratio < req_delta_ratio or win_probability < req_win_prob:
        return min_contracts, "CONSERVATIVE_EDGE_SINGLE_CONTRACT"

    # 3. Cálculo de Kelly Fracionário (25%)
    net_odds = (1.0 - entry_price) / entry_price
    loss_prob = 1.0 - win_probability
    full_kelly = (net_odds * win_probability - loss_prob) / net_odds

    if full_kelly <= 0.0:
        return min_contracts, "NEGATIVE_KELLY_BASE"

    raw_fraction = full_kelly * 0.25
    target_usd = bankroll * raw_fraction
    ideal_contracts = int(target_usd / entry_price)

    # Bounded pelo teto de saldo
    bounded = max(min_contracts, min(ideal_contracts, bankroll_max))

    # 4. Checagem de Liquidez L2 no Topo do Livro
    if available_qty > 0 and bounded > available_qty:
        final_contracts = max(min_contracts, min(bounded, available_qty))
        status = f"KELLY_CAPPED_BY_L2_DEPTH_{final_contracts}"
    else:
        final_contracts = bounded
        status = f"KELLY_OPTIMAL_{final_contracts}"

    return final_contracts, status


def bayesian_fair_value(
    prior_prob: float,
    p_signal_if_outcome: float,
    p_signal_if_alternative: float,
    collinearity_discount: float = 0.75
) -> float:
    """
    Atualização Bayesiana de probabilidade de vitória com desconto de colinearidade.
    
    O desconto atenua a probabilidade do sinal em direção a 0.50 para evitar
    superestimação resultante de sinais co-dependentes (ex: momentum + taker flow + OBI).
    """
    prior = max(0.01, min(0.99, prior_prob))

    # Atenua sinal com o fator de colinearidade
    p_sig_out = 0.5 + (max(0.01, min(0.99, p_signal_if_outcome)) - 0.5) * collinearity_discount
    p_sig_alt = 0.5 + (max(0.01, min(0.99, p_signal_if_alternative)) - 0.5) * collinearity_discount

    weighted_outcome = prior * p_sig_out
    weighted_alt = (1.0 - prior) * p_sig_alt
    denom = weighted_outcome + weighted_alt

    if denom <= 1e-9:
        return prior

    posterior = weighted_outcome / denom
    return round(max(0.01, min(0.99, posterior)), 4)


def cross_market_zscore(
    current_spread: float,
    average_spread: float,
    spread_std: float
) -> float:
    """
    Calcula o Z-Score de dispersão entre mercados relacionados (ex: 5m vs 15m).
    """
    if spread_std <= 1e-6:
        return 0.0
    return round((current_spread - average_spread) / spread_std, 2)


def get_diurnal_regime(current_utc_hour: Optional[int] = None) -> Dict[str, Any]:
    """
    Retorna o regime de microestrutura diurna com base nas evidências empíricas
    extraídas dos dados Dukascopy/HistData e auditadas pela IA Jev (97% prob):
    - TRENDING / MOMENTUM: Horas UTC [6, 8, 10, 13] (Aberturas de Londres e NY) -> deadband_multiplier = 1.0
    - MEAN_REVERTING / NOISE: Horas UTC [0, 4, 5, 11, 16, 17, 19, 21, 22, 23] -> deadband_multiplier = 1.35
    - NEUTRAL / TRANSITION: Demais horas -> deadband_multiplier = 1.15
    """
    if current_utc_hour is None:
        from datetime import datetime, timezone
        current_utc_hour = datetime.now(timezone.utc).hour

    trending_hours = {6, 8, 10, 13}
    mean_reverting_hours = {0, 4, 5, 11, 16, 17, 19, 21, 22, 23}

    if current_utc_hour in trending_hours:
        return {
            "regime": "TRENDING_MOMENTUM",
            "hour_utc": current_utc_hour,
            "deadband_multiplier": 1.0,
            "kelly_scale": 1.10,
            "description": "Abertura institucional (Londres/NY): persistência de fluxo direcional confirmada."
        }
    elif current_utc_hour in mean_reverting_hours:
        return {
            "regime": "MEAN_REVERTING_CHOP",
            "hour_utc": current_utc_hour,
            "deadband_multiplier": 1.35,
            "kelly_scale": 0.85,
            "description": "Sessão noturna/fechamento: ruído mecânico de bid-ask bounce; deadband elevado em 35% para evitar falso breakout."
        }
    else:
        return {
            "regime": "NEUTRAL_TRANSITION",
            "hour_utc": current_utc_hour,
            "deadband_multiplier": 1.15,
            "kelly_scale": 1.00,
            "description": "Horário de transição: deadband com folga conservadora de 15%."
        }


def check_fat_tail_hazard(
    entry_price: float,
    strike_distance_pct: float,
    hours_remaining: float,
    min_sigma_distance: float = 0.0075
) -> Tuple[bool, str]:
    """
    Avalia o risco de ruína por caudas gordas (Fat Tails) em contratos de Yield Harvesting
    (Desk 6) ou compras a preços elevados (> $0.92):
    
    Evidência empírica Dukascopy/HistData: 4.45% das velas de 15m movem > 0.50% do spot.
    Para contratos com preço >= $0.92 e vencimento em menos de 24h, exige distância
    mínima de strike de 3 sigmas (>= 0.75% do spot).
    """
    if entry_price < 0.92:
        return True, "PREÇO_SEGURO: Cota abaixo de 92¢, risco de cauda absorvido pelo payoff assimétrico."

    if hours_remaining <= 24.0 and strike_distance_pct < min_sigma_distance:
        return False, (
            f"VETO_FAT_TAIL_HAZARD: Preço ${entry_price:.3f} (exige 92%+ WR) com distância de strike "
            f"de apenas {strike_distance_pct:.2%} (< {min_sigma_distance:.2%} / 3 sigmas) a {hours_remaining:.1f}h do vencimento. "
            f"Negative EV por curtose excessiva comprovada nos dados históricos."
        )

def calculate_ornstein_uhlenbeck_halflife(
    series: List[float],
    dt: float = 1.0
) -> Tuple[Optional[float], float, float]:
    """
    Calcula a velocidade de reversão à média (theta) e a Meia-Vida (Half-Life)
    do processo de Ornstein-Uhlenbeck, conforme formulado por Ernie Chan (2021, Cap. 7):
    
        dz_t = theta * (mu - z_{t-1}) * dt + epsilon_t
        Delta z_t = lambda * (z_{t-1} - mu) + error
        Half-Life = -ln(2) / lambda
        
    Args:
        series: Sequência temporal de valores (ex: delta em relação ao strike, spread).
        dt: Intervalo de tempo entre observações em segundos ou minutos.
        
    Returns:
        (halflife, theta, equilibrium_mean)
        Se a série for explosiva/trending (theta >= 0) ou dados insuficientes, halflife é None.
    """
    if not series or len(series) < 5:
        return None, 0.0, 0.0

    n = len(series)
    prev_z = series[:-1]
    dz = [series[i] - series[i - 1] for i in range(1, n)]

    mu = sum(prev_z) / len(prev_z)
    x_dev = [val - mu for val in prev_z]

    # Regressão linear OLS: dz = lambda * x_dev
    sum_xx = sum(x * x for x in x_dev)
    if sum_xx < 1e-12:
        return None, 0.0, mu

    sum_xy = sum(x * y for x, y in zip(x_dev, dz))
    lam = sum_xy / sum_xx  # Coeficiente angular

    if lam >= 0:
        # Série não é mean-reverting (é estocasticamente trending ou divergente)
        return None, lam, mu

    theta = -lam / dt
    halflife = (math.log(2.0) / theta) if theta > 0 else None
    return (round(halflife, 2) if halflife is not None else None), round(theta, 6), round(mu, 4)


# =============================================================================
# 6. SARDINE EMPIRICAL BASE-RATE & VOLATILITY Z-SCORE ENGINE (SARDINE.INFO)
# =============================================================================
_SARDINE_TABLE_CACHE: Optional[List[Dict[str, Any]]] = None

def load_sardine_table() -> List[Dict[str, Any]]:
    """Carrega a tabela empírica calibrada do sardine_table_kxbtc15m.json com cache."""
    global _SARDINE_TABLE_CACHE
    if _SARDINE_TABLE_CACHE is not None:
        return _SARDINE_TABLE_CACHE
    import os, json
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    tbl_path = os.path.join(curr_dir, "sardine_table_kxbtc15m.json")
    if os.path.exists(tbl_path):
        try:
            with open(tbl_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _SARDINE_TABLE_CACHE = data.get("cells", [])
                return _SARDINE_TABLE_CACHE
        except Exception:
            pass
    _SARDINE_TABLE_CACHE = []
    return _SARDINE_TABLE_CACHE


def calculate_sardine_zscore(
    spot: float,
    strike: float,
    realized_vol_60m: float,
    seconds_remaining: float
) -> float:
    """
    Calcula a distância padronizada em unidades de volatilidade (Z-Score Sardine):
    z = ln(spot / strike) / (sigma_60m * sqrt(seconds_remaining / (365.25 * 86400)))
    
    Se sigma_60m ou seconds_remaining <= 0, retorna 0.0.
    """
    if spot <= 0 or strike <= 0 or realized_vol_60m <= 0 or seconds_remaining <= 0:
        return 0.0
    t_years = seconds_remaining / (365.25 * 86400.0)
    vol_scale = realized_vol_60m * math.sqrt(t_years)
    if vol_scale < 1e-8:
        return 0.0
    return math.log(spot / strike) / vol_scale


def lookup_sardine_empirical_probability(
    z_score: float,
    seconds_remaining: float
) -> Tuple[Optional[float], int, Tuple[float, float]]:
    """
    Consulta a probabilidade empírica baseada no histórico de 10.497 janelas da Kalshi (Sardine):
    Retorna (p_empirical, n_observations, (wilson_lo, wilson_hi)).
    Se não encontrar célula exata, interpola pelo checkpoint temporal mais próximo.
    """
    cells = load_sardine_table()
    if not cells:
        return None, 0, (0.0, 1.0)

    # Checkpoints suportados no table: 120s, 300s, 480s, 720s, 900s
    valid_ttx = [120, 300, 480, 720, 900]
    closest_ttx = min(valid_ttx, key=lambda x: abs(x - seconds_remaining))

    # Procura a célula correspondente
    for c in cells:
        if c.get("ttx_s") == closest_ttx:
            z_lo = c.get("z_lo", -999.0)
            z_hi = c.get("z_hi", 999.0)
            if z_lo <= z_score < z_hi:
                return float(c.get("p", 0.5)), int(c.get("n", 0)), (float(c.get("lo", 0.0)), float(c.get("hi", 1.0)))

    # Fallback se z estiver além das bordas (z > 3.5 ou z < -3.0)
    if z_score >= 3.0:
        return 0.99, 1000, (0.98, 1.0)
    elif z_score <= -3.0:
        return 0.01, 1000, (0.0, 0.02)

def check_round_number_barrier(
    spot: float,
    target_side: str,
    interval: float = 500.0,
    buffer_usd: float = 20.0
) -> Tuple[bool, str]:
    """
    Round Number Barrier Shield (Anti-Ricochete .00 Double Zero - Raghee Horner / JEV):
    - Se aposta em DOWN / NO e o spot estiver a menos de `buffer_usd` acima de um suporte de número redondo (ex: $83,012 a $12 de $83,000),
      veta a entrada pois o preço tende a ricochetear no suporte institucional.
    - Se aposta em UP / YES e o spot estiver a menos de `buffer_usd` abaixo de uma resistência de número redondo (ex: $82,988 a $12 de $83,000),
      veta a entrada pois o preço tende a ser rejeitado no teto institucional.
    """
    if spot <= 0 or interval <= 0:
        return False, "OK"

    side = target_side.upper()
    remainder = spot % interval

    if side in ("DOWN", "NO"):
        if remainder < buffer_usd:
            support_level = spot - remainder
            return True, f"Barrado por Round Number Shield: Spot ${spot:,.2f} está a ${remainder:.2f} do suporte de ${support_level:,.0f} (< ${buffer_usd:.0f}). Risco de ricochete."
    elif side in ("UP", "YES"):
        dist_to_res = interval - remainder
        if dist_to_res < buffer_usd:
            resistance_level = spot + dist_to_res
            return True, f"Barrado por Round Number Shield: Spot ${spot:,.2f} está a ${dist_to_res:.2f} da resistência de ${resistance_level:,.0f} (< ${buffer_usd:.0f}). Risco de rejeição."

    return False, "OK"


def detect_dow_regime_15m(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """
    Dow Regime Detector com Dynamic Stake Scaling (Charles Dow & Raghee Horner / JEV AI):
    Avalia a inclinação (Slope) da 34 EMA nos dados recentes de 15m para identificar:
    - UPTREND (Onda 12:00 às 2:00, Slope > +8 bps): Convicção compradora. 2 contratos com Scale-Out. Deadband 1.0x.
    - DOWNTREND (Onda 4:00 às 6:00, Slope < -8 bps): Convicção vendedora. 2 contratos com Scale-Out. Deadband 1.0x.
    - DISTRIBUTION_CHOPPY (Onda plana 3:00, |Slope| <= 8 bps): Mercado lateral sem momentum organizado.
      Em vez de Hard Veto, aplica Dynamic Stake Scaling: Reduz para 1 contrato defensivo e exige Deadband 1.5x.
    """
    import urllib.request
    import json

    default_res = {
        "regime": "TRENDING",
        "slope_bps": 12.0,
        "is_choppy": False,
        "deadband_multiplier": 1.0,
        "recommended_contracts": 2,
        "description": "Fallback padrão de tendência ativa."
    }

    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=24"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            klines = json.loads(r.read().decode())
            if len(klines) < 16:
                return default_res

            closes = [float(k[4]) for k in klines]
            
            # Cálculo de 34 EMA recursivo simples
            alpha34 = 2.0 / (34 + 1)
            ema34_series = []
            cur_ema = closes[0]
            for c in closes:
                cur_ema = (c * alpha34) + (cur_ema * (1.0 - alpha34))
                ema34_series.append(cur_ema)

            # Slope sobre as últimas 8 velas (2 horas):
            prev_ema = ema34_series[-9] if len(ema34_series) >= 9 else ema34_series[0]
            latest_ema = ema34_series[-1]
            slope_bps = ((latest_ema - prev_ema) / max(1.0, prev_ema)) * 10000.0

            if abs(slope_bps) <= 8.0:
                return {
                    "regime": "DISTRIBUTION_CHOPPY",
                    "slope_bps": round(slope_bps, 2),
                    "is_choppy": True,
                    "deadband_multiplier": 1.5,
                    "recommended_contracts": 1,
                    "description": f"Mercado em Distribuição/Acumulação Lateral (3:00 Flat Wave | Slope: {slope_bps:+.1f} bps). Dynamic Scaling: 1 contrato e Deadband 1.5x."
                }
            elif slope_bps > 8.0:
                return {
                    "regime": "UPTREND",
                    "slope_bps": round(slope_bps, 2),
                    "is_choppy": False,
                    "deadband_multiplier": 1.0,
                    "recommended_contracts": 2,
                    "description": f"Tendência de Alta Confirmada (Onda 12:00 às 2:00 | Slope: {slope_bps:+.1f} bps). 2 contratos ativos com Scale-Out."
                }
            else:
                return {
                    "regime": "DOWNTREND",
                    "slope_bps": round(slope_bps, 2),
                    "is_choppy": False,
                    "deadband_multiplier": 1.0,
                    "recommended_contracts": 2,
                    "description": f"Tendência de Baixa Confirmada (Onda 4:00 às 6:00 | Slope: {slope_bps:+.1f} bps). 2 contratos ativos com Scale-Out."
                }
    except Exception as e:
        return default_res


def calculate_black_scholes_digital_fv(
    spot: float,
    strike: float,
    elapsed_sec: int,
    total_sec: int = 900,
    sigma: float = 0.0030
) -> float:
    """
    Calcula a probabilidade neutra ao risco N(d2) de uma Opção Binária Digital Cash-or-Nothing.
    Retorna a probabilidade teórica de fechar acima do strike em formato decimal (0.01 a 0.99).
    
    Args:
        spot: Preço atual do ativo (Chainlink ou Binance).
        strike: Strike do contrato (preço de abertura da vela).
        elapsed_sec: Segundos decorridos na janela (ex: 450s para 15m, 135s para 5m).
        total_sec: Duração total da janela (900s para 15m, 300s para 5m).
        sigma: Volatilidade realizada esperada para a janela (~30 bps para 15m, ~15 bps para 5m).
    """
    if spot <= 0 or strike <= 0:
        return 0.50
    try:
        remaining_sec = max(1, total_sec - elapsed_sec)
        tau_ratio = remaining_sec / float(total_sec)
        vol_sqrt_t = sigma * math.sqrt(tau_ratio)
        if vol_sqrt_t <= 1e-8:
            return 0.99 if spot >= strike else 0.01
        
        d2 = (math.log(spot / strike) - 0.5 * (sigma ** 2) * tau_ratio) / vol_sqrt_t
        prob = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
        return round(max(0.01, min(0.99, prob)), 4)
    except Exception:
        return 0.50


def calculate_expected_max_sharpe(
    n_trials: int,
    mean_sharpe: float = 0.0,
    var_sharpe: float = 1.0
) -> float:
    """
    Calcula o Sharpe Ratio Máximo Esperado sob a hipótese nula de passeio aleatório (Random Walk)
    após N testes independentes (Marcos López de Prado, 2014/2018).
    
    Formula:
        E[max_N] = ( (1 - gamma) * Z^{-1}(1 - 1/N) + gamma * Z^{-1}(1 - 1/(N*e)) ) * sqrt(var_sharpe)
    """
    if n_trials <= 1:
        return mean_sharpe

    euler_gamma = 0.5772156649015328606  # Constante de Euler-Mascheroni
    
    def approx_inv_cdf(p: float) -> float:
        # Aproximação de Winitzki / Hastings para a inversa da Normal
        p = max(1e-12, min(1.0 - 1e-12, p))
        t = math.sqrt(-2.0 * math.log(1.0 - p if p > 0.5 else p))
        # Coeficientes Hastings
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        z = t - (c0 + c1 * t + c2 * (t ** 2)) / (1.0 + d1 * t + d2 * (t ** 2) + d3 * (t ** 3))
        return z if p > 0.5 else -z

    z1 = approx_inv_cdf(1.0 - 1.0 / n_trials)
    z2 = approx_inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    exp_max = ((1.0 - euler_gamma) * z1 + euler_gamma * z2) * math.sqrt(var_sharpe)
    return round(mean_sharpe + exp_max, 4)


def calculate_deflated_sharpe_ratio(
    estimated_sharpe: float,
    n_trials: int,
    sample_length: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    var_sharpe: float = 1.0
) -> Dict[str, Any]:
    """
    Calcula o Deflated Sharpe Ratio (DSR) de Marcos López de Prado.
    Penaliza o Sharpe Ratio estimado pelo viés de seleção decorrente de múltiplos testes (n_trials),
    não-gaussianidade (assimetria e curtose) e tamanho amostral.
    
    Returns:
        dict contendo:
            - 'dsr': Probabilidade de que a estratégia seja estatisticamente genuína (0.0 a 1.0).
            - 'expected_max_sharpe': Sharpe limiar gerado por puro acaso com n_trials.
            - 'is_statistically_significant': True se DSR >= 0.95 (confiança de 95%).
            - 'haircut_pct': Penalidade aplicada ao Sharpe.
    """
    if sample_length <= 2:
        return {
            "dsr": 0.0,
            "expected_max_sharpe": 0.0,
            "is_statistically_significant": False,
            "haircut_pct": 100.0,
            "verdict": "Amostra insuficiente (T <= 2)"
        }

    sr_0 = calculate_expected_max_sharpe(n_trials, mean_sharpe=0.0, var_sharpe=var_sharpe)

    # Variância do estimador Sharpe sob não-gaussianidade (Mertens, 2002)
    # V[SR] = (1 - skew * SR + ((kurt - 1) / 4) * SR^2) / (T - 1)
    denom_var = 1.0 - skewness * estimated_sharpe + ((kurtosis - 1.0) / 4.0) * (estimated_sharpe ** 2)
    if denom_var <= 0:
        denom_var = 1.0
    se_sr = math.sqrt(denom_var / (sample_length - 1))

    z = (estimated_sharpe - sr_0) / se_sr if se_sr > 0 else 0.0

    # CDF Normal
    dsr = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    dsr = max(0.0001, min(0.9999, dsr))

    significant = dsr >= 0.95
    haircut = max(0.0, min(100.0, (1.0 - (estimated_sharpe - sr_0) / max(1e-4, estimated_sharpe)) * 100)) if estimated_sharpe > 0 else 100.0

    return {
        "dsr": round(dsr, 4),
        "estimated_sharpe": round(estimated_sharpe, 4),
        "expected_max_sharpe": round(sr_0, 4),
        "is_statistically_significant": significant,
        "haircut_pct": round(haircut, 1),
        "verdict": "GENUÍNO (p < 0.05 após múltiplos testes)" if significant else "REJEITADO (provável overfitting / selection bias)"
    }


def calculate_sadf_score(
    prices: List[float],
    lags: int = 1,
    min_window: int = 12
) -> Dict[str, Any]:
    """
    Supremum Augmented Dickey-Fuller (SADF) Test para Detecção de Quebras Estruturais e Bolhas/Momentum
    (Phillips, Wu & Yu, 2011; Marcos López de Prado, Advances in Financial ML, Cap. 17).
    
    Testa se a série de preços recente exibe comportamento explosivo (beta > 0)
    ou reversão à média (beta < 0) em janela expansiva:
        Delta y_t = alpha + beta * y_{t-1} + sum_{l=1}^p gamma_l * Delta y_{t-l} + epsilon_t
        
    Returns:
        dict com:
            - 'sadf_stat': Supremum do t-stat na janela expansiva (float)
            - 'latest_t': Último t-stat estimado (float)
            - 'is_explosive': bool (True se sadf_stat > 1.35)
            - 'is_mean_reverting': bool (True se latest_t < -1.80)
            - 'veto_mean_reversion': bool (True se explosivo -> não apostar contra a tendência)
            - 'regime': 'EXPLOSIVE_MOMENTUM' | 'STATIONARY_MEAN_REVERTING' | 'RANDOM_WALK_CHOP'
    """
    import numpy as np

    if not prices or len(prices) < min_window + lags + 2:
        return {
            "sadf_stat": 0.0,
            "latest_t": 0.0,
            "is_explosive": False,
            "is_mean_reverting": False,
            "veto_mean_reversion": False,
            "regime": "INSUFFICIENT_DATA"
        }

    series = np.array(prices, dtype=float)
    T = len(series)

    def adf_t(sub_series: np.ndarray) -> float:
        sub_t = len(sub_series)
        if sub_t <= lags + 3:
            return 0.0
        dy = np.diff(sub_series)
        dy_dep = dy[lags:]
        y_lag = sub_series[lags : sub_t - 1]
        x_cols = [np.ones(len(dy_dep)), y_lag]
        for lag in range(1, lags + 1):
            x_cols.append(dy[lags - lag : sub_t - 1 - lag])
        x = np.column_stack(x_cols)
        try:
            beta, _, _, _ = np.linalg.lstsq(x, dy_dep, rcond=None)
            residuals = dy_dep - x @ beta
            dof = len(dy_dep) - x.shape[1]
            if dof <= 0:
                return 0.0
            sigma2 = np.sum(residuals ** 2) / dof
            cov = sigma2 * np.linalg.pinv(x.T @ x)
            se_beta = math.sqrt(max(1e-12, cov[1, 1]))
            return float(beta[1] / se_beta)
        except Exception:
            return 0.0

    t_stats = [adf_t(series[:end]) for end in range(min_window, T + 1)]
    sadf_stat = max(t_stats) if t_stats else 0.0
    latest_t = t_stats[-1] if t_stats else 0.0

    is_explosive = bool(sadf_stat > 1.35 and latest_t > 0.8)
    is_mean_reverting = bool(latest_t < -1.80)

    if is_explosive:
        regime = "EXPLOSIVE_MOMENTUM"
    elif is_mean_reverting:
        regime = "STATIONARY_MEAN_REVERTING"
    else:
        regime = "RANDOM_WALK_CHOP"

    return {
        "sadf_stat": round(sadf_stat, 3),
        "latest_t": round(latest_t, 3),
        "is_explosive": is_explosive,
        "is_mean_reverting": is_mean_reverting,
        "veto_mean_reversion": is_explosive,
        "regime": regime
    }


def safe_eval_gate(gate_name: str, gate_func, default_verdict: Any, *args, **kwargs) -> Any:
    """
    Wrapper fail-safe universal para filtros quantitativos e gates secundários.
    Garante que qualquer erro de escopo, exceção de rede ou KeyError não interrompa
    o fluxo de execução de um trade válido.
    """
    try:
        return gate_func(*args, **kwargs)
    except Exception as e:
        print(f"   [🛡️ FAIL-SAFE GATE - {gate_name}]: Exceção capturada com sucesso ({e}). Aplicando fallback neutro: {default_verdict}")
        return default_verdict



if __name__ == "__main__":
    print("=" * 70)
    print("  TESTE DO MÓDULO EXECUTION_MATH (INSTITUTIONAL GRADE)")
    print("=" * 70)

    # 1. Teste VWAP Ask
    test_asks = [(0.45, 10.0), (0.47, 25.0), (0.50, 40.0), (0.55, 100.0)]
    vwap, cost, shares, slip_bps = calculate_vwap_ask(test_asks, target_usd=25.0)
    print(f"VWAP Ask para $25: Preço={vwap}, Custo=${cost}, Cotas={shares}, Slippage={slip_bps} bps")

    # 2. Teste Executable Net Edge
    gross, net, ok = calculate_executable_edge(fair_value=0.55, expected_fill_price=vwap or 0.48)
    print(f"Edge: Bruto={gross:.2%}, Líquido={net:.2%}, Executável={ok}")

    # 3. Teste Kelly Fracionário
    stake, fk, st = compute_fractional_kelly_stake(win_probability=0.62, entry_price=0.48, bankroll=500.0)
    print(f"Kelly Stake: ${stake:.2f} (Full Kelly: {fk:.2%}, Status: {st})")

    # 4. Teste Bayesiano com Colinearidade
    post = bayesian_fair_value(0.50, p_signal_if_outcome=0.72, p_signal_if_alternative=0.38)
    print(f"Bayesian Posterior: {post:.2%}")

    # 5. Teste Black-Scholes Digital FV
    bs_up = calculate_black_scholes_digital_fv(spot=83500.0, strike=83450.0, elapsed_sec=450, total_sec=900)
    print(f"Black-Scholes Digital FV (Spot +$50 sobre Strike aos 450s): {bs_up:.1%}")
    print("=" * 70)
