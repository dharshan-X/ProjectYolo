# Skill: Managing Worker Agents

This skill provides highly detailed instructions on how the primary Yolo agent should spawn, manage, and interact with autonomous background worker agents.

## Context & Purpose

The Yolo architecture supports multi-agent orchestration. The primary agent acts as a Manager and can spawn isolated, specialized worker agents to handle long-running, complex, or parallel tasks. This prevents the primary reasoning loop from blocking and keeps the context window clean. 

Workers run autonomously in the background, have access to all coding and research tools, and maintain their own isolated session histories.

## Available Tools for the Manager

As the Manager, you have access to specific tools to control the worker lifecycle:

1. **`run_background_mission(user_id: int, objective: str, mission_coro: Callable)`**
   - **Purpose:** Spawns a single autonomous background worker for a specific sub-task.
   - **Usage:** Provide a highly specific, self-contained `objective` (e.g., "Implement the login form in src/Login.jsx and ensure tests pass").
   - **Return:** Returns a task ID (e.g., `w_1a2b3c4d`) which you must track.

2. **`dispatch_parallel_agents(user_id: int, objectives: list[str], mission_coro: Callable)`**
   - **Purpose:** Spawn multiple tracked agents simultaneously for parallel objectives (e.g., researching 5 different topics at once). Spawns one worker per objective.
   - **Return:** A summary of spawned task IDs and their objectives.

## Monitoring Workers

There is no dedicated `check_workers` tool. Instead, query the `background_tasks` database table directly to check worker status:
- Use database tools (e.g., `run_bash` with `sqlite3` or a DB query tool) to query the `background_tasks` table.
- Filter by `user_id` and optionally `task_id` to retrieve status and results.

## Worker Agent Lifecycle & Behaviors

Worker agents are initialized with a strict system prompt (the background mission appendix) instructing them to:
1. Operate autonomously without asking the user for input.
2. Persist through errors and use tools to solve the objective.
3. Run `run_agent_turn` in an isolated session loop until the objective is achieved or they cannot proceed.
4. Produce a final assistant message summarizing their results when complete.

### Status States in the Database (`background_tasks` table)
- `running`: The worker is currently executing its agent turn loop.
- `completed`: The worker successfully finished its task. The `result` field contains the summary and the `history` field contains the full session log.
- `failed`: The worker crashed, hit the maximum turn limit, or timed out. The `history` field contains diagnostic information.

## Manager Procedures

When a user requests a complex task that should be delegated, follow this procedure:

### 1. Planning & Delegation
- Analyze the user's request and break it down into independent sub-tasks.
- Use `run_background_mission` for individual sub-tasks, or `dispatch_parallel_agents` for multiple independent tasks at once.
- Ensure each `objective` is completely self-contained (e.g., "Create a Python script named fetch_data.py that downloads X and saves to Y. Verify it works.").
- **Do not** spawn multiple workers that will edit the exact same file simultaneously to prevent race conditions.

### 2. Monitoring
- After spawning workers, inform the user that tasks have been delegated to the background.
- Query the `background_tasks` table to check worker status when needed.
- If a worker is `running`, do not interfere. Let it work.

### 3. Handling Completion
- When a worker's status is `completed`, read its `result` summary and `history` from the `background_tasks` table.
- Verify the worker's output if necessary (e.g., run tests yourself or inspect the modified files).
- Integrate the worker's findings or code into the broader project state.

### 4. Handling Failures
- If a worker's status is `failed`, inspect its `history` in the `background_tasks` table to understand what went wrong.
- **Intervention:** As the Manager, investigate the failure yourself. Fix underlying architectural issues, provide missing context, or adjust the codebase.
- Once the issue is resolved, spawn a *new* worker with an updated objective to resume the task, or finish the task yourself.

## Expected Outcome

By adhering to this orchestration pattern, you act as a true 10x Engineer leading a virtual team. You effectively distribute work, monitor progress asynchronously, and intervene only when your expert architectural guidance is required.