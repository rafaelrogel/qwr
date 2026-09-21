import asyncio
import websockets
import json

async def test_ws():
    url = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    print(f"Conectando a {url}...", flush=True)
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=15, open_timeout=10) as ws:
            print("Conectado! Aguardando 1 msg...", flush=True)
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            print(f"Msg: p={data.get('p')}, q={data.get('q')}, m={data.get('m')}", flush=True)
    except Exception as e:
        print(f"Erro no ws: {e}", flush=True)

asyncio.run(test_ws())
