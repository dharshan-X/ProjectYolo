import asyncio
import aiohttp
import json

async def test():
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect('ws://127.0.0.1:8790/browser/stream') as ws:
            print("Connected!")
            await ws.send_json({"type": "mousemove", "x": 100, "y": 100})
            await ws.send_json({"type": "click", "x": 100, "y": 100, "button": "left"})
            print("Sent click!")
            # Read one frame
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    print("Got frame!")
                    break

asyncio.run(test())
