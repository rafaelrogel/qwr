# 🚀 Plano de Expansão Multi-Ativos: Polymarket ETH 5m & SOL 5m

Este documento consolida a arquitetura técnica, os datasets descobertos e os parâmetros quantitativos para a expansão futura do robô de alta precisão para os mercados de **Ethereum (ETH 5m)** e **Solana (SOL 5m)** no Polymarket.

---

## 1. Datasets Homologados e Descobertas-Chave

### A. Dataset Primário: `aliplayer1/polymarket-crypto-updown` (Hugging Face)
* **Status**: Ativo, mantido e atualizado a cada 3 horas.
* **Licença**: MIT.
* **Ativos cobertos**: BTC, ETH, SOL, BNB, XRP, DOGE, HYPE.
* **Timeframes**: 5-minutos, 15-minutos, 1-hora, 4-horas.
* **Subsets disponíveis**:
  1. `markets`: Metadados, IDs de condição, strikes de abertura e resoluções.
  2. `prices`: Histórico de cotações dos tokens UP/DOWN.
  3. `ticks`: Execuções on-chain granulares.
  4. `spot_prices`: Preços spot de referência (Binance/CEX).
  5. `orderbook`: Livro de ofertas (Bids/Asks) do CLOB V2.

#### Como consultar sob demanda via DuckDB (Zero Download Local):
```python
import duckdb

# Consulta direta remota via Parquet no Hugging Face:
conn = duckdb.connect()
df_eth = conn.sql("""
    SELECT timestamp, market_slug, outcome, price 
    FROM 'hf://datasets/aliplayer1/polymarket-crypto-updown/data/prices/**/*.parquet' 
    WHERE crypto = 'ETH' AND timeframe = '5-minute' 
    LIMIT 1000
""").df()
print(df_eth.head())
```

### B. Repositório de WebSocket Bruto: `PMData.dev`
* Preservação contínua de streams de WebSocket de mercados Up/Down da Polymarket com carimbo de tempo, cotações de Bids/Asks e telemetria bruta.

---

## 2. Mapa dos Oráculos Chainlink na Rede Polygon (PoS)

Para operar ETH e SOL com a mesma precisão do BTC, o robô consome diretamente os contratos da `AggregatorV3Interface`:

| Ativo | Par | Endereço do Contrato (Polygon) | Decimais | Heartbeat Médio | Deviation Threshold |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bitcoin** | `BTC / USD` | `0xc907E116054Ad103354f2D350FD2514433D57F6f` | 8 | 27s | 0.25% |
| **Ethereum** | `ETH / USD` | `0xF9680D99D6C9589e2a93a78A04A279e509205945` | 8 | 27s | 0.25% |
| **Solana** | `SOL / USD` | `0x10d38B880B37870F0d9526727271424E6d31F1D8` | 8 | 27s | 0.50% |

---

## 3. Calibração Paramétrica Comparativa (Deadband e Gatilhos)

A volatilidade absoluta varia significativamente entre os ativos. Os filtros devem ser calibrados proporcionalmente ao preço nominal do ativo:

| Métrica / Parâmetro | BTC 5m (Atual) | ETH 5m (Projetado) | SOL 5m (Projetado) |
| :--- | :--- | :--- | :--- |
| **Preço de Referência** | ~$80.000 | ~$3.000 | ~$150 - $200 |
| **Filtro de Ruído (Deadband)** | **$15.00** (~0.018%) | **$1.20** (~0.040%) | **$0.20** (~0.100%) |
| **Gatilho Sweeper aos 265s** | **$25.00** (~0.031%) | **$2.50** (~0.083%) | **$0.40** (~0.200%) |
| **Teto de Preço Primário (135s)** | $\le \$0.65$ | $\le \$0.65$ | $\le \$0.65$ |
| **Janela Segura Sweeper (265s)** | $\$0.88 - \$0.965$ | $\$0.88 - \$0.965$ | $\$0.88 - \$0.965$ |
| **Par Binance Spot Liderança** | `BTCUSDT` | `ETHUSDT` | `SOLUSDT` |

---

## 4. Técnica SentAI: Busca Binária para Recuperação de Strike (`roundId`)

Caso o robô reinicie no meio do ciclo e precise saber o preço exato do strike na abertura da vela sem depender de APIs externas:

```python
# Fórmula de Decomposição Bitwise Chainlink (EVM):
def parse_chainlink_round_id(round_id: int):
    phase_id = round_id >> 64
    aggregator_round_id = round_id & 0xFFFFFFFFFFFFFFFF
    return phase_id, aggregator_round_id

def make_chainlink_round_id(phase_id: int, agg_round_id: int) -> int:
    return (phase_id << 64) | agg_round_id

# Busca binária sobre aggregator_round_id para localizar o roundId
# correspondente ao timestamp exato de abertura da vela com <= 5 chamadas RPC.
```

---

## 5. Arquitetura Multithread / Concorrente Recomendada

Para rodar os 3 pares em paralelo de forma eficiente:
1. **Feed WebSocket Único da Binance**:
   Subscrever simultaneamente aos streams agregados:
   `wss://stream.binance.com:9443/ws/btcusdt@ticker/ethusdt@ticker/solusdt@ticker`
2. **Workers Assíncronos Isolados**:
   Cada par tem seu próprio ciclo de 5 minutos, garantindo que uma ordem de ETH ou SOL não bloqueie a execução de BTC.
3. **Gestão de Margem Compartilhada**:
   Alocação de risco dividida (ex: 40% BTC, 30% ETH, 30% SOL).
