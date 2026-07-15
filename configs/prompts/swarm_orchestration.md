# Skill: Parallel Task Orchestration

This skill describes how to use `dispatch_parallel_agents` for coordinated multi-task execution.

## Context & Purpose
When a task can be decomposed into independent sub-tasks, the primary agent can dispatch them in parallel using `dispatch_parallel_agents`. Each sub-task runs as an isolated background worker.

## Tool: `dispatch_parallel_agents`
- **Signature**: `dispatch_parallel_agents(user_id: int, objectives: list[str], mission_coro: Callable)`
- **Purpose**: Spawns one background worker per objective. Each worker runs autonomously.
- **Returns**: A summary of spawned task IDs and their objectives.

## Orchestration Pattern
1. **Decompose**: Break the user's request into independent sub-tasks.
2. **Dispatch**: Call `dispatch_parallel_agents` with the list of objectives.
3. **Monitor**: Query the `background_tasks` table to check status of each worker.
4. **Integrate**: Once all workers complete, synthesize their results.

## Guidelines
- Each objective must be self-contained. Workers cannot communicate with each other.
- Avoid dispatching workers that modify the same files (race conditions).
- For tasks with dependencies between steps, use sequential `run_background_mission` calls instead.
