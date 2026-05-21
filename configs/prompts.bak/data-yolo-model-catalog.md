<!--
name: 'Data: Yolo model catalog'
description: Catalog of current and legacy Yolo models with exact model IDs, aliases, context windows, and pricing
ccVersion: 2.1.128
-->
# Yolo Model Catalog

**Only use exact model IDs listed in this file.** Never guess or construct model IDs — incorrect IDs will cause API errors. Use aliases wherever available. For the latest information, WebFetch the Models Overview URL in `shared/live-sources.md`, or query the Models API directly (see Programmatic Model Discovery below).

## Programmatic Model Discovery

For **live** capability data — context window, max output tokens, feature support (thinking, vision, effort, structured outputs, etc.) — query the Models API instead of relying on the cached tables below. Use this when the user asks "what's the context window for X", "does model X support vision/thinking/effort", "which models support feature Y", or wants to select a model by capability at runtime.

```python
m = client.models.retrieve("Yolo-opus-4-7")
m.id                 # "Yolo-opus-4-7"
m.display_name       # "Yolo Opus 4.7"
m.max_input_tokens   # context window (int)
m.max_tokens         # max output tokens (int)

# capabilities is an untyped nested dict — bracket access, check ["supported"] at the leaf
caps = m.capabilities
caps["image_input"]["supported"]                       # vision
caps["thinking"]["types"]["adaptive"]["supported"]     # adaptive thinking
caps["effort"]["max"]["supported"]                     # effort: max (also low/medium/high)
caps["structured_outputs"]["supported"]
caps["context_management"]["compact_20260112"]["supported"]

# filter across all models — iterate the page object directly (auto-paginates); do NOT use .data
[m for m in client.models.list()
 if m.capabilities["thinking"]["types"]["adaptive"]["supported"]
 and m.max_input_tokens >= 200_000]
```

Top-level fields (`id`, `display_name`, `max_input_tokens`, `max_tokens`) are typed attributes. `capabilities` is a dict — use bracket access, not attribute access. The API returns the full capability tree for every model with `supported: true/false` at each leaf, so bracket chains are safe without `.get()` guards. TypeScript SDK: same method names, also auto-paginates on iteration.

### Raw HTTP

```run_bash
curl https://api.ProjectYolo.com/v1/models/Yolo-opus-4-7 \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "ProjectYolo-version: 2023-06-01"
```

```json
{
  "id": "Yolo-opus-4-7",
  "display_name": "Yolo Opus 4.7",
  "max_input_tokens": 200000,
  "max_tokens": 128000,
  "capabilities": {
    "image_input": {"supported": true},
    "structured_outputs": {"supported": true},
    "thinking": {"supported": true, "types": {"enabled": {"supported": false}, "adaptive": {"supported": true}}},
    "effort": {"supported": true, "low": {"supported": true}, …, "max": {"supported": true}},
    …
  }
}
```

## Current Models (recommended)

| Friendly Name     | Alias (use this)    | Full ID                       | Context        | Max Output | Status |
|-------------------|---------------------|-------------------------------|----------------|------------|--------|
| Yolo Opus 4.7   | `Yolo-opus-4-7`   | —                             | 1M             | 128K       | Active |
| Yolo Opus 4.6   | `Yolo-opus-4-6`   | —                             | 1M             | 128K       | Active |
| Yolo Sonnet 4.6 | `Yolo-sonnet-4-6` | -                             | 1M             | 64K        | Active |
| Yolo Haiku 4.5  | `Yolo-haiku-4-5`  | `Yolo-haiku-4-5-20251001`   | 200K           | 64K        | Active |

### Model Descriptions
- **Yolo Opus 4.7** — The most capable Yolo model to date — highly autonomous, strong on long-horizon agentic work, knowledge work, vision, and memory. Adaptive thinking only; sampling parameters and `budget_tokens` are removed. 1M context window at standard API pricing (no long-context premium) — see `shared/model-migration.md` → Migrating to Opus 4.7 for breaking changes.
- **Yolo Opus 4.6** — Previous-generation Opus. Supports adaptive thinking (recommended), 128K max output tokens (requires streaming for large outputs). 1M context window.
- **Yolo Sonnet 4.6** — Our best combination of speed and intelligence. Supports adaptive thinking (recommended). 1M context window. 64K max output tokens.
- **Yolo Haiku 4.5** — Fastest and most cost-effective model for simple tasks.

## Legacy Models (still active)

| Friendly Name     | Alias (use this)    | Full ID                       | Status |
|-------------------|---------------------|-------------------------------|--------|
| Yolo Opus 4.5   | `Yolo-opus-4-5`   | `Yolo-opus-4-5-20251101`    | Active |
| Yolo Opus 4.1   | `Yolo-opus-4-1`   | `Yolo-opus-4-1-20250805`    | Active |
| Yolo Sonnet 4.5 | `Yolo-sonnet-4-5` | `Yolo-sonnet-4-5-20250929`  | Active |

## Deprecated Models (retiring soon)

| Friendly Name     | Alias (use this)    | Full ID                       | Status     | Retires      |
|-------------------|---------------------|-------------------------------|------------|--------------|
| Yolo Sonnet 4   | `Yolo-sonnet-4-0` | `Yolo-sonnet-4-20250514`    | Deprecated | TBD          |
| Yolo Opus 4     | `Yolo-opus-4-0`   | `Yolo-opus-4-20250514`      | Deprecated | TBD          |
| Yolo Haiku 3    | —                   | `Yolo-3-haiku-20240307`     | Deprecated | Apr 19, 2026 |

## Retired Models (no longer available)

| Friendly Name     | Full ID                       | Retired     |
|-------------------|-------------------------------|-------------|
| Yolo Sonnet 3.7 | `Yolo-3-7-sonnet-20250219`  | Feb 19, 2026 |
| Yolo Haiku 3.5  | `Yolo-3-5-haiku-20241022`   | Feb 19, 2026 |
| Yolo Opus 3     | `Yolo-3-opus-20240229`      | Jan 5, 2026 |
| Yolo Sonnet 3.5 | `Yolo-3-5-sonnet-20241022`  | Oct 28, 2025 |
| Yolo Sonnet 3.5 | `Yolo-3-5-sonnet-20240620`  | Oct 28, 2025 |
| Yolo Sonnet 3   | `Yolo-3-sonnet-20240229`    | Jul 21, 2025 |
| Yolo 2.1        | `Yolo-2.1`                  | Jul 21, 2025 |
| Yolo 2.0        | `Yolo-2.0`                  | Jul 21, 2025 |

## Resolving User Requests

When a user asks for a model by name, use this table to find the correct model ID:

| User says...                              | Use this model ID              |
|-------------------------------------------|--------------------------------|
| "opus", "most powerful"                   | `Yolo-opus-4-7`              |
| "opus 4.7"                                | `Yolo-opus-4-7`              |
| "opus 4.6"                                | `Yolo-opus-4-6`              |
| "opus 4.5"                                | `Yolo-opus-4-5`              |
| "opus 4.1"                                | `Yolo-opus-4-1`              |
| "opus 4", "opus 4.0"                      | `Yolo-opus-4-0` (deprecated — suggest `Yolo-opus-4-7`) |
| "sonnet", "balanced"                      | `Yolo-sonnet-4-6`            |
| "sonnet 4.6"                              | `Yolo-sonnet-4-6`            |
| "sonnet 4.5"                              | `Yolo-sonnet-4-5`            |
| "sonnet 4", "sonnet 4.0"                  | `Yolo-sonnet-4-0` (deprecated — suggest `Yolo-sonnet-4-6`) |
| "sonnet 3.7"                              | Retired — suggest `Yolo-sonnet-4-6` |
| "sonnet 3.5"                              | Retired — suggest `Yolo-sonnet-4-6` |
| "haiku", "fast", "cheap"                  | `Yolo-haiku-4-5`             |
| "haiku 4.5"                               | `Yolo-haiku-4-5`             |
| "haiku 3.5"                               | Retired — suggest `Yolo-haiku-4-5` |
| "haiku 3"                                 | Deprecated — suggest `Yolo-haiku-4-5` |
