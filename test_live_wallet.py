"""
Script de Validação e Teste de Conexão com a Carteira Real do Polymarket
Verifica:
1. Leitura das variáveis do arquivo .env
2. Assinatura e autenticação com a CLOB API (sem gastar nada)
3. Consulta do saldo real de USDC e permissões de trading
"""
import os
import sys
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

env_path = os.path.join(os.path.dirname(__file__), ".env")

def load_env():
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def test_connection():
    print("=" * 65)
    print("TESTE DE CONEXÃO COM A CARTEIRA REAL DO POLYMARKET")
    print("=" * 65)
    
    cfg = load_env()
    pk = cfg.get("POLYGON_PRIVATE_KEY") or cfg.get("PRIVATE_KEY")
    funder = cfg.get("POLY_FUNDER_ADDRESS") or cfg.get("FUNDER_ADDRESS") or cfg.get("POLY_ADDRESS")
    
    if not pk or pk in ["sua_chave_privada_aqui", "sua_chave_privada_revelada_aqui"]:
        print("\n[!] Chave Privada não configurada no arquivo .env ainda.")
        print(f"    Abra o arquivo: {env_path}")
        print("    E preencha: POLYGON_PRIVATE_KEY=sua_chave")
        return False
        
    # Remove '0x' se houver duplicado ou formata
    pk_clean = pk.strip()
    if pk_clean.startswith("0x"):
        pk_clean = pk_clean[2:]
        
    print("\n1. Chave privada detectada no .env!")
    print(f"2. Endereço Funder configurado: {funder or 'Usando o próprio endereço da chave (EOA)'}")
    
    host = "https://clob.polymarket.com"
    chain_id = 137  # Polygon Mainnet
    
    # Testa primeiro com signature_type=1 (Magic/Gnosis Safe proxy) ou 2 (Proxy) ou 0 (EOA)
    # Para contas Google / Magic, signature_type costuma ser 1 ou 2
    signature_types_to_try = [1, 2, 0] if funder else [0]
    
    connected_client = None
    successful_sig_type = 0
    
    for sig_type in signature_types_to_try:
        try:
            print(f"\nTentando autenticação com assinatura tipo {sig_type}...")
            client = ClobClient(
                host=host,
                key=pk_clean,
                chain_id=chain_id,
                signature_type=sig_type,
                funder=funder if sig_type != 0 else None
            )
            # Deriva ou cria credenciais da API CLOB
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
            print("   -> Autenticação L1/L2 com a CLOB bem-sucedida!")
            connected_client = client
            successful_sig_type = sig_type
            break
        except Exception as e:
            print(f"   Aviso tipo {sig_type}: {e}")
            
    if not connected_client:
        print("\n[Erro] Não foi possível autenticar com a CLOB. Verifique a chave privada.")
        return False
        
    print("\n3. Consultando saldo de USDC e limites na conta...")
    try:
        # Consulta balanço de USDC e allowance de negociação
        balance_info = connected_client.get_balance_allowance()
        print(f"   Retorno do Saldo: {balance_info}")
    except Exception as e:
        print(f"   Aviso ao consultar saldo: {e}")
        
    print("\n" + "=" * 65)
    print("CONEXÃO VALIDADA COM SUCESSO! O ROBÔ ESTÁ PRONTO.")
    print(f"Tipo de assinatura ideal para sua conta: signature_type={successful_sig_type}")
    print("=" * 65)
    return True

if __name__ == "__main__":
    test_connection()
