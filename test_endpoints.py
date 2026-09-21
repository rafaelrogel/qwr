import asyncio
import websockets
import json

endpoints = [
    "wss://fstream.binance.com/stream?streams=btcusdt@aggTrade",
    "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
    "wss://fstream.binance.com/ws/btcusdt@aggTrade"
]

async def test_endpoint(ep):
    print(f"Testando {ep}...", flush=True)
    try:
        async with websockets.connect(ep, open_timeout=4) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=4)
            print(f" -> SUCESSO em {ep}! Msg preview: {msg[:80]}", flush=True)
            return ep
    except Exception as e:
        print(f" -> FALHA em {ep}: {e}", flush=True)
        return None

async def main():
    for ep in endpoints:
        res = await test_endpoint(ep)
        if res:
            print(f"[OK] Melhor endpoint: {res}")
            break

asyncio.run(main())
