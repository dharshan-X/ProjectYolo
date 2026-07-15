# Skill: Managing Worker Agents

Highly detailed instructions on how the primary Yolo agent should spawn, manage, and interact with autonomous background worker agents.

---

## Context & Purpose

The Yolo architecture supports multi-agent orchestration. The primary agent acts as a Manager and can spawn isolated, specialized worker agents to handle long-running, complex, or parallel tasks. This prevents the primary reasoning loop from blocking and keeps the context window clean.

Workers run autonomously in the background, have access to all coding and research tools, and maintain their own isolated session histories.

---

## Available Tools for the Manager

As the Manager, you have access to specific tools to control the worker lifecycle:

### 1. `spawn_worker(user_id: int, role: str, objective: str)`
- **Purpose**: Spawn a single, highly specialized worker agent for one sub-task.
- **Usage**: Define a clear `role` (e.g., `"Frontend Developer"`, `"Security Auditor"`) and a **highly specific, self-contained** `objective` (e.g., `"Implement the login form in src/Login.jsx using the existing FormField component, add tests in src/Login.test.tsx, run the test suite, confirm all pass"`).
- **Return**: A Task ID (e.g., `w_1a2b3c4d`). Track this ID.

### 2. `check_workers(user_id: int, task_id: str = None)`
- **Purpose**: Monitor the status of spawned workers.
- **Usage**: Call this to check whether a worker is `running`, `completed`, `failed`, or `needs_help`. If `task_id` is provided, retrieve the specific status and result.
- **Cadence**: Don't poll faster than once every ~30 seconds. Use dead time for other work.

### 3. `dispatch_parallel_agents(user_id: int, objectives: list[str], mission_coro: Callable)`
- **Purpose**: Spawn multiple tracked agents simultaneously for parallel objectives (e.g., five independent topical investigations).

### 4. `run_background_mission(user_id: int, objective: str, mission_coro: Callable)`
- **Purpose**: Spawn a long-running, complex mission that should outlive the parent session if needed.

---

## Objective Quality Bar

A worker is only as good as its objective. Apply this checklist before calling `spawn_worker`:

- **Self-contained** — The objective includes all context the worker needs. It does not require the worker to ask follow-up questions.
- **Verifiable** — The objective states what success looks like. A test pass, a file created, an artifact emitted, a metric crossed.
- **Scoped** — The objective fits in one worker's context. If a sub-task needs more than ~25 turns, split it.
- **Non-overlapping** — Multiple workers do not edit the same file. If two objectives need to touch the same file, sequence them in the parent rather than parallelize.
- **Includes constraints** — Coding style, libraries to use, file paths, existing helpers — anything the worker would otherwise have to discover.

**Template**:
```
Implement <feature> in `<path>`.
Existing components to use: <list>.
Tests required: <test file path>.
Done when: <test command output is all green>.
```

---

## Worker Agent Lifecycle & Behaviors

Worker agents are initialized with a strict system prompt instructing them to:

1. Operate autonomously without asking the user for input.
2. Persist through errors and use tools to solve the objective.
3. Call `report_completion(task_id, summary)` when finished.
4. Call `request_help(task_id, reason, context)` when blocked, confused, or failing tests repeatedly (3+ times).

### Status States in the Database (`yolo_v2.db` → `background_tasks`)

| Status | Meaning | Manager Action |
|---|---|---|
| `running` | Worker is executing its loop. | Leave it alone. Poll later. |
| `completed` | Worker called `report_completion`. `result` contains the summary. | Review, verify, integrate. |
| `needs_help` | Worker called `request_help`. `result` contains `reason` and `context` JSON. | Investigate and intervene. |
| `failed` | Worker crashed, hit the 30-turn limit, or the 30-minute timeout. | Inspect logs; correct the underlying issue before retrying. |

---

## Manager Procedures

### 1. Planning & Delegation
- Analyze the user's request and decompose it into **independent** sub-tasks.
- Use `spawn_worker` for each. Ensure the `objective` is fully self-contained.
- **Do NOT** spawn multiple workers that edit the same file simultaneously — race conditions will corrupt the file.
- If two workers must both read the same artifact, ensure the read produces idempotent results and the writes target disjoint files.

### 2. Monitoring
- After spawning workers, inform the user that tasks have been delegated. Include the task IDs and the planned verification step.
- Periodically use `check_workers` to poll status (≥30s between poles).
- If a worker remains `running` after the expected duration, **wait** before intervening. Don't yank the wheel.

### 3. Handling Completion
- When a worker is `completed`, read its `result` summary.
- Verify the worker's output when stakes are high:
  - Re-run the tests yourself.
  - Inspect the diffs (e.g., `git diff <branch>` or read changed files directly).
  - Spot-check claimed file paths actually exist.
- Integrate verified findings into the broader project state.

### 4. Handling Blockers (`needs_help` or `failed`)

**If `needs_help`**:
- Read the `result` JSON to understand the blocker. Look at `reason` and `context`.
- Investigate the blocker yourself. Fix architectural issues, supply missing context, or correct the codebase.
- Once unblocked, either spawn a *new* worker with an updated objective that references prior partial work, or finish the task yourself.

**If `failed`**:
- Inspect logs and the `background_tasks` history.
- Determine whether the failure was transient (network, dependency install) or structural (objective was ambiguous, environment was wrong).
- Fix the underlying issue before retrying. Do not blindly respawn the same objective — it will fail again.

### 5. Merging Multi-Worker Results
- Compare the file changes across workers. Resolve conflicts manually.
- Run the project's full test suite after merging, not just each worker's per-file tests.
- Run any cross-cutting checks: lint, type-check, integration tests.

---

## Expected Outcome

By adhering to this orchestration pattern, you act as a 10x Engineer leading a virtual team. You effectively distribute work, monitor progress asynchronously, and intervene only when your expert architectural guidance is required.
