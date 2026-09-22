import json
import os
from py_clob_client_v2 import ClobClient, SignatureTypeV2, BalanceAllowanceParams, AssetType
import urllib.request

cfg = {}
with open(".env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()

funder = cfg.get("POLY_FUNDER_ADDRESS")
key = cfg.get("POLYGON_PRIVATE_KEY")

print("=" * 65)
print("COMPROVACAO INDISCUTIVEL DE SALDO REAL EM BLOCKCHAIN")
print("=" * 65)
print(f"1. Endereco Funder Safe na Polygon: {funder}")

# Consulta 1: API Oficial Polymarket CLOB V2 (BalanceAllowance)
client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137, signature_type=SignatureTypeV2.POLY_1271, funder=funder)
client.set_api_creds(client.derive_api_key())
bal_info = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
clob_balance = float(bal_info.get("balance", 0.0)) / 1e6

print(f"2. Saldo de Garantia (Collateral USDC) na CLOB: ${clob_balance:.6f} USDC")
print(f"   Allowance de Negociacao: ${float(bal_info.get('allowance', 0.0))/1e6:.2f} USDC")

# Consulta 2: On-chain direto no contrato USDC.e / Native USDC na Polygon
rpcs = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.llamarpc.com",
    "https://1rpc.io/matic"
]

addr_padded = funder.lower().replace("0x", "").zfill(64)
call_data = "0x70a08231" + addr_padded

# Contratos de colateral usados pela Polymarket
contracts = [
    ("USDC.e (Bridged Polymarket Collateral)", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),
    ("Native USDC (Circle Polygon)", "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")
]

for name, token_addr in contracts:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": token_addr, "data": call_data}, "latest"]
    }).encode("utf-8")

    for rpc in rpcs:
        try:
            req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                r = json.loads(resp.read().decode())
                if "result" in r and r["result"]:
                    val = int(r["result"], 16) / 1e6
                    print(f"3. On-chain {name}: ${val:.6f}")
                    break
        except Exception:
            continue

print("=" * 65)
print(f"Link publico para conferencia no Polygonscan:")
print(f"https://polygonscan.com/address/{funder}")
print(f"https://polygonscan.com/token/0x2791bca1f2de4661ed88a30c99a7a9449aa84174?a={funder}")
print("=" * 65)
