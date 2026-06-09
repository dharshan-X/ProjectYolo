import asyncio
from session import Session
from tools.yolo_memory import TieredMemoryEngine
import os
import agent

async def main():
    if os.path.exists("yolo_memory.db"):
        os.remove("yolo_memory.db")

    engine = TieredMemoryEngine(db_path="yolo_memory.db")
    engine.add("user: i am dharshan\nassistant: Hello, Dharshan. How can I assist you today?", "1")

    session = Session(user_id=1)
    
    # Use the mock engine for memory
    agent._memory_service_override = engine
    
    print("Running turn...")
    response = await agent.run_agent_turn("who am i", session, memory_service=engine)
    print("RESPONSE:", response)

asyncio.run(main())
