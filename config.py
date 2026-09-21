"""
Configurações do Polymarket Trading Bot
"""
import os

# Endpoints Oficiais do Polymarket
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
POLYGON_RPC_URL = "https://polygon-rpc.com"

# Configurações de Varredura e Arbitragem
MIN_24H_VOLUME_USD = 10_000.0   # Filtra mercados com pelo menos $10k de volume diário
ARBITRAGE_THRESHOLD_PCT = 1.0   # Alerta de arbitragem quando soma != 1.00 por mais de 1%
TOP_MARKETS_LIMIT = 20          # Número de mercados analisados por ciclo

# Modo de Execução: 'paper' (Simulação) ou 'live' (Real)
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "paper")

# Credenciais de Carteira Web3 (Opcional, apenas se for operar em modo real)
POLYGON_PRIVATE_KEY = os.getenv("POLYGON_PRIVATE_KEY", "")
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_API_SECRET = os.getenv("POLYMARKET_API_SECRET", "")
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", "")
