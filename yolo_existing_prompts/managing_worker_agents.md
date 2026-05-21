# Skill: Managing Worker Agents

This skill provides highly detailed instructions on how the primary Yolo agent should spawn, manage, and interact with autonomous background worker agents.

## Context & Purpose

The Yolo architecture supports multi-agent orchestration. The primary agent acts as a Manager and can spawn isolated, specialized worker agents to handle long-running, complex, or parallel tasks. This prevents the primary reasoning loop from blocking and keeps the context window clean. 

Workers run autonomously in the background, have access to all coding and research tools, and maintain their own isolated session histories.

## Available Tools for the Manager

As the Manager, you have access to specific tools to control the worker lifecycle:

1. **`spawn_worker(user_id: int, role: str, objective: str)`**
   - **Purpose:** Spawns a single, highly specialized worker agent for a specific sub-task.
   - **Usage:** Define a clear `role` (e.g., "Frontend Developer", "Security Auditor") and a highly specific `objective` (e.g., "Implement the login form in src/Login.jsx and ensure tests pass").
   - **Return:** Returns a Task ID (e.g., `w_1a2b3c4d`) which you must track.

2. **`check_workers(user_id: int, task_id: str = None)`**
   - **Purpose:** Monitor the status of spawned workers.
   - **Usage:** Call this periodically to check if a worker is `running`, `completed`, `failed`, or `needs_help`. If `task_id` is provided, it retrieves the specific status and result summary.

3. **`dispatch_parallel_agents(user_id: int, objectives: list[str], mission_coro: Callable)`**
   - **Purpose:** Spawn multiple tracked agents simultaneously for parallel objectives (e.g., researching 5 different topics at once).

4. **`run_background_mission(user_id: int, objective: str, mission_coro: Callable)`**
   - **Purpose:** Spawn a long-running, complex mission.

## Worker Agent Lifecycle & Behaviors

Worker agents are initialized with a strict system prompt instructing them to:
1. Operate autonomously without asking the user for input.
2. Persist through errors and use tools to solve the objective.
3. Call **`report_completion(task_id, summary)`** when finished.
4. Call **`request_help(task_id, reason, context)`** if they are fundamentally blocked, confused, or failing tests repeatedly (e.g., 3+ times).

### Status States in the Database (`yolo_v2.db` -> `background_tasks`)
- `running`: The worker is currently executing its loop.
- `completed`: The worker successfully finished its task and called `report_completion`. The `result` field contains the summary.
- `needs_help`: The worker encountered a blocker and called `request_help`. The `result` field contains a JSON payload with `reason` and `context`.
- `failed`: The worker crashed, hit the maximum turn limit (30 turns), or timed out (30 minutes).

## Manager Procedures

When a user requests a complex task that should be delegated, follow this procedure:

### 1. Planning & Delegation
- Analyze the user's request and break it down into independent sub-tasks.
- Use `spawn_worker` for each sub-task. Ensure the `objective` is completely self-contained (e.g., "Create a Python script named fetch_data.py that downloads X and saves to Y. Verify it works.").
- **Do not** spawn multiple workers that will edit the exact same file simultaneously to prevent race conditions.

### 2. Monitoring
- After spawning workers, inform the user that tasks have been delegated to the background.
- Periodically use `check_workers` to poll their status.
- If a worker is `running`, do not interfere. Let it work.

### 3. Handling Completion
- When `check_workers` shows a worker is `completed`, read its `result` summary.
- Verify the worker's output if necessary (e.g., run tests yourself or inspect the modified files).
- Integrate the worker's findings or code into the broader project state.

### 4. Handling Blockers (`needs_help` or `failed`)
- If a worker reports `needs_help`, retrieve the `result` JSON to understand the blocker.
- **Intervention:** As the Manager, investigate the blocker yourself. Fix underlying architectural issues, provide missing context, or adjust the codebase.
- Once the blocker is resolved, you may spawn a *new* worker with an updated objective to resume the task, or finish the task yourself.
- If a worker is `failed`, investigate the logs or `background_tasks` history to determine why it crashed and correct the underlying issue before retrying.

## Expected Outcome

By adhering to this orchestration pattern, you act as a true 10x Engineer leading a virtual team. You effectively distribute work, monitor progress asynchronously, and intervene only when your expert architectural guidance is required.