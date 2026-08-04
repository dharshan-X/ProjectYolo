import json
from typing import Optional
from tools.gui.config import GUIConfig
from tools.gui.models import GUIErrorReason, GroundingResult
from tools.gui.engine import capture_state, wait_for_stability
from tools.gui.grounding import ground_element
from tools.gui.backend import emit_click, emit_type, emit_scroll
from tools.gui.verification import verify_transition, format_error

def _format_success(result: dict) -> str:
    return json.dumps({"status": "success", "data": result})

def gui_observe(config: GUIConfig) -> str:
    state = capture_state(config)
    return _format_success({
        "state_id": state.state_id,
        "active_window": state.active_window.title if state.active_window else None,
        "element_count": len(state.elements),
        "windows": [{"title": w.title, "active": w.is_active} for w in state.windows],
        "elements": [{"id": e.id, "text": e.text, "type": e.type, "bounds": [e.bounds.x, e.bounds.y, e.bounds.width, e.bounds.height]} for e in state.elements[:config.max_elements]]
    })

def gui_find(query: str, config: GUIConfig) -> str:
    state = capture_state(config)
    ground_res = ground_element(query, state.elements, config, state.active_window)

    if ground_res.status == "not_found":
        return format_error(GUIErrorReason.ELEMENT_NOT_FOUND.value, ground_res.reason or "Element not found")

    if ground_res.status == "ambiguous":
        return format_error(
            GUIErrorReason.AMBIGUOUS_MATCH.value,
            ground_res.reason or "Multiple candidates match the query too closely",
            {"candidates": [c.text for c in ground_res.candidates]}
        )

    el = ground_res.target
    return _format_success({
        "state_id": state.state_id,
        "target": {
            "text": el.text,
            "bounds": [el.bounds.x, el.bounds.y, el.bounds.width, el.bounds.height],
            "confidence": ground_res.confidence
        }
    })

def gui_action(query: str, action_type: str, action_args: dict, config: GUIConfig) -> str:
    # 1. Observe Before
    state_before = capture_state(config)

    # 2. Ground
    ground_res = ground_element(query, state_before.elements, config, state_before.active_window)
    if ground_res.status != "success" or not ground_res.target:
        return format_error(
            ground_res.status if ground_res.status != "not_found" else GUIErrorReason.ELEMENT_NOT_FOUND.value,
            ground_res.reason or "Could not ground target for action"
        )

    target = ground_res.target
    x, y = target.bounds.center_x, target.bounds.center_y

    # 3. Act
    try:
        if action_type == "click":
            emit_click(x, y, button=action_args.get("button", "left"), clicks=action_args.get("clicks", 1))
        elif action_type == "type":
            emit_click(x, y) # Focus first
            emit_type(action_args.get("text", ""))
        elif action_type == "scroll":
            emit_scroll(action_args.get("clicks", -10), x, y)
        else:
            return format_error("invalid_action", f"Unknown action: {action_type}")
    except Exception as e:
        return format_error(GUIErrorReason.BACKEND_ERROR.value, str(e))

    # 4. Wait for stability
    wait_for_stability(config)

    # 5. Observe After
    state_after = capture_state(config)

    # 6. Verify
    success, msg = verify_transition(state_before, state_after)
    if not success:
        return format_error(GUIErrorReason.VERIFICATION_FAILED.value, msg)

    return _format_success({
        "action": action_type,
        "target": target.text,
        "verification": msg
    })
