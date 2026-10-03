# -*- coding: utf-8 -*-
"""
Teste dos Modelos Matemáticos Extraídos do Artigo @robrtcode:
1. VWAP Executable Net Edge (L2 Book Depth)
2. Fractional Kelly Sizing (Quarter-Kelly com Bounds)
3. Bayesian Fair Value Updating com Poda de Colinearidade
"""

def calculate_vwap_ask(asks, target_usd):
    """
    Calcula o preço médio ponderado (VWAP) para comprar `target_usd` no CLOB.
    asks: lista de tuplas (preco, tamanho_em_cotas)
    """
    sorted_asks = sorted(asks, key=lambda x: x[0])
    total_cost = 0.0
    total_shares = 0.0
    for price, size in sorted_asks:
        cost_level = price * size
        if total_cost + cost_level >= target_usd:
            needed_cost = target_usd - total_cost
            needed_shares = needed_cost / price
            total_shares += needed_shares
            total_cost += needed_cost
            break
        else:
            total_cost += cost_level
            total_shares += size
            
    if total_cost < target_usd:
        return None, total_cost, total_shares  # Livro sem profundidade suficiente
    vwap = total_cost / total_shares
    return vwap, total_cost, total_shares

def calculate_executable_edge(fair_value, vwap_price, trading_fee=0.0, expected_slippage=0.005, safety_buffer=0.010):
    """Calcula o edge líquido real após custos de execução e buffer de segurança."""
    gross_edge = fair_value - vwap_price
    net_edge = gross_edge - trading_fee - expected_slippage - safety_buffer
    return gross_edge, net_edge

def fractional_kelly_stake(win_probability, entry_price, bankroll, kelly_fraction=0.25, min_stake=5.0, max_stake=30.0):
    """
    Calcula o stake em USD usando Kelly Fracionário (25%), respeitando limites de risco.
    """
    if not (0.01 < entry_price < 0.99):
        return 0.0
    loss_prob = 1.0 - win_probability
    net_odds = (1.0 - entry_price) / entry_price
    full_kelly = (net_odds * win_probability - loss_prob) / net_odds
    if full_kelly <= 0:
        return 0.0
    raw_stake = bankroll * (full_kelly * kelly_fraction)
    return round(max(min_stake, min(raw_stake, max_stake)), 2)

def bayesian_fair_value(prior_up, p_signal_given_up, p_signal_given_down, collinearity_discount=0.75):
    """
    Atualização Bayesiana do Fair Value com desconto de colinearidade.
    O desconto atenua a probabilidade do sinal para evitar hiper-reação a choques idênticos.
    """
    p_sig_up_adj = 0.5 + (p_signal_given_up - 0.5) * collinearity_discount
    p_sig_down_adj = 0.5 + (p_signal_given_down - 0.5) * collinearity_discount
    
    weighted_up = prior_up * p_sig_up_adj
    weighted_down = (1.0 - prior_up) * p_sig_down_adj
    if (weighted_up + weighted_down) <= 0:
        return prior_up
    return weighted_up / (weighted_up + weighted_down)

if __name__ == "__main__":
    print("=== TESTE DE ENGENHARIA QUANTITATIVA (@ROBRTCODE) ===")
    
    # 1. VWAP Book Test
    sample_asks = [(0.48, 20.0), (0.49, 30.0), (0.52, 50.0)]
    target_usd = 25.0
    vwap, cost, shares = calculate_vwap_ask(sample_asks, target_usd)
    print(f"Target: USD {target_usd:.2f}")
    print(f"Top-of-book ask: 0.4800 | VWAP Real: {vwap:.4f} | Cotas Adquiridas: {shares:.2f} | Custo: USD {cost:.2f}")
    
    fair_value = 0.55
    gross, net = calculate_executable_edge(fair_value, vwap)
    print(f"Fair Value: {fair_value:.2f} | Gross Edge: {gross:.2%} | Net Edge: {net:.2%}")
    
    # 2. Kelly Sizing Test
    bankroll = 500.0
    stake = fractional_kelly_stake(win_probability=0.62, entry_price=vwap, bankroll=bankroll)
    print(f"Bankroll: USD {bankroll:.2f} | Kelly Stake (25%): USD {stake:.2f}")
    
    # 3. Bayesian Fair Value Test
    prior = 0.50
    post = bayesian_fair_value(prior, p_signal_given_up=0.70, p_signal_given_down=0.35, collinearity_discount=0.80)
    print(f"Prior: {prior:.2%} -> Posterior (com desconto colinearidade): {post:.2%}")
