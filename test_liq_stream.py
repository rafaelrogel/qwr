import asyncio
import json
import websockets

async def main():
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"
    print("Conectando ao WebSocket de liquidacoes da Binance...", flush=True)
    try:
        async with websockets.connect(url) as ws:
            print("Conectado! Aguardando eventos de liquidacao...", flush=True)
            for i in range(5):
                msg = await ws.recv()
                data = json.loads(msg)
                o = data.get("o", {})
                sym = o.get("s")
                side = o.get("S")
                qty = float(o.get("q", 0))
                price = float(o.get("p", 0))
                vol = qty * price
                print(f"[{i+1}/5] LIQUIDACAO: {sym} | {side} | {qty} cotas @ ${price:,.2f} = ${vol:,.2f} USD", flush=True)
    except Exception as e:
        print("Erro:", e, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
