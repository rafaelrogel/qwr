import urllib.request
import json
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
from dotenv import load_dotenv

load_dotenv()
pk = os.getenv('POLYGON_PRIVATE_KEY')
funder = os.getenv('SAFE_ADDRESS')

with open('live_trading_journal.json') as f:
    d = json.load(f)
c89 = [t for t in d['trades'] if t['cycle'] == 89][0]
print('C89 window_ts:', c89['window_ts'], 'time:', c89['time_str'])
slug = f"btc-updown-5m-{c89['window_ts']}"
url = f'https://gamma-api.polymarket.com/events?slug={slug}'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
        m = data[0]['markets'][0]
        print('Market Question:', m.get('question'))
        print('Closed:', m.get('closed'))
        print('OutcomePrices:', m.get('outcomePrices'))
        tokens = json.loads(m.get('clobTokenIds', '[]'))
        print('Tokens:', tokens)
        
        # Check token balance
        client = ClobClient(host='https://clob.polymarket.com', key=pk, chain_id=137, signature_type=2, funder=funder)
        creds = client.derive_api_key()
        client.set_api_creds(creds)
        if len(tokens) >= 2:
            p_up = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=tokens[0])
            b_up = client.get_balance_allowance(p_up)
            p_down = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=tokens[1])
            b_down = client.get_balance_allowance(p_down)
            print('UP Token Balance:', float(b_up.get('balance', 0))/1e6)
            print('DOWN Token Balance:', float(b_down.get('balance', 0))/1e6)
except Exception as e:
    print('Error:', e)
