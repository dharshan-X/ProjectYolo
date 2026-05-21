# Skill: Deep Web Research
This skill provides a methodical procedure for conducting extensive research using the visual browser.

## Procedure
1. **Search Initiation**: Use `browser_navigate` to go to a major search engine (Google/Bing).
2. **Execution**: Use `browser_type` to search for the query.
3. **Queueing**: Identify 20-50 relevant links. Use `research_queue_urls` to store them in the persistent state.
4. **Stateful Loop**:
   - Use `research_get_next` to fetch the next URL from the queue.
   - Use `browser_navigate` to visit the site.
   - If content is paginated or lazy-loaded:
     - Prefer `browser_crawl_step` to perform scroll + link extraction + optional next click in one call.
     - Prefer `research_enqueue_from_crawl_step` to parse crawl output and queue only high-signal links.
     - If needed, use `browser_scroll_until_end`, `browser_scroll`, `browser_click_next`, and `browser_extract_links` individually.
     - Feed newly found result URLs back into `research_queue_urls`.
   - Use `browser_extract_text` to read the currently visible content.
   - **CRITICAL**: Use `research_store_summary` to save a concise version of the findings to disk.
   - **Memory Management**: Once the summary is stored, proceed to the next URL. Do NOT keep the full text of previous sites in your message history.
5. **Synthesis**: When the queue is empty or the goal is met, use `research_get_all_summaries` to retrieve all findings and `create_artifact` to generate the final report.

## Ethical Note
Avoid infinite loops and excessive resource consumption. Respect `robots.txt` when possible and do not perform malicious scraping.

## Expected Outcome
A high-quality Research Artifact summarizing findings from dozens of verified sources.
