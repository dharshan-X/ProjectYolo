# Skill: Swarm Orchestration

This skill provides instructions on how the primary Yolo agent should use the Multi-Agent Swarm Orchestration capabilities to tackle highly complex tasks asynchronously.

## Context & Purpose

While the `spawn_worker` tool is useful for isolated tasks, `spawn_swarm` allows the creation of a coordinated team of background workers. The swarm operates with a "Swarm Lead" (the manager of the swarm) and various sub-agents. They share a persistent message bus that allows them to pass data, request reviews, and synchronize their work without blocking the primary user-facing agent.

## Tools Overview

1. **`spawn_swarm(user_id: int, objective: str, roles: list[str])`**
   - **User:** Primary Agent
   - **Purpose:** Starts a new swarm. It generates a unique `swarm_id` and spawns a "Swarm Lead" agent.
   - **Usage:** Provide the overall `objective` and a list of `roles` (e.g., `["Frontend Dev", "Backend Dev", "QA Tester"]`). The Swarm Lead will automatically be instructed to spawn these roles.

2. **`broadcast_swarm_message(task_id: str, swarm_id: str, role: str, message: str)`**
   - **User:** Swarm Workers
   - **Purpose:** Post a message to the shared swarm message bus.
   - **Usage:** Use this to report progress, share code snippets, or notify other team members that your part of the task is complete and ready for review.

3. **`read_swarm_messages(swarm_id: str, limit: int)`**
   - **User:** Swarm Workers
   - **Purpose:** Read the recent messages posted by other members of the swarm.
   - **Usage:** Call this periodically to stay synced. If you are waiting on another agent, it is highly recommended to use `wait_for_swarm_message` instead.

4. **`wait_for_swarm_message(swarm_id: str, pattern: str, timeout_seconds: int)`**
   - **User:** Swarm Workers
   - **Purpose:** Pause execution until a message matching a regex pattern is broadcasted to the swarm.
   - **Usage:** Use this to pause your workflow without consuming turns. For example, `wait_for_swarm_message(swarm_id, "Backend API complete")`.

## How to Orchestrate a Swarm

### 1. Initiation (Primary Agent)
When the user gives a complex task requiring multiple domains of expertise:
- Call `spawn_swarm` with the objective and the required roles.
- Inform the user that a Swarm has been dispatched and provide the `swarm_id`.
- Use `check_workers` periodically to monitor the overall status of the Swarm Lead.

### 2. Swarm Lead Responsibilities
If you are spawned as a "Swarm Lead", your specific instructions are to:
1. **Plan Dependencies:** Do NOT spawn all workers simultaneously if they have dependencies.
2. **Execute Sequentially:** Use `spawn_worker(..., swarm_id=...)` to create the first agent. Then use `wait_for_swarm_message` to wait for them to broadcast completion before spawning the next agent.
3. Coordinate their work. 
4. If a sub-agent gets stuck, you can provide guidance via the message bus or spawn a new agent to help them.
5. Once all sub-agents have completed their objectives and you have synthesized the final result, call `report_completion`.

### 3. Sub-Agent Responsibilities
If you are spawned as a sub-agent within a Swarm:
1. You have a specific objective (e.g., "Write the tests").
2. Check `read_swarm_messages` to see what your teammates have done, or use `wait_for_swarm_message` if you are blocked.
3. Once your code is written, use `broadcast_swarm_message` to tell the QA or Lead agent that your work is ready for review. Include a clear, easily matchable phrase like "[TASK COMPLETE]".
4. When your specific sub-task is totally complete and approved by the Lead, call `report_completion`.

## Example Workflow

**User:** "Build a full-stack to-do app in the `todo_app` directory."
**Primary Agent:** Calls `spawn_swarm` with roles `["React Dev", "FastAPI Dev", "QA Engineer"]`.
**Swarm Lead:** Spawns "FastAPI Dev". Waits for message matching `API COMPLETE`.
**FastAPI Dev:** Writes the backend, tests it, then calls `broadcast_swarm_message` saying "[API COMPLETE] Backend is running". Then calls `report_completion`.
**Swarm Lead:** Sees match, then spawns "React Dev".
**React Dev:** Builds the frontend to connect to the backend. Broadcasts "[FRONTEND COMPLETE]".
**Swarm Lead:** Sees match, spawns "QA Engineer".
**QA Engineer:** Runs end-to-end tests. Finds bug, broadcasts to React Dev.
**React Dev:** Fixes bug, broadcasts "[FRONTEND COMPLETE]".
**Swarm Lead:** Synthesizes the final state, calls `report_completion` to tell the Primary Agent that the entire swarm has finished successfully.
