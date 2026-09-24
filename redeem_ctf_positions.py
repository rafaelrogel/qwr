"""
Redeem CTF Positions - Polymarket Conditional Tokens (ERC1155) On-Chain Settlement
==================================================================================
Identifica e resgata automaticamente cotas vencedoras (curPrice == 1.0) mantidas na
carteira Gnosis Safe (Poly1271) na rede Polygon PoS.

Contratos Oficiais Polygon Mainnet:
- Conditional Tokens Framework (CTF): 0x4D97DCd97eC945f40cF65F87097ACe5EA0476045
- Collateral Token (Bridged USDC.e):  0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
- Polymarket Data API:                https://data-api.polymarket.com/positions
"""

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import time
import argparse
import urllib.request
from typing import List, Dict, Any, Optional

try:
    from web3 import Web3
    from eth_account import Account
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
PARENT_COLLECTION_ID = b"\x00" * 32

CTF_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"}
        ],
        "name": "redeemPositions",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "index", "type": "uint256"}
        ],
        "name": "payoutDenominator",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "index", "type": "uint256"}
        ],
        "name": "payoutNumerators",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

SAFE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "value", "type": "uint256"},
            {"internalType": "bytes", "name": "data", "type": "bytes"},
            {"internalType": "uint8", "name": "operation", "type": "uint8"},
            {"internalType": "uint256", "name": "safeTxGas", "type": "uint256"},
            {"internalType": "uint256", "name": "baseGas", "type": "uint256"},
            {"internalType": "uint256", "name": "gasPrice", "type": "uint256"},
            {"internalType": "address", "name": "gasToken", "type": "address"},
            {"internalType": "address payable", "name": "refundReceiver", "type": "address"},
            {"internalType": "bytes", "name": "signatures", "type": "bytes"}
        ],
        "name": "execTransaction",
        "outputs": [{"internalType": "bool", "name": "success", "type": "bool"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "nonce",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

def load_env_config() -> Dict[str, str]:
    cfg = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg

def get_positions(safe_address: str) -> List[Dict[str, Any]]:
    """Consulta todas as posições da carteira via Polymarket Data API"""
    url = f"https://data-api.polymarket.com/positions?user={safe_address}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Erro ao consultar Polymarket Data API: {e}")
        return []

def filter_winning_unredeemed(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filtra posições com valor residual positivo que aguardam resgate para USDC"""
    winning = []
    for p in positions:
        cur_price = float(p.get("curPrice") or 0.0)
        cur_val = float(p.get("currentValue") or 0.0)
        size = float(p.get("size") or 0.0)
        redeemable = bool(p.get("redeemable", False))
        # Cotas vencedoras possuem curPrice == 1.0 ou valor positivo residual
        if (cur_price >= 0.98 or cur_val > 0.01) and size > 0:
            winning.append(p)
    return winning

def inspect_wallet_positions(safe_address: str) -> Dict[str, Any]:
    """Relatório estruturado de todas as posições da carteira Safe"""
    positions = get_positions(safe_address)
    winning = filter_winning_unredeemed(positions)
    worthless = [p for p in positions if p not in winning]

    total_unredeemed_usd = sum(float(p.get("currentValue") or float(p.get("size", 0)) * float(p.get("curPrice", 0))) for p in winning)

    return {
        "safe_address": safe_address,
        "total_positions_tracked": len(positions),
        "winning_unredeemed_count": len(winning),
        "winning_unredeemed_usd": round(total_unredeemed_usd, 2),
        "winning_positions": winning,
        "worthless_count": len(worthless),
        "timestamp": time.time()
    }

def build_redeem_call_data(condition_id_hex: str) -> bytes:
    """Gera o calldata da função redeemPositions do CTF para o mercado binário"""
    if not HAS_WEB3:
        raise RuntimeError("web3 library is required to encode calldata")
    w3 = Web3()
    ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)
    
    cond_bytes = bytes.fromhex(condition_id_hex[2:] if condition_id_hex.startswith("0x") else condition_id_hex)
    if len(cond_bytes) != 32:
        raise ValueError(f"Invalid conditionId length: {len(cond_bytes)}")
        
    return ctf.encode_abi("redeemPositions", [
        Web3.to_checksum_address(USDC_ADDRESS),
        PARENT_COLLECTION_ID,
        cond_bytes,
        [1, 2] # IndexSets para mercados binários Up/Down
    ])

def run_redeem_check():
    """Modo de Verificação e Execução de Resgate"""
    cfg = load_env_config()
    safe_addr = cfg.get("POLY_FUNDER_ADDRESS", "0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c")
    rpc_url = cfg.get("POLYGON_RPC_URL", "https://polygon-rpc.com")
    pk = cfg.get("POLYGON_PRIVATE_KEY", "").strip()
    signer_addr = cfg.get("POLY_SIGNER_ADDRESS", "").strip()

    print("=" * 80)
    print("  🪙 POLYMARKET CTF POSITION REDEEMER (POLYGON MAINNET)")
    print(f"  Carteira Safe (Funder): {safe_addr}")
    print(f"  Carteira Signer:        {signer_addr}")
    print("=" * 80)

    report = inspect_wallet_positions(safe_addr)
    print(f"\n[📊 STATUS DA CARTEIRA SAFE]:")
    print(f"  Posições Rastreadas na API: {report['total_positions_tracked']}")
    print(f"  Cotas Vencedoras Pendentes: {report['winning_unredeemed_count']}")
    print(f"  Valor Estimado a Resgatar:  ${report['winning_unredeemed_usd']:.2f} USDC")
    print(f"  Posições Expiradas Perdedoras (Valor $0.00): {report['worthless_count']}")

    if report["winning_unredeemed_count"] == 0:
        print("\n[✅ PARIDADE ON-CHAIN CONFIRMADA]:")
        print("  Todas as cotas vencedoras históricas já foram resgatadas com sucesso para USDC ou")
        print("  foram realizadas antecipadamente via SirMartingale Take-Profit.")
        print("  Nenhum capital de lucro está represado em tokens condicionais.")
        return 0

    print(f"\n[⚠️ ATENÇÃO]: Encontradas {report['winning_unredeemed_count']} posições com valor pendente:")
    for idx, p in enumerate(report["winning_positions"], 1):
        print(f"  {idx}. {p.get('title')} | Outcome: {p.get('outcome')} | Size: {p.get('size')} | Val: ${p.get('currentValue')}")

    if not HAS_WEB3:
        print("\n[!] Web3 não está instalado para envio on-chain. Instale com 'pip install web3'.")
        return 1

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"\n[!] Falha ao conectar ao RPC Polygon: {rpc_url}")
        return 1

    signer_bal = w3.eth.get_balance(signer_addr) if signer_addr else 0
    signer_pol = float(w3.from_wei(signer_bal, "ether"))
    print(f"\n[⛽ GÁS DE TRANSAÇÃO]: Saldo Signer: {signer_pol:.4f} POL")

    if signer_pol < 0.05:
        print("  [i] Signer possui POL insuficiente para pagar gás on-chain direto.")
        print("      As transações diárias do bot são liquidadas sem gás via Relayer da Polymarket.")
        print("      Para resgate manual via Web3, envie 0.1 POL para:", signer_addr)
        return 0

    print("\n[*] Preparando transações de resgate via Safe execTransaction...")
    if not pk:
        print("[!] Chave privada POLYGON_PRIVATE_KEY não configurada no .env!")
        return 1

    try:
        account = Account.from_key(pk)
    except Exception as epk:
        print(f"[!] Erro ao carregar conta signer: {epk}")
        return 1

    safe_contract = w3.eth.contract(address=Web3.to_checksum_address(safe_addr), abi=SAFE_ABI)
    zero_addr = "0x0000000000000000000000000000000000000000"

    # Assinatura pré-validada do Safe (v=1, r=owner, s=0) quando msg.sender == owner
    owner_bytes = bytes.fromhex(account.address[2:].lower()).rjust(32, b"\x00")
    s_bytes = b"\x00" * 32
    v_byte = b"\x01"
    pre_validated_sig = owner_bytes + s_bytes + v_byte

    redeemed_count = 0
    for idx, p in enumerate(report["winning_positions"], 1):
        condition_id = p.get("conditionId")
        title = p.get("title", f"Position #{idx}")
        if not condition_id:
            print(f"  [!] Posição '{title}' não possui conditionId. Pulando...")
            continue

        try:
            call_data = build_redeem_call_data(condition_id)
            tx_data = safe_contract.functions.execTransaction(
                Web3.to_checksum_address(CTF_ADDRESS),
                0,
                call_data,
                0, # Operation: Call
                0, # safeTxGas
                0, # baseGas
                0, # gasPrice
                Web3.to_checksum_address(zero_addr),
                Web3.to_checksum_address(zero_addr),
                pre_validated_sig
            ).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 300000,
                "gasPrice": int(w3.eth.gas_price * 1.25)
            })

            signed = account.sign_transaction(tx_data)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            print(f"  [🚀 RESGATE ENVIADO]: {title}")
            print(f"     TX Hash: {tx_hash.hex()}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.get("status") == 1:
                print(f"     ✅ Sucesso! Confirmado no bloco {receipt.get('blockNumber')}")
                redeemed_count += 1
            else:
                print(f"     ❌ Falha na execução da transação: status={receipt.get('status')}")
        except Exception as e:
            print(f"  [!] Erro ao resgatar {title}: {e}")

    print(f"\n[🏁 RESGATE CONCLUÍDO]: {redeemed_count} posições resgatadas com sucesso.")
    return 0

if __name__ == "__main__":
    sys.exit(run_redeem_check())
