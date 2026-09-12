from tools.registry import register_tool
import httpx
from bs4 import BeautifulSoup  # type: ignore
from duckduckgo_search import DDGS
from tools.base import audit_log

MAX_BROWSE_TEXT_CHARS = 8000


def _search_bing(query: str, max_results: int = 8) -> list[str]:
    """Search Bing for real-time web results."""
    import urllib.parse
    results = []
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(follow_redirects=True, timeout=12.0, verify=False) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for li in soup.select("li.b_algo"):
                h2 = li.select_one("h2 a")
                snip = li.select_one(".b_caption p") or li.select_one(".b_lineclamp2") or li.select_one("p")
                if h2:
                    title = h2.get_text(strip=True)
                    link = h2.get("href", "")
                    snippet = snip.get_text(strip=True) if snip else ""
                    if title and link:
                        results.append(f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n")
                if len(results) >= max_results:
                    break
    return results


def _search_ddg(query: str, max_results: int = 8) -> list[str]:
    """Search DuckDuckGo."""
    results = []
    with DDGS(timeout=15) as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n")
    return results


def _search_wikipedia(query: str, max_results: int = 5) -> list[str]:
    """Search Wikipedia API for encyclopedia entries."""
    import urllib.request, urllib.parse, json
    results = []
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        items = data.get("query", {}).get("search", [])[:max_results]
        for it in items:
            clean_snippet = BeautifulSoup(it.get("snippet", ""), "html.parser").get_text()
            title = it.get("title", "")
            results.append(f"Title: {title}\nURL: https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}\nSnippet: {clean_snippet}\n")
    return results


@register_tool()
def web_search(query: str) -> str:
    """Search the internet for real-time information."""
    # 1. Primary: Bing (fast, real-time news & web indexing, reliable)
    try:
        results = _search_bing(query, max_results=8)
        if results:
            audit_log("web_search", {"query": query}, "success", "bing")
            return "\n".join(results)
    except Exception as e:
        audit_log("web_search", {"query": query}, "warning", f"Bing error: {e}")

    # 2. Secondary: DuckDuckGo
    try:
        results = _search_ddg(query, max_results=8)
        if results:
            audit_log("web_search", {"query": query}, "success", "ddg")
            return "\n".join(results)
    except Exception as e:
        audit_log("web_search", {"query": query}, "warning", f"DDG error: {e}")

    # 3. Tertiary: Wikipedia
    try:
        results = _search_wikipedia(query, max_results=5)
        if results:
            audit_log("web_search", {"query": query}, "success", "wikipedia")
            return "\n".join(results)
    except Exception as exc:
        audit_log("web_search", {"query": query}, "error", f"Wikipedia error: {exc}")

    return f"No search results found for query: {query}"


@register_tool()
def browse_url(url: str) -> str:
    """Fetch and extract text content from a specific URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
            script_or_style.extract()

        text = soup.get_text(separator="\n")
        lines = (line.strip() for line in text.splitlines())
        clean_text = "\n".join(line for line in lines if line)

        result = clean_text[:MAX_BROWSE_TEXT_CHARS]
        audit_log("browse_url", {"url": url}, "success")
        return result
    except Exception as e:
        audit_log("browse_url", {"url": url}, "error", str(e))
        return f"Error browsing URL: {e}. Suggestion: Use `browser_navigate` for a visual session if this fetch failed."
