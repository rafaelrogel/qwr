"""
Scanner em Tempo Real de Mercados e Oportunidades de Arbitragem no Polymarket
"""
import json
import time
from clob_client import PolymarketClient
import config

def format_usd(val: float) -> str:
    return f"${val:,.2f}"

def run_scanner():
    client = PolymarketClient(config.GAMMA_API_URL, config.CLOB_API_URL)
    print("==================================================================")
    print("      POLYMARKET ALGO TRADER - SCANNER DE MERCADO EM TEMPO REAL   ")
    print("==================================================================")
    print(f"Conectando aos servidores do Polymarket...")
    print(f"Filtro: Volume mínimo 24h = {format_usd(config.MIN_24H_VOLUME_USD)}")
    print("------------------------------------------------------------------\n")

    markets = client.get_top_markets(limit=config.TOP_MARKETS_LIMIT, min_volume=config.MIN_24H_VOLUME_USD)
    print(f"-> {len(markets)} mercados altamente líquidos encontrados.\n")

    arbitrage_count = 0

    for idx, m in enumerate(markets, 1):
        question = m.get("question", "N/A")
        vol24h = float(m.get("volume24hr") or 0)
        liquidity = float(m.get("liquidityNum") or 0)
        
        try:
            outcomes = json.loads(m.get("outcomes", "[]"))
            prices_str = json.loads(m.get("outcomePrices", "[]"))
            prices = [float(p) for p in prices_str]
        except Exception:
            continue

        if len(outcomes) < 2 or len(prices) < 2:
            continue

        price_sum = sum(prices)
        diff_pct = (price_sum - 1.0) * 100

        print(f"[{idx}] {question}")
        print(f"    Volume 24h: {format_usd(vol24h)} | Liquidez: {format_usd(liquidity)}")
        
        outcomes_info = []
        for o, p in zip(outcomes, prices):
            outcomes_info.append(f"{o}: ${p:.3f} ({p*100:.1f}%)")
        print(f"    Cotacoes:   {' | '.join(outcomes_info)}")
        print(f"    Soma Total: {price_sum:.4f} ({diff_pct:+.2f}%)")

        # Detector de Oportunidade de Arbitragem de Paridade
        # Em mercados binários, se YES + NO < 0.99 (ex: $0.97), comprar ambos garante lucro de $0.03 no vencimento.
        if abs(diff_pct) >= config.ARBITRAGE_THRESHOLD_PCT:
            arbitrage_count += 1
            if price_sum < 1.0:
                profit = (1.0 - price_sum) * 100
                print(f"    >>> [OPORTUNIDADE DE ARBITRAGEM (DESCONTO)]: Lucro potencial garantido de {profit:.2f}% ao comprar todos os lados!")
            else:
                spread_excess = (price_sum - 1.0) * 100
                print(f"    >>> [SOBREPREÇO DE MERCADO]: O mercado está sobrecomprado em {spread_excess:.2f}%. Oportunidade para venda/minting.")
        
        # Checar se o mercado oferece recompensas diárias aos criadores de mercado (Market Making)
        if m.get("holdingRewardsEnabled") or m.get("clobRewards"):
            max_spread = m.get("rewardsMaxSpread", 0)
            print(f"    * Elegivel a Recompensas de Liquidez diárias (Spread Max: {max_spread}%)")
            
        print("")

    print("==================================================================")
    print(f"Varredura concluída. Oportunidades de desvio de paridade detectadas: {arbitrage_count}")
    print("==================================================================")

if __name__ == "__main__":
    run_scanner()
