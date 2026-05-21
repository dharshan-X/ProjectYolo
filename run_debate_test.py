import asyncio
import os
import sys

# Ensure we're in the right directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools.team_ops import spawn_team_discussion
from tools.database_ops import init_db

async def run_debate():
    init_db()
    
    topic = "We are a newly funded, pre-product-market-fit startup building a B2B SaaS platform. We need to decide on our initial backend architecture: Monolith vs. Microservices. The team is small (3 backend engineers)."
    roles = [
        "Monolithic Architecture Advocate",
        "Microservices Architecture Advocate",
        "Pragmatic CTO"
    ]
    
    print(f"Spawning team discussion on topic:\n{topic}\n")
    print(f"Roles involved: {roles}\n")
    print("-" * 50)
    
    # max_rounds=2 to keep the test reasonably short, but enough to see interaction
    transcript = await spawn_team_discussion(topic, roles, max_rounds=2)
    
    print(transcript)
    print("-" * 50)
    print("Debate finished.")

if __name__ == "__main__":
    asyncio.run(run_debate())
