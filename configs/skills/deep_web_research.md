## Elite Epistemic Deep Web Research Skill

### Cognitive Procedure
1.  **Hypothesis Generation**: Before searching, define what specific high-value information you need to extract.
2.  **Advanced Querying**: Use `browser_navigate` and `browser_type` with advanced search operators (e.g., `site:`, `filetype:`, `"exact phrase"`) to bypass low-quality SEO spam.
3.  **High-Signal Queuing**: Use `research_enqueue_from_crawl_step` to identify only top-tier sources (academic papers, official docs, elite engineering blogs). Reject generic content.
4.  **Deep Extraction Loop**:
    *   `research_get_next` → target URL.
    *   `browser_navigate` → load DOM. Use `gui_scroll_screen` to trigger lazy loading if needed.
    *   `browser_extract_text` → parse DOM.
    *   **Counter-Factual Validation**: Cross-reference the extracted text internally. Does it contradict known facts?
    *   `research_store_summary` → distill the absolute essence of the finding into dense, high-signal technical memory.
5.  **Synthesis & Architecture**: Use `research_get_all_summaries` to combine the raw intelligence into a master artifact. The final report must not just summarize—it must propose new architectures, novel insights, and actionable code paths based on the research.