import asyncio
from session import Session
from agent import run_agent_turn

async def main():
    sess = Session(user_id=1)
    sess.yolo_mode = True
    prompt = "Spawn a worker to write a hello world python script."
    result = await run_agent_turn(prompt, sess)
    print(result)

asyncio.run(main())
