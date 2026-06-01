import asyncio
import json
import uuid

from tools.registry import register_tool
from tools.database_ops import update_worker_status, add_worker_task, _conn_ctx
from tools.base import audit_log

import logging
logger = logging.getLogger(__name__)


@register_tool()
def report_completion(task_id: str, summary: str) -> str:
    """Worker tool: Report that the assigned task is complete."""
    update_worker_status(task_id, "completed", summary)
    audit_log("report_completion", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as completed."


@register_tool()
def request_help(task_id: str, reason: str, context: str) -> str:
    """Worker tool: Report confusion and request Manager assistance."""
    details = json.dumps({"reason": reason, "context": context})
    update_worker_status(task_id, "needs_help", details)
    audit_log("request_help", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as needs_help."


@register_tool()
async def spawn_worker(user_id: int, role: str, objective: str, swarm_id: str = None, model: str = None) -> str:
    """Manager tool: Spawn an isolated worker agent for a specific sub-task.

    Bug 5 fix: Properly handles missing event loop with a fallback.
    """
    task_id = f"w_{uuid.uuid4().hex[:8]}"
    add_worker_task(task_id, user_id, role, objective)

    from worker import run_worker_loop, _active_workers
    from tools.memory_service import get_memory

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Bug 5 fix: No running event loop — create one and run in background thread
        import threading

        def _run_in_thread():
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            _loop.run_until_complete(run_worker_loop(user_id, task_id, role, objective, get_memory(), swarm_id=swarm_id, model=model))
            _loop.close()

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        audit_log("spawn_worker", {"task_id": task_id, "role": role, "swarm_id": swarm_id, "fallback": "thread"}, "success")
        return f"Worker spawned (thread fallback) with Task ID: `{task_id}`. Role: {role}. Use `check_workers()` to monitor."

    # Normal async path: register the task so it can be cancelled later (Bug 1 fix)
    task = loop.create_task(run_worker_loop(user_id, task_id, role, objective, get_memory(), swarm_id=swarm_id, model=model))
    _active_workers[task_id] = task

    audit_log("spawn_worker", {"task_id": task_id, "role": role, "swarm_id": swarm_id}, "success")
    return f"Worker spawned with Task ID: `{task_id}`. Role: {role}. Swarm ID: {swarm_id}. Use `check_workers()` to monitor status."


@register_tool()
def check_workers(user_id: int, limit: int = 50) -> str:
    """Manager tool: Check the status of all active and recently completed workers.

    Bug 11 fix: Increased default limit from 10 to 50, made it a parameter.
    """
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT task_id, objective, status, result FROM background_tasks WHERE user_id = ? AND task_id LIKE 'w_%' ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cursor.fetchall()

    if not rows:
        return "No workers found."

    output = []
    for r in rows:
        res_preview = (r[3][:100] + "...") if r[3] and len(r[3]) > 100 else (r[3] or "None")
        output.append(f"- ID: {r[0]} | Status: {r[2]} | Obj: {r[1]}\n  Result/Help: {res_preview}")

    return "\n".join(output)


@register_tool()
async def spawn_team_discussion(topic: str, roles: list[str], max_rounds: int = 5, model: str = None) -> str:
    """Manager tool: Spawn a synchronous chat room where specialized agents debate a topic until consensus.

    Bug 8 fix: consensus_count is tracked across rounds, not reset each round.
    Bug 9 fix: temp_history correctly includes the participant's own prior replies.
    Bug 10 fix: Errors are logged with severity indication in transcript.
    """
    from agent import router

    transcript = [f"**MANAGER**: We need to discuss the following topic to reach a consensus or solution:\n{topic}\n"]

    # Initialize histories for each role
    participants = {}
    for role in roles:
        sys_prompt = (
            f"You are participating in an engineering team discussion as the: {role}.\n"
            "Review the transcript of the conversation so far, and provide your expert perspective, critique, or proposal.\n"
            "Be concise and technical. If you agree a consensus has been reached, state 'CONSENSUS REACHED'.\n"
            "Do NOT use tools. Just speak."
        )
        participants[role] = [{"role": "system", "content": sys_prompt}]

    # Bug 8 fix: Track which roles have agreed to consensus across rounds
    consensus_roles = set()

    rounds = 0
    while rounds < max_rounds:
        rounds += 1
        round_transcript = "\n".join(transcript)

        for role, history in participants.items():
            # Build specific prompt for this turn
            prompt = f"Here is the discussion so far:\n\n{round_transcript}\n\nWhat is your input {role}?"

            # Bug 9 fix: history already contains the participant's own prior replies
            # so we just append the new prompt to it
            history.append({"role": "user", "content": prompt})

            try:
                active_router = router
                if model:
                    from llm_router import LLMRouter, load_llm_config
                    config = load_llm_config()
                    config.model = model
                    active_router = LLMRouter(config)
                    
                response = await active_router.chat_completions(
                    messages=history,
                    tools=None,  # No tools in the chat room
                    tool_choice="none",
                    stream=False
                )
                if not getattr(response, "choices", None) or len(response.choices) == 0:
                    reply = "[No response generated]"
                else:
                    reply = response.choices[0].message.content

                # Save the reply to their history (Bug 9 fix: history is now correctly cumulative)
                history.append({"role": "assistant", "content": reply})

                transcript.append(f"**{role.upper()}**:\n{reply}\n")

                if "CONSENSUS REACHED" in reply.upper():
                    consensus_roles.add(role)

            except Exception as e:
                # Bug 10 fix: Mark error severity and note it doesn't count toward consensus
                transcript.append(f"**{role.upper()}** ⚠️ (Error — this round's input skipped): {e}\n")
                logger.warning(f"Team discussion error for {role}: {e}")

        # Bug 8 fix: Check if ALL roles have reached consensus (can be across rounds)
        if consensus_roles == set(participants.keys()):
            transcript.append("\n**SYSTEM**: All participants reached consensus. Discussion concluded.")
            break

    if rounds >= max_rounds:
        agreed = ", ".join(consensus_roles) if consensus_roles else "none"
        transcript.append(f"\n**SYSTEM**: Maximum rounds reached. Discussion terminated. Agreed: {agreed}")

    audit_log("spawn_team_discussion", {"topic": topic, "roles": roles, "rounds": rounds}, "success")
    return "\n".join(transcript)


@register_tool()
def cancel_all_workers(user_id: int) -> str:
    """Manager tool: Forcefully cancel all currently 'running' workers for the user.

    Bug 1 fix: Actually cancel the running asyncio tasks, not just update DB.
    Bug 2 fix: Only cancel worker tasks (w_ prefix), not background missions.
    """
    from worker import _active_workers

    # Bug 2 fix: Only target worker tasks with 'w_%' prefix
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT task_id FROM background_tasks WHERE user_id = ? AND status = 'running' AND task_id LIKE 'w_%'",
            (user_id,)
        )
        worker_ids = [row[0] for row in cursor.fetchall()]

        if worker_ids:
            placeholders = ",".join("?" * len(worker_ids))
            cursor.execute(
                f"UPDATE background_tasks SET status = 'cancelled', result = 'Terminated by manager' WHERE task_id IN ({placeholders})",
                worker_ids
            )

    # Bug 1 fix: Cancel the actual asyncio coroutines
    cancelled_count = 0
    for wid in worker_ids:
        task = _active_workers.pop(wid, None)
        if task and not task.done():
            task.cancel()
            cancelled_count += 1

    audit_log("cancel_all_workers", {"db_count": len(worker_ids), "task_count": cancelled_count}, "success")
    return f"Cancelled {len(worker_ids)} worker(s) in DB, {cancelled_count} running coroutine(s) stopped."




@register_tool()
async def spawn_swarm(user_id: int, objective: str, roles: list[str], model: str = None) -> str:
    """Manager tool: Create a new asynchronous Swarm to tackle a complex objective.
    
    This generates a unique swarm_id and spawns a 'Swarm Lead' agent. The Lead is
    responsible for spawning the sub-agents (based on the provided roles) and coordinating
    them using the swarm message bus.
    """
    swarm_id = f"swarm_{uuid.uuid4().hex[:6]}"
    lead_role = "Swarm Lead"
    
    lead_objective = (
        f"You are the Swarm Lead for Swarm ID: {swarm_id}.\n"
        f"The ultimate objective is: {objective}\n"
        f"You must use `spawn_worker(..., swarm_id='{swarm_id}')` to create the following sub-agents: {', '.join(roles)}.\n"
        "IMPORTANT: Do not spawn all sub-agents at once if they have dependencies. Spawn them sequentially.\n"
        "Coordinate their work using `broadcast_swarm_message` and `read_swarm_messages`.\n"
        "Use `wait_for_swarm_message` to pause your execution until a specific event or completion message occurs, "
        "saving resources rather than repeatedly calling `read_swarm_messages`.\n"
        "Wait for them to complete their tasks, synthesize the results, and then call `report_completion`."
    )
    
    # Delegate the actual spawning to the existing spawn_worker logic
    result = await spawn_worker(user_id, lead_role, lead_objective, swarm_id=swarm_id, model=model)
    
    audit_log("spawn_swarm", {"swarm_id": swarm_id, "roles": roles}, "success")
    return f"Swarm `{swarm_id}` created. {result}"


@register_tool()
def broadcast_swarm_message(task_id: str, swarm_id: str, role: str, message: str) -> str:
    """Worker tool: Broadcast a message to all members of a specific Swarm."""
    from tools.database_ops import add_swarm_message
    try:
        add_swarm_message(swarm_id, task_id, role, message)
        audit_log("broadcast_swarm_message", {"swarm_id": swarm_id, "sender": role}, "success")
        return "Message broadcasted to the swarm successfully."
    except Exception as e:
        logger.error(f"Failed to broadcast swarm message: {e}")
        return f"Error broadcasting message: {e}"


@register_tool()
def read_swarm_messages(swarm_id: str, limit: int = 20) -> str:
    """Worker tool: Read recent messages broadcasted by other agents in the Swarm."""
    from tools.database_ops import get_swarm_messages
    try:
        messages = get_swarm_messages(swarm_id, limit=limit)
        if not messages:
            return "No messages in the swarm bus yet."
            
        output = [f"--- Recent Messages for Swarm {swarm_id} ---"]
        for msg in messages:
            output.append(f"[{msg['created_at']}] {msg['sender_role']} ({msg['sender_task_id']}):\n{msg['message']}\n")
            
        audit_log("read_swarm_messages", {"swarm_id": swarm_id, "count": len(messages)}, "success")
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Failed to read swarm messages: {e}")
        return f"Error reading messages: {e}"


@register_tool()
async def wait_for_swarm_message(swarm_id: str, pattern: str, timeout_seconds: int = 300) -> str:
    """Worker tool: Pause execution and wait until a message matching a regex pattern is broadcasted to the swarm.
    
    This is highly recommended over repeatedly polling `read_swarm_messages`.
    """
    import re
    from tools.database_ops import get_swarm_messages
    
    audit_log("wait_for_swarm_message", {"swarm_id": swarm_id, "pattern": pattern, "timeout": timeout_seconds}, "info")
    
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except Exception as e:
        return f"Error compiling regex pattern '{pattern}': {e}"
        
    start_time = asyncio.get_event_loop().time()
    
    # Check current messages first to see if it already happened
    try:
        initial_messages = get_swarm_messages(swarm_id, limit=50)
        # Check backwards so we see newest first, but actually any match is fine.
        for msg in initial_messages:
            if regex.search(msg['message']):
                return f"Match found immediately in past messages:\n[{msg['created_at']}] {msg['sender_role']}: {msg['message']}"
    except Exception:
        pass
        
    # Poll database incrementally (acting like a condition variable without needing pub/sub setup)
    while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
        try:
            # We only need the very newest messages
            recent_msgs = get_swarm_messages(swarm_id, limit=5)
            for msg in recent_msgs:
                # We need to make sure this message was created AFTER we started waiting.
                # Simplest heuristic: check if any recent message matches.
                # In a real event bus we'd use a cursor/timestamp, but string match works for YOLO mode.
                if regex.search(msg['message']):
                    audit_log("wait_for_swarm_message", {"swarm_id": swarm_id, "status": "matched"}, "success")
                    return f"Match found!\n[{msg['created_at']}] {msg['sender_role']}: {msg['message']}"
        except Exception as e:
            logger.warning(f"Error checking messages during wait: {e}")
            
        await asyncio.sleep(5)  # Poll every 5 seconds
        
    audit_log("wait_for_swarm_message", {"swarm_id": swarm_id, "status": "timeout"}, "info")
    return f"Timeout reached ({timeout_seconds}s) waiting for pattern '{pattern}'."
