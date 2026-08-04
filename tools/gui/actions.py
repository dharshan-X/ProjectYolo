import json
from typing import Optional
from tools.gui.config import GUIConfig
from tools.gui.models import GUIErrorReason, GroundingResult
from tools.gui.engine import capture_state, wait_for_stability
from tools.gui.grounding import ground_element
from tools.gui.backend import emit_click, emit_type, emit_scroll
from tools.gui.verification import verify_transition, format_error
from tools.base import audit_log

def _format_success(result: dict) -> str:
    return json.dumps({"status": "success", "data": result})

def gui_observe(config: GUIConfig) -> str:
    try:
        state = capture_state(config)
        res = _format_success({
            "state_id": state.state_id,
            "active_window": state.active_window.title if state.active_window else None,
            "element_count": len(state.elements),
            "windows": [{"title": w.title, "active": w.is_active} for w in state.windows],
            "elements": [{"id": e.id, "text": e.text, "type": e.type, "bounds": [e.bounds.x, e.bounds.y, e.bounds.width, e.bounds.height]} for e in state.elements[:config.max_elements]]
        })
        audit_log("gui_observe", {}, "success", "Screen observed successfully")
        return res
    except Exception as e:
        audit_log("gui_observe", {}, "error", str(e))
        return format_error(GUIErrorReason.BACKEND_ERROR.value, str(e))
def gui_find(query: str, config: GUIConfig) -> str:
    try:
        state = capture_state(config)
        ground_res = ground_element(query, state.elements, config, state.active_window)

        if ground_res.status == "not_found":
            audit_log("gui_find", {"query": query}, "error", ground_res.reason or "Element not found")
            return format_error(GUIErrorReason.ELEMENT_NOT_FOUND.value, ground_res.reason or "Element not found")

        if ground_res.status == "ambiguous":
            audit_log("gui_find", {"query": query}, "error", "Ambiguous match")
            return format_error(
                GUIErrorReason.AMBIGUOUS_MATCH.value,
                ground_res.reason or "Multiple candidates match the query too closely",
                {"candidates": [c.text for c in ground_res.candidates]}
            )

        el = ground_res.target
        res = _format_success({
            "state_id": state.state_id,
            "target": {
                "text": el.text,
                "bounds": [el.bounds.x, el.bounds.y, el.bounds.width, el.bounds.height],
                "confidence": ground_res.confidence
            }
        })
        audit_log("gui_find", {"query": query, "found": el.text}, "success", "Element found")
        return res
    except Exception as e:
        audit_log("gui_find", {"query": query}, "error", str(e))
        return format_error(GUIErrorReason.BACKEND_ERROR.value, str(e))
def gui_action(query: str, action_type: str, action_args: dict, config: GUIConfig) -> str:
    try:
        # 1. Observe Before
        state_before = capture_state(config)

        # 2. Ground
        ground_res = ground_element(query, state_before.elements, config, state_before.active_window)
        if ground_res.status != "success" or not ground_res.target:
            reason = {
                "not_found": GUIErrorReason.ELEMENT_NOT_FOUND.value,
                "ambiguous": GUIErrorReason.AMBIGUOUS_MATCH.value,
            }.get(ground_res.status, GUIErrorReason.BACKEND_ERROR.value)

            audit_log("gui_action", {"query": query, "action": action_type}, "error", f"Grounding failed: {ground_res.status}")
            return format_error(reason, ground_res.reason or "Could not ground target for action")

        target = ground_res.target
        x, y = target.bounds.center_x, target.bounds.center_y

        # 3. Act
        if action_type == "click":
            emit_click(x, y, button=action_args.get("button", "left"), clicks=action_args.get("clicks", 1))
        elif action_type == "type":
            emit_click(x, y) # Focus first
            emit_type(action_args.get("text", ""))
        elif action_type == "scroll":
            emit_scroll(action_args.get("clicks", -10), x, y)
        else:
            audit_log("gui_action", {"query": query, "action": action_type}, "error", f"Unknown action: {action_type}")
            return format_error("invalid_action", f"Unknown action: {action_type}")

        # 4. Wait for stability
        wait_for_stability(config)

        # 5. Observe After
        state_after = capture_state(config)

        # 6. Verify
        success, msg = verify_transition(state_before, state_after)
        if not success:
            audit_log("gui_action", {"query": query, "action": action_type}, "error", msg)
            return format_error(GUIErrorReason.VERIFICATION_FAILED.value, msg)

        res = _format_success({
            "action": action_type,
            "target": target.text,
            "verification": msg
        })
        audit_log("gui_action", {"query": query, "action": action_type, "target": target.text}, "success", "Action complete and verified")
        return res
    except Exception as e:
        audit_log("gui_action", {"query": query, "action": action_type}, "error", str(e))
        return format_error(GUIErrorReason.BACKEND_ERROR.value, str(e))
