import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from tools.team_ops import spawn_swarm, check_workers, cancel_all_workers
from tools.database_ops import init_db

async def run_test():
    init_db()
    user_id = 12345
    
    # Cancel any existing workers for this test user
    cancel_all_workers(user_id)
    
    objective = (
        "Create a small Python application called 'math_utils.py' that includes functions for factorial and fibonacci. "
        "Also create a 'test_math_utils.py' using pytest to test these functions. "
        "Run the tests to ensure they pass."
    )
    roles = ["Lead Developer", "QA Engineer"]
    
    print(f"Spawning swarm for user {user_id}...")
    print(f"Objective: {objective}")
    print(f"Roles: {roles}")
    
    result = await spawn_swarm(user_id, objective, roles)
    print("\nSwarm creation result:")
    print(result)
    
    print("\nMonitoring swarm execution (checking every 10 seconds)...")
    try:
        for i in range(20): # Monitor for up to ~3 minutes
            await asyncio.sleep(10)
            status = check_workers(user_id, limit=20)
            print(f"\n--- Worker Status (Check {i+1}) ---")
            print(status)
            
            # Check if all workers are completed or cancelled
            if status and "No workers found" not in status:
                lines = status.split('\n')
                # Count how many are running vs completed
                running = sum(1 for line in lines if "Status: running" in line)
                needs_help = sum(1 for line in lines if "Status: needs_help" in line)
                if running == 0 and needs_help == 0 and len(lines) > 0:
                    print("\nAll workers have finished their execution.")
                    break
    except KeyboardInterrupt:
        print("\nTest interrupted. Cancelling workers...")
        cancel_all_workers(user_id)

if __name__ == "__main__":
    asyncio.run(run_test())
