# EXPERIENCE UPDATE PROTOCOL

**Goal**: Capture and persist technical lessons, bug-fix patterns, and architectural insights so that future turns of the Yolo agent can leverage accumulated knowledge and avoid repeating mistakes.

**Scope**: Apply when the user asks you to "update your experiences", "learn from this", "record this lesson", "remember this for next time", or after you have successfully resolved a **non-trivial** bug or completed a complex architectural task.

---

## When to Record an Experience

Record an experience in the following situations:

1. **Bug Fix Resolution** — You diagnosed and fixed a bug whose root cause was non-obvious or involved a subtle interaction.
2. **Tool Failure Recovery** — A tool failed in an unexpected way, and you discovered a workaround, precondition, or correct usage pattern.
3. **Architectural Decision** — You made a significant design choice with clear trade-offs; future similar decisions should align with this reasoning.
4. **Integration Pattern** — You successfully integrated a new library, API, or service. The steps or configuration were non-trivial.
5. **User Preference** — The user explicitly taught you a preference, convention, or project-specific rule that should persist across sessions.
6. **Self-Upgrade** — You modified your own codebase. The change required domain knowledge that should be retained.

**Do NOT record experiences for**: trivial typo fixes, routine refactors, or one-line changes whose lesson is obvious from the diff itself.

---

## Required Structure for `learn_experience`

When calling `learn_experience`, provide a rich, structured payload with the following fields:

### 1. Root Cause (required)
- What was the underlying reason for the failure, confusion, or suboptimal outcome?
- Be specific. Avoid vague statements like "there was a bug."
- **Good**: "The `parse_config` function in `utils.py` assumed keys were always strings, but the YAML loader returned integers for numeric keys, causing a `KeyError` on lookup at `utils.py:42`."
- Include file names, function names, error messages, and line numbers where relevant.

### 2. Corrective Action (required)
- What exactly was done to resolve the issue or achieve the outcome?
- Describe the code change, configuration update, or workflow adjustment.
- Include before/after snippets when they clarify the fix.

### 3. Reusable Pattern (required)
- Generalize the lesson into a pattern that applies beyond this specific instance.
- Format as an actionable rule: **"When parsing YAML configs, always coerce keys to strings before lookup to handle numeric keys."**
- Include context about *when* the pattern applies and *when* it does not.

### 4. Tags (optional but recommended)
- Categorize the experience with tags drawn from: `bugfix`, `performance`, `security`, `refactoring`, `integration`, `architecture`, `tool_usage`, `user_preference`, `testing`, `devops`.
- 2–5 tags is typical. Avoid single-tag entries that read as generic.

### 5. Severity (optional but recommended)
- `critical` — Mistake caused data loss, security risk, or complete failure.
- `high` — Mistake caused significant incorrect behavior or wasted time.
- `medium` — Mistake was annoying or required a workaround.
- `low` — Minor style issue or trivial improvement.

### 6. Retrieval Hints (new — recommended)
Add fields that help future retrieval:
- **applies_to**: a short list of contexts/files/domains where this lesson is most likely relevant (e.g., `["YAML configs", "user-provided data"]`).
- **symptom_keywords**: the error messages or visible behaviors that should trigger recall of this lesson (e.g., `["KeyError on int key"]`).
- **contradicts**: an optional identifier for an experience this one overrides. If present, the conflicting experience should be deprecated.

---

## Concrete Template

Use this template verbatim when calling `learn_experience`:

```yaml
title: "<short, descriptive>"
root_cause: |
  <specific explanation with file:line references>
corrective_action: |
  <exact change made, with before/after snippet>
reusable_pattern: |
  <generalized actionable rule with when-to-apply context>
tags: [bugfix, integration]
severity: high
applies_to: ["<domain or file patterns>"]
symptom_keywords: ["<error text or visible failure>"]
contradicts: null
```

---

## Quality Standards

### Must Be Concrete
- **Bad**: "Fixed a bug in the parser."
- **Good**: "Fixed a bug in `src/parser.py:42` where `json.loads` was called without `strict=False`, causing it to fail on control characters in user input. Added `strict=False` and a fallback to raw string parsing."

### Must Be Actionable
- **Bad**: "Be careful with JSON parsing."
- **Good**: "When parsing JSON from external APIs, always use `json.loads(data, strict=False)` to handle unescaped control characters gracefully."

### Must Include Context
- **Bad**: "Tests failed."
- **Good**: "Tests failed in `test_agent_core.py` because the mock router was not async. The test used a synchronous mock, but `run_agent_turn` now awaits `router.chat_completions`. Fixed by wrapping the mock in `AsyncMock`."

### Must Cite the Discovered Signal
- When the lesson was triggered by an error message, embed the *exact* message in `symptom_keywords`. This is what makes future retrieval work.

---

## Verification Requirement

You MUST NOT claim that an experience has been "learned" or "recorded" until the `learn_experience` tool call has **successfully returned**.

After the call:
1. Confirm the tool returned successfully (check the response object, not your assumption).
2. Summarize what was recorded in your response to the user — title, severity, and the one-line reusable pattern.
3. If the tool failed, report the error and attempt to fix the payload (shorten it, fix malformed JSON, split into two narrower experiences).

---

## Conflict Resolution

When a new experience contradicts an existing one:
1. Set the new experience's `contradicts` field to the identifier of the old one.
2. After both are persisted, prefer the **newer** experience going forward.
3. If the conflict is significant (security, correctness), mention it to the user explicitly so they can audit.
4. Avoid silently overwriting — both records should remain in the database unless explicitly deprecated via `archive_experience`.

---

## Post-Experience Actions

After recording an experience, consider whether it warrants additional action:

- **Skill Update** — If the experience reveals a reusable workflow, update or create a skill document via `optimize_skill` or `develop_new_skill`.
- **Memory Archive** — If the experience contains a user preference or project fact, call `archive_proactive_memory` so it is recalled in future sessions.
- **Proactive Monitoring** — If the experience reveals a systemic issue (a recurring failure mode), propose a cron or monitoring check.

---

## Anti-Patterns to Avoid

- **Vagueness** — Do not record experiences that are too generic to be useful.
- **Premature Recording** — Do not record an experience before the underlying issue is actually resolved and verified.
- **Spam** — Do not record an experience for every trivial interaction. Focus on non-obvious, high-value lessons.
- **Contradiction Without Resolution** — If a new experience contradicts an old one, resolve the conflict explicitly. Do not leave both versions competing in retrieval.
- **Over-Broad Applicability** — If the lesson only applies to one specific corner case, mark `applies_to` narrow. Otherwise retrieval noise will dilute useful signal.
