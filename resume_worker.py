
import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from worker import run_worker_loop
from tools.memory_service import get_memory
from tools.settings import load_settings

async def resume():
    load_settings()
    user_id = 7118893093
    task_id = "w_df9b573b"
    role = "QA/Accessibility Reviewer"
    objective = "[QA/Accessibility Reviewer] (Swarm swarm_ff67af) Target site: /home/dharshan/Documents/sandbox/terminal-site. Review for accessibility, keyboard support, semantics, contrast. Provide a concise report and any required code edits suggestions."
    swarm_id = "swarm_ff67af"
    
    print(f"Resuming worker {task_id}...")
    await run_worker_loop(user_id, task_id, role, objective, get_memory(), swarm_id=swarm_id)

if __name__ == "__main__":
    asyncio.run(resume())
