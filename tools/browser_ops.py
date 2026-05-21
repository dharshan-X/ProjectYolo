from tools.registry import register_tool
import asyncio
import contextlib
import json
import os
import random
from pathlib import Path
from urllib.parse import urljoin, urlparse

from camoufox.async_api import AsyncCamoufox

from tools.base import YOLO_ARTIFACTS, YOLO_BROWSER_PROFILE, audit_log

# Persistent browser state
_browser_context = None
_browser_exit_stack = None
_page_instance = None
_lock = None

def _get_lock():
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock

# Profile path
BROWSER_PROFILE_DIR = YOLO_BROWSER_PROFILE


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_camoufox_headless_value():
    raw = os.getenv("CAMOUFOX_HEADLESS", "true").strip().lower()
    if raw in {"virtual", "xvfb"}:
        return "virtual"
    return raw in {"1", "true", "yes", "on"}


def _get_camoufox_os_value():
    raw = os.getenv("CAMOUFOX_OS", "").strip()
    if not raw:
        return None
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return parts


CAMOUFOX_HUMANIZE = _get_bool_env("CAMOUFOX_HUMANIZE", True)
CAMOUFOX_BLOCK_IMAGES = _get_bool_env("CAMOUFOX_BLOCK_IMAGES", False)


async def _human_mouse_move(page, target_x, target_y):
    """Simulate human-like mouse movement.

    Performance: previously this issued 10-20 separate `page.mouse.move(...)`
    calls plus one initial `page.evaluate(...)` to estimate the start point.
    Each round-trip adds ~10-50ms, so a single click could spend 0.5-2s
    purely on IPC. This version generates the full path locally and dispatches
    the moves in a single `page.evaluate` round-trip via CDP-equivalent
    DOM events, falling back to a small batch of `mouse.move` calls if needed.
    """
    steps = random.randint(10, 20)
    # Generate the entire path locally (no IPC during generation).
    points = []
    # We do not actually know the current cursor position; the original code
    # estimated it as the viewport center. Keep the same heuristic but with
    # a single evaluate call to fetch viewport size only when needed.
    try:
        viewport = await page.evaluate(
            "() => ({x: window.innerWidth/2, y: window.innerHeight/2})"
        )
        start_x, start_y = viewport["x"], viewport["y"]
    except Exception:
        start_x, start_y = target_x, target_y

    for i in range(steps):
        percentage = (i + 1) / steps
        sx = start_x + (target_x - start_x) * percentage + random.uniform(-3, 3)
        sy = start_y + (target_y - start_y) * percentage + random.uniform(-3, 3)
        points.append((sx, sy))

    # Dispatch as a single batched move via Playwright's mouse.move steps API,
    # which interpolates server-side without per-step Python<->browser IPC.
    try:
        # Move to first point quickly, then to final with steps=N for smoothing.
        first_x, first_y = points[0]
        last_x, last_y = points[-1]
        await page.mouse.move(first_x, first_y)
        # `steps` causes Playwright to interpolate server-side, one IPC call.
        await page.mouse.move(last_x, last_y, steps=max(1, steps - 1))
    except Exception:
        # Fallback: original per-step approach if `steps=` is unsupported.
        for sx, sy in points:
            await page.mouse.move(sx, sy)
            await asyncio.sleep(random.uniform(0.005, 0.015))
    # One small post-move settle delay (replaces N micro-sleeps).
    await asyncio.sleep(random.uniform(0.05, 0.12))


async def _get_page():
    """Internal helper to manage the persistent Camoufox browser context."""
    global _browser_context, _browser_exit_stack, _page_instance
    async with _get_lock():
        if _page_instance is None:
            launch_options = {
                "persistent_context": True,
                "user_data_dir": str(BROWSER_PROFILE_DIR),
                "headless": _get_camoufox_headless_value(),
                "humanize": CAMOUFOX_HUMANIZE,
                "block_images": CAMOUFOX_BLOCK_IMAGES,
            }
            camoufox_os = _get_camoufox_os_value()
            if camoufox_os is not None:
                launch_options["os"] = camoufox_os

            _browser_exit_stack = contextlib.AsyncExitStack()
            _browser_context = await _browser_exit_stack.enter_async_context(
                AsyncCamoufox(**launch_options)
            )

            if _browser_context.pages:
                _page_instance = _browser_context.pages[0]
            else:
                _page_instance = await _browser_context.new_page()
            audit_log(
                "browser_start",
                {
                    "headless": str(launch_options.get("headless")),
                    "humanize": launch_options.get("humanize"),
                    "block_images": launch_options.get("block_images"),
                    "os": launch_options.get("os"),
                },
                "success",
            )
        return _page_instance


@register_tool()
async def browser_navigate(url: str) -> str:
    """Navigate with improved wait conditions and CAPTCHA detection."""
    try:
        page = await _get_page()
        await asyncio.sleep(random.uniform(1.5, 3.0))
        response = await page.goto(url, wait_until="load", timeout=60000)
        if not response:
            return f"Error: Navigation to `{url}` failed."
        await asyncio.sleep(random.uniform(2.0, 4.0))
        title = await page.title()
        audit_log(
            "browser_navigate", {"url": url, "status": response.status}, "success"
        )
        content = await page.content()
        if any(
            term in content.lower()
            for term in ["captcha", "verify you are human", "unusual traffic"]
        ):
            return f"FAILURE: CAPTCHA detected on `{url}`. Try `browser_click_at` manually."
        return f"Successfully navigated to `{url}`. Title: `{title}`."
    except Exception as e:
        audit_log("browser_navigate", {"url": url}, "error", str(e))
        return f"Error navigating to URL: {e}"


@register_tool()
async def browser_click(selector: str) -> str:
    """Click an element with simulated human noise and jitter."""
    try:
        page = await _get_page()
        try:
            await page.wait_for_selector(selector, state="visible", timeout=5000)
            element = page.locator(selector).first
            box = await element.bounding_box()
            if box:
                # Add human jitter within the element bounds (±2 pixels from center)
                center_x = box["x"] + box["width"] / 2 + random.uniform(-2, 2)
                center_y = box["y"] + box["height"] / 2 + random.uniform(-2, 2)

                await _human_mouse_move(page, center_x, center_y)
                await asyncio.sleep(random.uniform(0.1, 0.4))
                await page.mouse.click(center_x, center_y)

                audit_log("browser_click", {"selector": selector}, "success")
                return f"Successfully clicked `{selector}` with human noise."
            else:
                # Fallback to standard click if no box
                await page.click(selector)
                return f"Successfully clicked `{selector}`."
        except Exception:
            raise
    except Exception as e:
        audit_log("browser_click", {"selector": selector}, "error", str(e))
        return f"Error clicking element: {e}"


@register_tool()
async def browser_click_at(x: int, y: int) -> str:
    """Click at coordinates with human jitter."""
    try:
        page = await _get_page()
        # Add slight organic jitter
        jx = x + random.uniform(-1, 1)
        jy = y + random.uniform(-1, 1)

        await _human_mouse_move(page, jx, jy)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.mouse.click(jx, jy)

        audit_log("browser_click_at", {"x": x, "y": y}, "success")
        return f"Successfully clicked at `({x}, {y})` with organic jitter."
    except Exception as e:
        audit_log("browser_click_at", {"x": x, "y": y}, "error", str(e))
        return f"Error: {e}"


@register_tool()
async def browser_press_key(key: str) -> str:
    """Press a specific keyboard key (e.g., 'Enter', 'Tab', 'Escape', 'ArrowDown')."""
    try:
        page = await _get_page()
        await page.keyboard.press(key)
        audit_log("browser_press_key", {"key": key}, "success")
        return f"Successfully pressed key: `{key}`."
    except Exception as e:
        audit_log("browser_press_key", {"key": key}, "error", str(e))
        return f"Error pressing key: {e}"


@register_tool()
async def browser_scroll(
    direction: str = "down",
    pixels: int = 1200,
    steps: int = 5,
    delay_seconds: float = 0.35,
) -> str:
    """Scroll page in human-like bursts to load deeper content."""
    direction = direction.lower().strip()
    if direction not in {"down", "up"}:
        return "Error: `direction` must be either `down` or `up`."
    if pixels <= 0:
        return "Error: `pixels` must be greater than 0."
    if steps <= 0:
        return "Error: `steps` must be greater than 0."
    if delay_seconds < 0:
        return "Error: `delay_seconds` must be >= 0."

    try:
        page = await _get_page()
        delta = pixels if direction == "down" else -pixels
        for _ in range(steps):
            jitter = random.randint(-80, 80)
            await page.mouse.wheel(0, delta + jitter)
            await asyncio.sleep(delay_seconds + random.uniform(0.05, 0.2))

        metrics = await page.evaluate("""() => ({
                y: Math.round(window.scrollY),
                h: Math.round(document.body.scrollHeight),
                vh: Math.round(window.innerHeight)
            })""")
        audit_log(
            "browser_scroll",
            {
                "direction": direction,
                "pixels": pixels,
                "steps": steps,
                "delay_seconds": delay_seconds,
            },
            "success",
        )
        return (
            f"Scrolled `{direction}` for {steps} steps of ~{pixels}px. "
            f"Position: `{metrics['y']}` / Page height: `{metrics['h']}` / Viewport: `{metrics['vh']}`."
        )
    except Exception as e:
        audit_log(
            "browser_scroll",
            {
                "direction": direction,
                "pixels": pixels,
                "steps": steps,
                "delay_seconds": delay_seconds,
            },
            "error",
            str(e),
        )
        return f"Error scrolling page: {e}"


@register_tool()
async def browser_extract_links(limit: int = 40, same_domain: bool = True) -> str:
    """Extract normalized links from current page for deep crawl/pagination."""
    if limit <= 0:
        return "Error: `limit` must be greater than 0."

    try:
        page = await _get_page()
        current_url = page.url
        current_domain = urlparse(current_url).netloc

        raw_links = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || '').trim()
            }))""")

        dedup = set()
        links = []
        for item in raw_links:
            href = str(item.get("href", "")).strip()
            if not href or href.startswith("#"):
                continue
            lower_href = href.lower()
            if lower_href.startswith("javascript:") or lower_href.startswith("mailto:"):
                continue

            absolute = urljoin(current_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if same_domain and parsed.netloc != current_domain:
                continue
            if absolute in dedup:
                continue

            dedup.add(absolute)
            text = " ".join(str(item.get("text", "")).split())[:120]
            links.append({"url": absolute, "text": text})
            if len(links) >= limit:
                break

        payload = {
            "current_url": current_url,
            "same_domain": same_domain,
            "count": len(links),
            "links": links,
        }
        audit_log(
            "browser_extract_links",
            {"current_url": current_url, "same_domain": same_domain, "limit": limit},
            "success",
        )
        return json.dumps(payload, indent=2)
    except Exception as e:
        audit_log(
            "browser_extract_links",
            {"same_domain": same_domain, "limit": limit},
            "error",
            str(e),
        )
        return f"Error extracting links: {e}"


@register_tool()
async def browser_click_next() -> str:
    """Click common next-page controls to continue beyond page 1."""
    selectors = [
        "a[rel='next']",
        "button[rel='next']",
        "a[aria-label*='next' i]",
        "button[aria-label*='next' i]",
        "a:has-text('Next')",
        "button:has-text('Next')",
        "a:has-text('Older')",
        "button:has-text('Older')",
        "a:has-text('Load more')",
        "button:has-text('Load more')",
        "a:has-text('More')",
        "button:has-text('More')",
    ]
    try:
        page = await _get_page()
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            try:
                await locator.scroll_into_view_if_needed(timeout=3000)
                await asyncio.sleep(random.uniform(0.15, 0.4))
                await locator.click(timeout=5000)
                await page.wait_for_load_state("load", timeout=20000)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                audit_log(
                    "browser_click_next",
                    {"selector": selector, "url": page.url},
                    "success",
                )
                return (
                    f"Moved to next page using `{selector}`. Current URL: `{page.url}`."
                )
            except Exception:
                continue

        audit_log(
            "browser_click_next",
            {"url": page.url},
            "warning",
            "No next-page control found",
        )
        return "No next-page control found on this page."
    except Exception as e:
        audit_log("browser_click_next", {}, "error", str(e))
        return f"Error moving to next page: {e}"


@register_tool()
async def browser_scroll_until_end(
    max_rounds: int = 12,
    step_pixels: int = 1400,
    settle_delay_seconds: float = 0.8,
) -> str:
    """Scroll until page height stops growing, useful for infinite-scroll pages."""
    if max_rounds <= 0:
        return "Error: `max_rounds` must be greater than 0."
    if step_pixels <= 0:
        return "Error: `step_pixels` must be greater than 0."
    if settle_delay_seconds < 0:
        return "Error: `settle_delay_seconds` must be >= 0."

    try:
        page = await _get_page()
        rounds = 0
        unchanged = 0
        last_height = -1

        for _ in range(max_rounds):
            rounds += 1
            jitter = random.randint(-120, 120)
            await page.mouse.wheel(0, step_pixels + jitter)
            await asyncio.sleep(settle_delay_seconds + random.uniform(0.1, 0.35))

            metrics = await page.evaluate("""() => ({
                    y: Math.round(window.scrollY),
                    h: Math.round(document.body.scrollHeight),
                    vh: Math.round(window.innerHeight)
                })""")
            current_height = int(metrics["h"])

            if current_height <= last_height:
                unchanged += 1
            else:
                unchanged = 0

            last_height = current_height

            # Two consecutive unchanged rounds means we likely reached the end.
            if unchanged >= 2:
                break

        final_metrics = await page.evaluate("""() => ({
                y: Math.round(window.scrollY),
                h: Math.round(document.body.scrollHeight),
                vh: Math.round(window.innerHeight)
            })""")

        reached_end = (
            final_metrics["y"] + final_metrics["vh"] >= final_metrics["h"] - 10
        )
        audit_log(
            "browser_scroll_until_end",
            {
                "max_rounds": max_rounds,
                "step_pixels": step_pixels,
                "settle_delay_seconds": settle_delay_seconds,
                "rounds": rounds,
                "final_height": final_metrics["h"],
                "final_y": final_metrics["y"],
                "reached_end": reached_end,
            },
            "success",
        )

        end_state = "reached" if reached_end else "not reached"
        return (
            f"Scroll-until-end finished after `{rounds}` rounds. "
            f"End `{end_state}`. Position: `{final_metrics['y']}` / "
            f"Page height: `{final_metrics['h']}` / Viewport: `{final_metrics['vh']}`."
        )
    except Exception as e:
        audit_log(
            "browser_scroll_until_end",
            {
                "max_rounds": max_rounds,
                "step_pixels": step_pixels,
                "settle_delay_seconds": settle_delay_seconds,
            },
            "error",
            str(e),
        )
        return f"Error scrolling until end: {e}"


@register_tool()
async def browser_crawl_step(
    link_limit: int = 40,
    same_domain: bool = True,
    try_next: bool = True,
    max_scroll_rounds: int = 8,
) -> str:
    """Single crawl step: scroll, collect links, optionally click next, then return state."""
    if link_limit <= 0:
        return "Error: `link_limit` must be greater than 0."
    if max_scroll_rounds <= 0:
        return "Error: `max_scroll_rounds` must be greater than 0."

    try:
        page = await _get_page()
        before_url = page.url

        scroll_result = await browser_scroll_until_end(max_rounds=max_scroll_rounds)
        links_result_raw = await browser_extract_links(
            limit=link_limit, same_domain=same_domain
        )

        links_payload = None
        links_error = None
        try:
            links_payload = json.loads(links_result_raw)
        except Exception:
            links_error = links_result_raw

        next_result = "Skipped next-page click."
        moved_next = False
        if try_next:
            next_result = await browser_click_next()
            moved_next = next_result.startswith("Moved to next page")

        after_url = page.url
        state = {
            "before_url": before_url,
            "after_url": after_url,
            "moved_next": moved_next,
            "scroll": scroll_result,
            "next": next_result,
            "links": (
                links_payload if links_payload is not None else {"error": links_error}
            ),
        }

        audit_log(
            "browser_crawl_step",
            {
                "before_url": before_url,
                "after_url": after_url,
                "moved_next": moved_next,
                "link_limit": link_limit,
                "same_domain": same_domain,
                "try_next": try_next,
                "max_scroll_rounds": max_scroll_rounds,
            },
            "success",
        )
        return json.dumps(state, indent=2)
    except Exception as e:
        audit_log(
            "browser_crawl_step",
            {
                "link_limit": link_limit,
                "same_domain": same_domain,
                "try_next": try_next,
                "max_scroll_rounds": max_scroll_rounds,
            },
            "error",
            str(e),
        )
        return f"Error in crawl step: {e}"


@register_tool()
async def browser_type(selector: str, text: str, press_enter: bool = True) -> str:
    """Type with randomized delays to mimic human typing."""
    try:
        page = await _get_page()
        await page.focus(selector)
        for char in text:
            await page.keyboard.type(char)
            # Human typing speed is inconsistent
            await asyncio.sleep(random.uniform(0.05, 0.2))

        if press_enter:
            await asyncio.sleep(random.uniform(0.4, 1.0))
            await page.keyboard.press("Enter")
        return f"Typed `{text}` into `{selector}` organically."
    except Exception as e:
        audit_log("browser_type", {"selector": selector}, "error", str(e))
        return f"Error: {e}"


@register_tool()
async def browser_screenshot() -> str:
    try:
        page = await _get_page()
        Path(YOLO_ARTIFACTS).mkdir(exist_ok=True)
        import datetime

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = YOLO_ARTIFACTS / f"screenshot_{ts}.png"
        await page.screenshot(path=path)
        audit_log("browser_screenshot", {"path": str(path)}, "success")
        return f"__SEND_FILE__:{os.path.abspath(path)}"
    except Exception as e:
        audit_log("browser_screenshot", {}, "error", str(e))
        return f"Error: {e}"


@register_tool()
async def browser_extract_text() -> str:
    try:
        page = await _get_page()
        text = await page.inner_text("body")
        audit_log("browser_extract_text", {}, "success")
        return text[:10000]
    except Exception as e:
        audit_log("browser_extract_text", {}, "error", str(e))
        return f"Error: {e}"


@register_tool()
async def browser_wait(seconds: float) -> str:
    if seconds < 0:
        return "Error: `seconds` must be >= 0."
    await asyncio.sleep(seconds)
    audit_log("browser_wait", {"seconds": seconds}, "success")
    return f"Waited {seconds}s."


@register_tool()
async def browser_close() -> str:
    global _browser_context, _browser_exit_stack, _page_instance
    async with _get_lock():
        if _browser_exit_stack:
            await _browser_exit_stack.aclose()
        _browser_context = _browser_exit_stack = _page_instance = None
        audit_log("browser_close", {}, "success")
        return "Browser closed."
