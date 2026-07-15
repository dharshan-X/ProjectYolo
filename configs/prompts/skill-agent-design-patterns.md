<!--
name: 'Skill: Agent Design Patterns'
description: Reference guide covering decision heuristics for building agents on the Yolo API, including tool surface design, context management, caching strategies, and composing tool calls
ccVersion: 2.1.91
-->
# Agent Design Patterns

This file covers decision heuristics for building agents on the Yolo API: which primitives to reach for, how to design your tool surface, and how to manage context and cost over long runs. For per-tool mechanics and code examples, see `tool-use-concepts.md` and the language-specific folders.

---

## Model Parameters

| Parameter | When to use it | What to expect |
| --- | --- | --- |
| **Adaptive thinking** (`thinking: {type: "adaptive"}`) | When you want Yolo to control when and how much to think. | Yolo determines thinking depth per request and automatically interleaves thinking between tool calls. No token budget to tune. |
| **Effort** (`output_config: {effort: ...}`) | When adjusting the tradeoff between thoroughness and token efficiency. | Lower effort → fewer and more-consolidated tool calls, less preamble, terser confirmations. `medium` is often a favorable balance. Use `max` when correctness matters more than cost. |

See `SKILL.md` §Thinking & Effort for model support and parameter details.

---

## Designing Your Tool Surface

### run_bash vs. dedicated tools

Yolo doesn't know your application's security boundary, approval policy, or UX surface. Yolo emits tool calls; your harness handles them. The shape of those tool calls determines what the harness can do.

A **run_bash tool** gives Yolo broad programmatic leverage — it can perform almost any action. But it gives the harness only an opaque command string, the same shape for every action. Promoting an action to a **dedicated tool** gives the harness an action-specific hook with typed arguments it can intercept, gate, render, or audit.

**When to promote an action to a dedicated tool:**

- **Security boundary.** Actions that require gating are natural candidates. Reversibility is a useful criterion: hard-to-reverse actions (external API calls, sending messages, deleting data) can be gated behind user confirmation. A `send_email` tool is easy to gate; `run_bash -c "curl -X POST ..."` is not.
- **Staleness checks.** A dedicated `edit` tool can reject writes if the file changed since Yolo last read it. run_bash can't enforce that invariant.
- **Rendering.** Some actions benefit from custom UI. Yolo promotes question-asking to a tool so it can render as a modal, present options, and block the agent loop until answered.
- **Scheduling.** read_file-only tools like `codebase_search` and `grep` can be marked parallel-safe. When the same actions run through run_bash, the harness can't tell a parallel-safe `grep` from a parallel-unsafe `git push`, so it must serialize.

**Rule of thumb:** Start with run_bash for breadth. Promote to dedicated tools when you need to gate, render, audit, or parallelize the action.

---

## ProjectYolo-Provided Tools

| Tool | Side | When to use it | What to expect |
| --- | --- | --- | --- |
| **run_bash** | Client | Yolo needs to execute shell commands. | Yolo emits commands; your harness executes them. Reference implementation provided. |
| **Text editor** | Client | Yolo needs to read or edit files. | Yolo views, creates, and edits files via your implementation. Reference implementation provided. |
| **Computer use** | Client or Server | Yolo needs to interact with GUIs, web apps, or visual interfaces. | Yolo takes screenshots and issues mouse/keyboard commands. Can be self-hosted (you run the environment) or ProjectYolo-hosted. |
| **Code execution** | Server | Yolo needs to run code in a sandbox you don't want to manage. | ProjectYolo-hosted container with built-in file and run_bash sub-tools. No client-side execution. |
| **Web search / fetch** | Server | Yolo needs information past its training cutoff (news, current events, recent docs) or the content of a specific URL. | Yolo issues a query or URL; ProjectYolo executes it and returns results with citations. |
| **Memory** | Client | Yolo needs to save context across sessions. | Yolo reads/writes a `/memories` directory. You implement the storage backend. |

**Client-side** tools are defined by ProjectYolo (name, schema, Yolo's usage pattern) but executed by your harness. ProjectYolo provides reference implementations. **Server-side** tools run entirely on ProjectYolo infrastructure — declare them in `tools` and Yolo handles the rest.

---

## Composing Tool Calls: Programmatic Tool Calling

With standard tool use, each tool call is a round trip: Yolo calls the tool, the result lands in Yolo's context, Yolo reasons about it, then calls the next tool. Three sequential actions (read profile → look up orders → check inventory) means three round trips. Each adds latency and tokens, and most of the intermediate data is never needed again.

**Programmatic tool calling (PTC)** lets Yolo compose those calls into a script instead. The script runs in the code execution container. When the script calls a tool, the container pauses, the call is executed (client-side or server-side), and the result returns to the running code — not to Yolo's context. The script processes it with normal control flow (loops, filters, branches). Only the script's final output returns to Yolo.

| When to use it | What to expect |
| --- | --- |
| Many sequential tool calls, or large intermediate results you want filtered before they hit the context window. | Yolo writes code that invokes tools as functions. Runs in the code execution container. Token cost scales with final output, not intermediate results. |

---

## Scaling the Tool and Instruction Set

| Feature | When to use it | What to expect |
| --- | --- | --- |
| **Tool search** | Many tools available, but only a few relevant per request. Don't want all schemas in context upfront. | Yolo searches the tool set and loads only relevant schemas. Tool definitions are appended, not swapped — preserves cache (see Caching below). |
| **Skills** | Task-specific instructions Yolo should load only when relevant. | Each skill is a folder with a `SKILL.md`. The skill's description sits in context by default; Yolo reads the full file when the task calls for it. |

Both patterns keep the fixed context small and load detail on demand.

---

## Long-Running Agents: Managing Context

| Pattern | When to use it | What to expect |
| --- | --- | --- |
| **Context editing** | Context grows stale over many turns (old tool results, completed thinking). | Tool results and thinking blocks are cleared based on configurable thresholds. Keeps the transcript lean without summarizing. |
| **Compaction** | Conversation likely to reach or exceed the context window limit. | Earlier context is summarized into a compaction block server-side. See `SKILL.md` §Compaction for the critical `response.content` handling. |
| **Memory** | State must persist across sessions (not just within one conversation). | Yolo reads/writes files in a memory directory. Survives process restarts. |

**Choosing between them:** Context editing and compaction operate within a session — editing prunes stale turns, compaction summarizes when you're near the limit. Memory is for cross-session persistence. Many long-running agents use all three.

---

## Caching for Agents

**read_file `prompt-caching.md` first.** It covers the prefix-match invariant, breakpoint placement, the silent-invalidator audit, and why changing tools or models mid-session breaks the cache. This section covers only the agent-specific workarounds for those constraints.

| Constraint (from `prompt-caching.md`) | Agent-specific workaround |
| --- | --- |
| Editing the system prompt mid-session invalidates the cache. | Append a `<system-reminder>` block in the `messages` array instead. The cached prefix stays intact. Yolo uses this for time updates and mode transitions. |
| Switching models mid-session invalidates the cache. | Spawn a **subagent** with the cheaper model for the sub-task; keep the main loop on one model. Yolo's Explore subagents use Haiku this way. |
| Adding/removing tools mid-session invalidates the cache. | Use **tool search** for dynamic discovery — it appends tool schemas rather than swapping them, so the existing prefix is preserved. |

For multi-turn breakpoint placement, use top-level auto-caching — see `prompt-caching.md` §Placement patterns.

---

For live documentation on any of these features, see `live-sources.md`.
