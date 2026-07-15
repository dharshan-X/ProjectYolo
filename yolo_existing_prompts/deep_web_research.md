# Skill: Deep Web Research

A disciplined, memory-bounded procedure for conducting extensive multi-source research using the visual browser. Optimizes for **signal density**, not page count.

---

## Core Principles

- **Breadth, then depth**: Cast a wide net of candidate URLs up front, then dive selectively. Avoid the trap of over-crawling one source while ignoring others.
- **Summarize and discard**: Persistent truth lives on disk (via `research_store_summary`). In-message history only holds the *current* site's findings.
- **Deduplicate aggressively**: If two sources reach the same conclusion, log the conclusion with both citations — do not write two parallel summaries.
- **Respect hosts**: Honor `robots.txt` where feasible. Use sensible rate limits. Do not perform malicious scraping or authentication bypass.

---

## Procedure

### 1. Search Initiation
- Use `browser_navigate` to open a major search engine (Google, Bing, DuckDuckGo).
- Formulate the query to be specific — include version numbers, library names, or date constraints when relevant.

### 2. Execution
- Use `browser_type` to enter the query, submit, and wait for results.
- If the SERP itself is paginated, follow pagination until results begin to repeat.

### 3. Queueing
- Identify **20–50 high-signal candidate links**. Prefer:
  - Official documentation and specs.
  - Reputable engineering blogs and conference talks.
  - Recent (last 24 months) discussions, GitHub issues, or RFCs.
- De-prioritize: SEO farms, content scrapers, broken domains, social posts without substance.
- Use `research_queue_urls` to persist the queue. Save the queue to disk so a retry can resume it.

### 4. Stateful Loop
For each URL:

1. Use `research_get_next` to pop the next URL.
2. `browser_navigate` to load it. If the request times out, retry once with a longer timeout; on second failure, log and skip.
3. **If content is paginated or lazy-loaded**:
   - Prefer `browser_crawl_step` to perform scroll + link extraction + optional next click in one call.
   - Prefer `research_enqueue_from_crawl_step` to parse crawl output and queue only high-signal links.
   - As a fallback, use `browser_scroll_until_end`, `browser_scroll`, `browser_click_next`, and `browser_extract_links` individually.
   - Feed newly discovered URLs into `research_queue_urls` for downstream visits.
4. Use `browser_extract_text` to read the visible content. If the page is enormous (>50k tokens), extract only the relevant section.
5. **CRITICAL**: Call `research_store_summary` with a **concise, source-grounded summary** (200–500 words). Include:
   - The source URL and publication date (if visible).
   - The 2–5 most important claims or facts.
   - A direct attribution to where each claim was found (e.g., "From section 'Migration Guide'" or "From code block at line 142").
   - Any verbatim quotes ≤15 words long, clearly marked as quotes.
6. **Memory discipline**: After storing, proceed immediately. Do not keep the previous site's full text in your message history.

### 5. Synthesis
When the queue empties or the goal is satisfied:
- Call `research_get_all_summaries` to retrieve every persisted summary.
- Cross-reference claims: where multiple sources agree, restate with confidence; where they disagree, flag the conflict and surface both views.
- Use `create_artifact` to generate the final report as a `markdown` artifact with these sections:
  1. **Executive Summary** (≤200 words)
  2. **Key Findings** (numbered, sourced)
  3. **Conflicts & Open Questions**
  4. **Source Index** (URL — short label — date accessed)

---

## Source Credibility Heuristics

When ranking sources, apply these tiers:

| Tier | Examples | Weight |
|---|---|---|
| Primary | Official docs, RFCs, source code, peer-reviewed papers | Highest |
| Trusted secondary | Recognized engineering blogs, conference videos, maintainer commentary | High |
| Community | Stack Overflow accepted answers, GitHub issues, Reddit threads | Medium — verify before citing |
| Low signal | SEO content farms, outdated forum posts, AI-generated listicles | Lowest — cite only if unavoidable |

Always prefer a primary source on first pass. Skip low-signal sources altogether unless the topic is obscure.

---

## Deduplication Rules

- If two sources agree on the same fact, write one summary entry with both citations.
- If two sources conflict, write two summary entries and explicitly flag the disagreement in synthesis.
- Skip summarizing navigation pages, ads, or boilerplate. Only persist content that advances the objective.

---

## Ethical & Safety Constraints

- Avoid infinite loops and excessive resource consumption.
- Respect `robots.txt` when practical. Add `User-Agent` headers if custom tools allow.
- Never bypass authentication walls, paywalls, or CAPTCHAs.
- Stop a crawl that exceeds your timebox. Collect what you have and synthesize.

---

## Expected Outcome

A high-quality research artifact summarizing findings from multiple verified sources, with each substantive claim attributable to a specific URL and section, conflicts surfaced explicitly, and no fabricated facts.
