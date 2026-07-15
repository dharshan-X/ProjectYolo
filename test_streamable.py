import asyncio
import httpx
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Tuple
from mcp.shared.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

@asynccontextmanager
async def streamable_client(url: str, headers: dict = None):
    headers = headers or {}
    read_stream_sender, read_stream_receiver = asyncio.Queue(), asyncio.Queue()
    
    # We will just write a custom client later if needed. For now, let's just see if we can use sse_client but send the endpoint event ourselves in a proxy!
