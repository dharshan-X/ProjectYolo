import asyncio
import os
import logging
import json
from typing import Any
from session import Session
import agent

logger = logging.getLogger(__name__)

# Global registry of active worker tasks so they can be cancelled
_active_workers: dict[str, asyncio.Task] = {}


def get_active_workers() -> dict[str, asyncio.Task]:
    """Return the global registry of running worker asyncio.Tasks."""
    return _active_workers


async def run_worker_loop(user_id: int, task_id: str, role: str, objective: str, memory_service: Any, swarm_id: str = None) -> None:
    """An isolated loop for a specialized worker agent using central orchestration.

    Fixes applied:
    - Bug 3: Break out of tool loop immediately after __WORKER_TERMINATE__
    - Bug 4: Persist worker history to DB after every turn (finally block)
    - Bug 6: Only catch IntegrityError for duplicate-insert guard, not all exceptions
    - Bug 7: Retry transient errors up to 3 times before marking as failed
    """
    import sqlite3
    from tools.database_ops import add_worker_task, update_worker_status, update_background_task_history

    # Ensure a record exists in the DB immediately
    # Bug 6 fix: Only catch IntegrityError, not all exceptions
    try:
        add_worker_task(task_id, user_id, role, objective)
    except sqlite3.IntegrityError:
        pass  # Already added by spawn_worker, expected
    except Exception as e:
        logger.error(f"[{task_id}] Failed to create DB record: {e}")
        return  # Can't run without a DB record

    worker_session = Session(user_id=user_id)
    # Default worker to YOLO mode as it runs autonomously
    worker_session.yolo_mode = True

    # Specialized system prompt for the worker
    system_prompt = (
        f"You are a specialized worker agent taking on the role of: {role}.\n"
        f"Your specific objective is: {objective}\n"
        f"Your Task ID is: {task_id}\n\n"
    )

    if swarm_id:
        system_prompt += (
            f"You are part of a Swarm (Swarm ID: {swarm_id}).\n"
            "You MUST collaborate with other swarm members to achieve the overall objective.\n"
            "Use `broadcast_swarm_message(task_id=..., swarm_id=..., role=..., message=...)` to share updates, code, or ask for reviews.\n"
            "Use `read_swarm_messages(swarm_id=...)` frequently to stay synced with your team.\n"
            "If you are the Swarm Lead, you should also spawn sub-workers using `spawn_worker(..., swarm_id=...)` to delegate tasks.\n\n"
        )

    system_prompt += (
        "You operate in an isolated context. You have access to all coding and research tools.\n"
        "CRITICAL: When you have finished the objective, you MUST call `report_completion(task_id=..., summary=...)`.\n"
        "CRITICAL: If you are confused, stuck (e.g. failing tests 3+ times), or blocked by architecture, you MUST call `request_help(task_id=..., reason=..., context=...)`.\n"
        "Do NOT ask the user for input. You run autonomously."
    )

    # Initialize history with the specialized prompt
    worker_session.message_history = [{"role": "system", "content": system_prompt}]

    max_turns = int(os.getenv("WORKER_MAX_TURNS", "30"))
    worker_timeout = int(os.getenv("WORKER_TIMEOUT_SECONDS", "1800"))
    max_retries_per_turn = 3
    turns = 0

    try:
        async def _run():
            nonlocal turns
            current_prompt = None  # Start with None since system prompt is already set

            while turns < max_turns:
                # Bug 1 fix: Check DB status every turn to respect cancellation
                from tools.database_ops import get_worker_status
                status_check = get_worker_status(task_id)
                if status_check.get("status") in ("cancelled", "completed", "failed"):
                    logger.info(f"[{task_id}] Worker stopped: DB status is '{status_check['status']}'")
                    break

                turns += 1
                print(f"[{task_id}] Turn {turns}...")

                # Bug 7 fix: Retry transient errors instead of immediately failing
                retries = 0
                while retries < max_retries_per_turn:
                    try:
                        result = await agent.run_agent_turn(
                            current_prompt,
                            worker_session,
                            signal_handler=None,
                            memory_service=memory_service
                        )

                        if "__WORKER_TERMINATE__" in result:
                            print(f"[{task_id}] Worker task terminated normally.")
                            return  # Bug 3 fix: Return immediately, no further processing

                        # If the agent didn't terminate, continue with a reminder
                        current_prompt = "Please continue working towards the objective. Use `report_completion` once finished."
                        break  # Success, exit retry loop

                    except Exception as e:
                        retries += 1
                        err_msg = str(e)
                        logger.warning(f"[{task_id}] Error in worker turn (attempt {retries}/{max_retries_per_turn}): {err_msg}")

                        # Fatal errors: don't retry
                        if "401" in err_msg or "unauthorized" in err_msg.lower():
                            update_worker_status(task_id, "failed", "Unauthorized: LLM token expired or invalid.")
                            return
                        
                        if retries >= max_retries_per_turn:
                            update_worker_status(task_id, "failed", f"Worker failed after {max_retries_per_turn} retries on turn {turns}: {e}")
                            return
                        
                        # Exponential backoff before retry
                        await asyncio.sleep(2 ** retries)
                
                # Bug 4 fix: Persist history after every successful turn
                try:
                    update_background_task_history(task_id, worker_session.message_history)
                except Exception as he:
                    logger.warning(f"[{task_id}] Failed to persist history: {he}")

            if turns >= max_turns:
                update_worker_status(task_id, "failed", "Worker hit max turns limit.")

        await asyncio.wait_for(_run(), timeout=worker_timeout)

    except asyncio.TimeoutError:
        update_worker_status(task_id, "failed", f"Worker timed out after {worker_timeout} seconds.")
    except asyncio.CancelledError:
        # Bug 1 fix: Handle actual asyncio cancellation gracefully
        update_worker_status(task_id, "cancelled", "Worker coroutine was cancelled.")
        logger.info(f"[{task_id}] Worker cancelled via asyncio.")
    except Exception as e:
        logger.exception("Global worker error")
        update_worker_status(task_id, "failed", f"Global worker loop error: {e}")
    finally:
        # Bug 4 fix: Final history persistence
        try:
            from tools.database_ops import update_background_task_history
            update_background_task_history(task_id, worker_session.message_history)
        except Exception:
            pass
        # Clean up from active registry
        _active_workers.pop(task_id, None)
