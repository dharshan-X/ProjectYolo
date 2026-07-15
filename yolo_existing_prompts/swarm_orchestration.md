# Skill: Swarm Orchestration

Instructions on how the primary Yolo agent should use the Multi-Agent Swarm Orchestration capabilities to tackle highly complex tasks asynchronously.

---

## Context & Purpose

While `spawn_worker` is useful for isolated tasks, `spawn_swarm` enables a coordinated team of background workers. The swarm operates with a **Swarm Lead** (the manager of the swarm) and various sub-agents. They share a persistent message bus that allows them to pass data, request reviews, and synchronize their work without blocking the primary user-facing agent.

Use a swarm when the task naturally decomposes into **coordinated** roles with hand-offs. Use a plain worker when the task is independent.

---

## Tools Overview

### 1. `spawn_swarm(user_id: int, objective: str, roles: list[str])`
- **User**: Primary Agent.
- **Purpose**: Start a new swarm. Generates a unique `swarm_id` and spawns the Swarm Lead.
- **Usage**: Provide the overall `objective` and a list of `roles` (e.g., `["Frontend Dev", "Backend Dev", "QA Tester"]`). The Swarm Lead will be instructed to spawn these as sub-agents.
- **Returns**: `swarm_id`. Track it.

### 2. `broadcast_swarm_message(task_id: str, swarm_id: str, role: str, message: str)`
- **User**: Swarm workers (and the Lead).
- **Purpose**: Post a message to the shared swarm message bus.
- **Usage**: Report progress, share code snippets, or notify teammates that a partial result is ready for review.

### 3. `read_swarm_messages(swarm_id: str, limit: int)`
- **User**: Swarm workers (and the Lead).
- **Purpose**: Read recent messages posted by other swarm members.
- **Usage**: Call periodically to stay synced. Before starting dependent work, read the bus to see whether upstream teammates have shipped.

---

## How to Orchestrate a Swarm

### 1. Initiation (Primary Agent)

When the user gives a complex task requiring multiple domains of expertise:

- Decompose the task into roles. Each role should have:
  - A clear responsibility (one well-defined slice).
  - An interface contract with other roles (APIs, files, message format).
  - An exit criterion.
- Call `spawn_swarm` with the objective and the required roles.
- Inform the user that a swarm has been dispatched and provide the `swarm_id`.
- Use `check_workers` periodically to monitor the overall status of the Swarm Lead.

### 2. Swarm Lead Responsibilities

When spawned as a Swarm Lead, you:

1. Use `spawn_worker(..., swarm_id=...)` to create the sub-agents for each role. Pass **role-specific, scoped objectives**.
2. Coordinate their work. Read the message bus frequently.
3. If a sub-agent gets stuck:
   - Provide guidance via the message bus (broadcast a tip or new constraint).
   - Adjust the worker's objective (spawn a replacement worker).
   - If the blocker is architectural in the codebase, fix it yourself in the parent.
4. Detect deadlocks: if messages stop flowing for more than a few check cycles, inspect each worker and steer them.
5. After all sub-agents have completed and you have synthesized the final result, call `report_completion`.

### 3. Sub-Agent Responsibilities

When spawned as a sub-agent within a Swarm:

1. You have a specific objective (e.g., "Write the tests").
2. Before starting dependent work, `read_swarm_messages` to learn what teammates have shipped.
3. Once your code is written, `broadcast_swarm_message` to notify the QA or Lead role that your work is ready for review.
4. When your sub-task is complete **and approved** by the Lead, call `report_completion`.
5. Never block silently. If waiting on a peer, broadcast what you are waiting on.

---

## Message Hygiene

Treat the swarm message bus like a shared log:

- **Be concise and actionable** — one paragraph or a few lines. No novel-length posts.
- **Include artifacts** — when handing off code, include file paths and short snippets rather than walls of code.
- **Tag intent** — prefix the message with `[READY]`, `[BLOCKED]`, `[REVIEW-REQUEST]`, `[FIX]`, or `[DONE]` so readers can scan.
- **Quote contracts verbatim** — when you need a teammate to depend on a contract (API shape, schema, port), paste the precise spec.
- **Avoid duplicates** — check the bus before re-posting the same update.

### Recommended message format

```
[<TAG>] <role> -> <recipient role(s)>
Status: <one line>
Artifact: <file paths or URL>
Detail: <short paragraph or contract spec>
Wait-on: <what unblocks the next step, if any>
```

---

## Conflict & Deadlock Handling

- **Code conflicts**: When two workers edit overlapping files, the Swarm Lead must serialize them or hand one off to itself.
- **Contract drift**: When a teammate's contract changes, that worker should broadcast `[CONTRACT-CHANGE]` and wait for downstream acknowledgement before continuing.
- **Bug rebellion**: When QA finds a bug, broadcast `[BUG]` with reproduction steps and the offending file/line. The relevant role responds with `[FIX]`.
- **Stall detection**: If two polls show no new messages and no worker status change, the Lead should proactively nudge stuck roles.

---

## Example Workflow

**User**: "Build a full-stack to-do app in the `todo_app` directory."

**Primary Agent**: Calls `spawn_swarm` with roles `["React Dev", "FastAPI Dev", "QA Engineer"]`.

**Swarm Lead**: Spawns the three workers; broadcasts the agreed API contract (port 8000, `/api/todos`).

**FastAPI Dev**: Implements the backend. Tests it via curl/pytest. Broadcasts `[READY] Backend is running on port 8000, API docs at /docs, schema: {id, title, done}`. Calls `report_completion`.

**React Dev**: Calls `read_swarm_messages`, sees the backend is ready, builds the frontend to call port 8000. Broadcasts `[READY] Frontend is done`. Calls `report_completion`.

**QA Engineer**: Reads both `[READY]` messages, runs end-to-end browser tests, finds a bug, broadcasts `[BUG] POST /api/todos accepts empty title — see api.py:42`. The Lead forwards this to the FastAPI Dev (re-spawned with the bug report) who broadcasts `[FIX]` after fixing.

**Swarm Lead**: Confirms all `[DONE]` tags are present, runs the full test suite itself, synthesizes the final state, calls `report_completion` to tell the Primary Agent the swarm finished successfully.

**Primary Agent**: Reviews the Swarm Lead's summary, verifies artifacts, presents the integrated result to the user.

---

## Expected Outcome

By the time the swarm reports completion, the Primary Agent receives a coherent end-to-end result with all roles' work reviewed, conflicts resolved, and the merged product verified. The user is shielded from orchestration churn.
