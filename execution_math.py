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
    print("=" * 70)
