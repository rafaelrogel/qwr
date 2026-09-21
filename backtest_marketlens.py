"""
=============================================================================
BACKTEST ENGINE COM MARKETLENS - POLYMARKET BTC 5M
=============================================================================
Simula estratégias quantitativas e ordens no livro de ofertas (Order Book L2)
em dados históricos reais da Polymarket com modelagem de slippage e latência.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Carregar variáveis de ambiente do .env
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("MARKETLENS_API_KEY", "").strip()

if not api_key:
    print("\n" + "=" * 75)
    print(" [AVISO] Chave de API do Marketlens não detectada!")
    print("=" * 75)
    print(" Para rodar backtests históricos reais, faça o seguinte:")
    print(" 1. Acesse: https://marketlens.trade/")
    print(" 2. Crie uma conta gratuita (Free Tier - sem cartão)")
    print(" 3. Copie sua API Key no console")
    print(" 4. Cole no arquivo .env:")
    print("    MARKETLENS_API_KEY=sua_chave_aqui")
    print("=" * 75 + "\n")
    sys.exit(0)

try:
    from marketlens import MarketLens, Strategy
except ImportError:
    print("Erro: marketlens não está instalado. Execute: pip install marketlens")
    sys.exit(1)


class LateCandleSweeperStrategy(Strategy):
    """
    Estratégia de Backtest: Late-Candle Sweeper (Inspirada no Takerner e BTC5MScour)
    Analisa o desbalanço e o preço nos últimos minutos da vela.
    """
    def __init__(self, target_imbalance: float = -0.20, min_stake: float = 1.0):
        super().__init__()
        self.target_imbalance = target_imbalance
        self.min_stake = min_stake
        self._entered = False

    def on_market_start(self, ctx, market, book):
        self._entered = False

    def on_trade(self, ctx, market, book, trade):
        # Exemplo de regra com base na microestrutura de fluxo
        if not self._entered and book.imbalance(5) < self.target_imbalance:
            # Comprar lado DOWN (NO) quando o fluxo vendedor pesa
            ctx.buy_no(size=self.min_stake)
            self._entered = True


def main():
    print("\n" + "=" * 75)
    print(" INICIANDO SESSÃO DE BACKTEST QUANTITATIVO (MARKETLENS)")
    print("=" * 75)
    print(f" Conectando com a API Key: {api_key[:6]}...{api_key[-4:]}")

    client = MarketLens(api_key=api_key)

    try:
        # Testando conexão listando mercados recentes de BTC 5m
        print(" Consultando catálogo de séries disponíveis...")
        series_iter = client.series.list(limit=5)
        series_list = list(series_iter)
        print(f" Conexão estabelecida com sucesso! Séries detectadas: {len(series_list)}")
        for s in series_list[:5]:
            print(f"  - {s.id}: {s.title}")

        print("\nPronto para executar backtests detalhados em 'btc-up-or-down-5m'.")

    except Exception as e:
        print(f" Erro ao consultar API do Marketlens: {e}")


if __name__ == "__main__":
    main()
