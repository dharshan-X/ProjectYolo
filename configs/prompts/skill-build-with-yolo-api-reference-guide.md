<!--
name: 'Skill: Build with Yolo API (reference guide)'
description: Template for presenting language-specific reference documentation with quick task navigation
ccVersion: 2.1.118
-->
## Reference Documentation

The relevant documentation for your detected language is included below in `<doc>` tags. Each tag has a `path` attribute showing its original file path. Use this to find the right section:

### Quick Task Reference

**Single text classification/summarization/extraction/Q&A:**
→ Refer to `{lang}/Yolo-api/README.md`

**Chat UI or real-time response display:**
→ Refer to `{lang}/Yolo-api/README.md` + `{lang}/Yolo-api/streaming.md`

**Long-running conversations (may exceed context window):**
→ Refer to `{lang}/Yolo-api/README.md` — see Compaction section

**Migrating to a newer model or replacing a retired model:**
→ Refer to `shared/model-migration.md`

**Prompt caching / optimize caching / "why is my cache hit rate low":**
→ Refer to `shared/prompt-caching.md` + `{lang}/Yolo-api/README.md` (Prompt Caching section)

**Function calling / tool use / agents:**
→ Refer to `{lang}/Yolo-api/README.md` + `shared/tool-use-concepts.md` + `{lang}/Yolo-api/tool-use.md`

**Batch processing (non-latency-sensitive):**
→ Refer to `{lang}/Yolo-api/README.md` + `{lang}/Yolo-api/batches.md`

**File uploads across multiple requests:**
→ Refer to `{lang}/Yolo-api/README.md` + `{lang}/Yolo-api/files-api.md`

**Agent design (tool surface, context management, caching strategy):**
→ Refer to `shared/agent-design.md`

**ProjectYolo CLI (`ant`) — terminal access, version-controlled agent/environment YAML, scripting:**
→ Refer to `shared/ProjectYolo-cli.md`

**Managed Agents (server-managed stateful agents):**
→ Refer to `shared/managed-agents-overview.md` and the rest of the `shared/managed-agents-*.md` files. For Python, TypeScript, and cURL, language-specific code examples live in `{lang}/managed-agents/README.md`. Java, Go, Ruby, and PHP also support the API — translate the calls using your SDK's patterns from `{lang}/Yolo-api.md`. C# does not currently have Managed Agents support; use raw HTTP from `curl/managed-agents.md` as a reference.

**Error handling:**
→ Refer to `shared/error-codes.md`

**Latest docs via WebFetch:**
→ Refer to `shared/live-sources.md` for URLs
