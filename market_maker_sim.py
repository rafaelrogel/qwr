"""
Simulador de Estratégia de Market Making para o Polymarket
Demonstra como um bot calcula cotações ideais (Bid/Ask) para capturar o spread
e se qualificar para as recompensas diárias de liquidez do Polymarket (CLOB Rewards).
"""
import json
import sys
from clob_client import PolymarketClient
import config

def simulate_market_making():
    client = PolymarketClient(config.GAMMA_API_URL, config.CLOB_API_URL)
    print("==================================================================")
    print("      SIMULADOR DE ESTRATÉGIA DE MARKET MAKING NO POLYMARKET      ")
    print("==================================================================")
    
    # 1. Encontrar o mercado mais líquido elegível a recompensas
    print("Buscando mercados ativos com programa de Recompensas de Liquidez...")
    markets = client.get_top_markets(limit=10, min_volume=20000)
    
    target_market = None
    for m in markets:
        if m.get("clobRewards") or m.get("holdingRewardsEnabled"):
            target_market = m
            break
            
    if not target_market:
        target_market = markets[0]

    question = target_market.get("question")
    max_spread = float(target_market.get("rewardsMaxSpread", 3.0) or 3.0)
    min_size = float(target_market.get("rewardsMinSize", 100) or 100)
    token_ids = json.loads(target_market.get("clobTokenIds", "[]"))
    
    if not token_ids:
        print("Nenhum token encontrado para este mercado.")
        return

    yes_token_id = token_ids[0]
    
    print(f"\n[Mercado Selecionado]: {question}")
    print(f"Token YES ID: {yes_token_id[:25]}...")
    print(f"Requisitos de Recompensa: Spread Máximo = {max_spread:.1f}% | Tamanho Mínimo = {min_size:.0f} cotas")
    
    # 2. Consultar o Livro de Ofertas Real (CLOB)
    book = client.get_order_book(yes_token_id)
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    
    if not bids or not asks:
        print("Livro de ofertas sem liquidez suficiente no momento.")
        return

    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])
    mid_price = (best_bid + best_ask) / 2.0
    current_spread = best_ask - best_bid
    current_spread_pct = (current_spread / mid_price) * 100

    print("\n--- Estado Atual do Livro de Ofertas ---")
    print(f"Melhor Comprador (Best Bid): ${best_bid:.4f} ({bids[0]['size']} cotas)")
    print(f"Melhor Vendedor  (Best Ask): ${best_ask:.4f} ({asks[0]['size']} cotas)")
    print(f"Preço Médio (Mid-Price):     ${mid_price:.4f}")
    print(f"Spread de Mercado Atual:     ${current_spread:.4f} ({current_spread_pct:.2f}%)")

    # 3. Cálculo das Ordens do Robô Market Maker
    # O bot posiciona uma ordem de compra 1 tick acima do best bid e uma venda 1 tick abaixo do best ask
    tick_size = float(target_market.get("orderPriceMinTickSize", 0.001) or 0.001)
    
    # Margem de segurança para garantir a qualificação de recompensas
    bot_bid = round(mid_price - (mid_price * (max_spread / 200.0)), 3)
    bot_ask = round(mid_price + (mid_price * (max_spread / 200.0)), 3)
    bot_spread = bot_ask - bot_bid
    bot_spread_pct = (bot_spread / mid_price) * 100

    print("\n--- Simulação de Posicionamento do Robô ---")
    print(f"Ordem de COMPRA planejada (Bid): ${bot_bid:.3f} (Qtd: {min_size:.0f} cotas)")
    print(f"Ordem de VENDA  planejada (Ask): ${bot_ask:.3f} (Qtd: {min_size:.0f} cotas)")
    print(f"Spread do seu Robô:             ${bot_spread:.3f} ({bot_spread_pct:.2f}%)")
    
    # Avaliação de Elegibilidade
    elegivel = bot_spread_pct <= max_spread
    status_recompensa = "APROVADO (Qualificado para pagar recompensas diárias)" if elegivel else "REPROVADO (Spread acima do teto)"
    print(f"Status no Programa de Recompensas: {status_recompensa}")

    # Retorno Esperado por Ciclo Completo (Round-trip)
    capital_investido = bot_bid * min_size
    lucro_bruto_ciclo = (bot_ask - bot_bid) * min_size
    retorno_pct = (lucro_bruto_ciclo / capital_investido) * 100

    print(f"\n[Métricas Financeiras da Simulação]:")
    print(f"Capital alocado por ordem:      ${capital_investido:.2f} USDC")
    print(f"Lucro por ciclo de preenchimento: ${lucro_bruto_ciclo:.2f} USDC ({retorno_pct:.2f}%)")
    print(f"Ganhos extras: Recompensas diárias do pool de USDC do Polymarket adicionadas diretamente na sua carteira.")
    print("==================================================================")

if __name__ == "__main__":
    simulate_market_making()
