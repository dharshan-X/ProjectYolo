import difflib
import math
from typing import List, Tuple, Optional

from tools.gui.models import UIElement, GroundingResult, GUIWindow
from tools.gui.config import GUIConfig

def normalized_text(text: str) -> str:
    return text.lower().strip()

def compute_text_score(target_text: str, element_text: str) -> float:
    t_text = normalized_text(target_text)
    e_text = normalized_text(element_text)

    if not t_text or not e_text:
        return 0.0

    if t_text == e_text:
        return 1.0

    # Check if target is a clean substring
    if t_text in e_text:
        return 0.9  # Substring match is strong

    # Difflib matching
    matcher = difflib.SequenceMatcher(None, t_text, e_text)
    return matcher.ratio()

def ground_element(
    query_text: str,
    elements: List[UIElement],
    config: GUIConfig,
    active_window: Optional[GUIWindow] = None
) -> GroundingResult:
    """
    Grounds an element using text similarity, spatial, and window context.
    """
    if not elements:
        return GroundingResult(target=None, confidence=0.0, margin=0.0, status="not_found", reason="No elements available")

    scored_candidates = []

    for el in elements:
        score = 0.0

        # 1. Text Score (Highest weight)
        text_score = compute_text_score(query_text, el.text)
        score += config.weight_text * text_score

        # 2. Role Score (Boost interactive elements)
        role_score = 0.5
        if el.type.lower() in ["button", "link", "input", "menu item", "checkbox", "radio button"]:
            role_score = 1.0
        score += config.weight_role * role_score

        # 3. Window Context (Boost elements inside the active window)
        window_score = 0.5
        if active_window:
            # Check if element's center is inside active window
            aw = active_window.bounds
            if (aw.x <= el.bounds.center_x <= aw.x + aw.width and
                aw.y <= el.bounds.center_y <= aw.y + aw.height):
                window_score = 1.0
        score += config.weight_window * window_score

        # Parse spatial hints from query_text if any (e.g. "top left", "bottom")
        spatial_score = 0.0
        q_lower = query_text.lower()
        if "top" in q_lower and el.bounds.y < 300: spatial_score += 0.5
        if "bottom" in q_lower and el.bounds.y > 600: spatial_score += 0.5
        if "left" in q_lower and el.bounds.x < 300: spatial_score += 0.5
        if "right" in q_lower and el.bounds.x > 600: spatial_score += 0.5
        if "top" not in q_lower and "bottom" not in q_lower and "left" not in q_lower and "right" not in q_lower:
            spatial_score = 0.5 # Default neutral if no hint

        score += config.weight_spatial * spatial_score

        scored_candidates.append((score, el))

    # Sort descending
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    top_score, top_el = scored_candidates[0]
    second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0

    margin = top_score - second_score

    # Evaluate against thresholds
    if top_score < config.min_match_confidence:
        return GroundingResult(
            target=None,
            confidence=top_score,
            margin=margin,
            status="not_found",
            candidates=[el for s, el in scored_candidates[:3]],
            reason=f"Confidence {top_score:.2f} below threshold {config.min_match_confidence}"
        )

    if len(scored_candidates) > 1 and margin < config.min_match_margin:
        return GroundingResult(
            target=None,
            confidence=top_score,
            margin=margin,
            status="ambiguous",
            candidates=[el for s, el in scored_candidates[:3]],
            reason=f"Ambiguous match. Margin {margin:.2f} below threshold {config.min_match_margin}"
        )

    return GroundingResult(
        target=top_el,
        confidence=top_score,
        margin=margin,
        status="success",
        candidates=[el for s, el in scored_candidates[:3]]
    )
