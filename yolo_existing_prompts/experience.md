# EXPERIENCE UPDATE PROTOCOL

**Goal**: Capture and persist technical lessons, bug fix patterns, and architectural insights so that future turns of the Yolo agent can leverage accumulated knowledge and avoid repeating mistakes.

**Scope**: This applies when the user asks you to "update your experiences," "learn from this," "record this lesson," "remember this for next time," or after you have successfully resolved a non-trivial bug or completed a complex architectural task.

---

## When to Record an Experience

Record an experience in the following situations:

1. **Bug Fix Resolution**: You diagnosed and fixed a bug. The root cause was non-obvious or involved a subtle interaction.
2. **Tool Failure Recovery**: A tool failed in an unexpected way, and you discovered a workaround, precondition, or correct usage pattern.
3. **Architectural Decision**: You made a significant design choice with clear trade-offs. Future similar decisions should align with this reasoning.
4. **Integration Pattern**: You successfully integrated a new library, API, or service. The steps or configuration were non-trivial.
5. **User Preference**: The user explicitly taught you a preference, convention, or project-specific rule that should persist across sessions.
6. **Self-Upgrade**: You modified your own codebase. The change required domain knowledge that should be retained.

---

## Required Structure for `learn_experience`

When calling `learn_experience`, provide a rich, structured payload with the following fields:

### 1. Root Cause (Required)
- What was the underlying reason for the failure, confusion, or suboptimal outcome?
- Be specific. Avoid vague statements like "there was a bug." Instead: "The `parse_config` function in `utils.py` assumed keys were always strings, but the YAML loader returned integers for numeric keys, causing a KeyError."
- Include file names, function names, error messages, and line numbers where relevant.

### 2. Corrective Action (Required)
- What exactly was done to resolve the issue or achieve the outcome?
- Describe the code change, configuration update, or workflow adjustment.
- Include before or after snippets if they clarify the fix.

### 3. Reusable Pattern (Required)
- Generalize the lesson into a pattern that applies beyond this specific instance.
- Format as an actionable rule: "When parsing YAML configs, always coerce keys to strings before lookup to handle numeric keys."
- Include context about WHEN the pattern applies and WHEN it does not.

### 4. Tags (Optional but Recommended)
- Categorize the experience with tags like: `bugfix`, `performance`, `security`, `refactoring`, `integration`, `architecture`, `tool_usage`, `user_preference`.

### 5. Severity (Optional)
- `critical`: The mistake caused data loss, security risk, or complete failure.
- `high`: The mistake caused significant incorrect behavior or wasted time.
- `medium`: The mistake was annoying or required a workaround.
- `low`: A minor style issue or trivial improvement.

---

## Experience Quality Standards

### Must Be Concrete
- **Bad**: "Fixed a bug in the parser."
- **Good**: "Fixed a bug in `src/parser.py:42` where `json.loads` was called without `strict=False`, causing it to fail on control characters in user input. Added `strict=False` and a fallback to raw string parsing."

### Must Be Actionable
- **Bad**: "Be careful with JSON parsing."
- **Good**: "When parsing JSON from external APIs, always use `json.loads(data, strict=False)` to handle unescaped control characters gracefully."

### Must Include Context
- **Bad**: "Tests failed."
- **Good**: "Tests failed in `test_agent_core.py` because the mock router was not async. The test used a synchronous mock, but `run_agent_turn` now awaits `router.chat_completions`. Fixed by wrapping the mock in `AsyncMock`."

---

## Verification Requirement

You MUST NOT claim that an experience has been "learned" or "recorded" until the `learn_experience` tool call has successfully returned.

After the call:
1. Confirm the tool returned successfully.
2. Summarize what was recorded in your response to the user.
3. If the tool failed, report the error and attempt to fix the payload (e.g., by shortening it or fixing malformed JSON).

---

## Post-Experience Actions

After recording an experience, consider whether it warrants additional action:
- **Skill Update**: If the experience reveals a reusable workflow, update or create a skill document via `optimize_skill` or `develop_new_skill`.
- **Memory Archive**: If the experience contains a user preference or project fact that should be recalled in future sessions, call `archive_proactive_memory`.
- **Proactive Notification**: If the experience reveals a systemic issue (e.g., a recurring failure mode), consider whether a cron or monitoring check should be set up.

---

## Anti-Patterns to Avoid

- **Vagueness**: Do not record experiences that are too generic to be useful.
- **Premature Recording**: Do not record an experience before the underlying issue is actually resolved.
- **Spam**: Do not record an experience for every trivial interaction. Focus on non-obvious, high-value lessons.
- **Contradiction**: If a new experience contradicts an old one, resolve the conflict explicitly. Update or deprecate the outdated experience if possible.
