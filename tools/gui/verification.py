import json
from typing import Dict, Any, Optional, Tuple
from tools.gui.models import GUIState

def verify_transition(state_before: GUIState, state_after: GUIState) -> Tuple[bool, str]:
    """
    Very basic verification engine.
    Checks if active window changed, or if the number of elements changed significantly.
    In the future, this can use exact visual diffing or LLM-based assertions.
    """
    # 1. Did the active window change?
    before_w = state_before.active_window.title if state_before.active_window else None
    after_w = state_after.active_window.title if state_after.active_window else None

    if before_w != after_w:
        return True, f"Window focus changed from '{before_w}' to '{after_w}'"

    # 2. Did elements change?
    before_count = len(state_before.elements)
    after_count = len(state_after.elements)

    if abs(before_count - after_count) > 5:
        return True, "Significant change in visible UI elements detected"

    # As a fallback for clicks that don't change state (e.g. focusing a text box)
    return False, "No observable UI transition was detected."

def format_error(reason: str, message: str, context: Optional[Dict[str, Any]] = None) -> str:
    return json.dumps({
        "status": "error",
        "reason": reason,
        "message": message,
        "context": context or {}
    })
