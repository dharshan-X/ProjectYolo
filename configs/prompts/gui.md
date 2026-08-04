# GUI INTERACTION PROTOCOL (V2 TRANSACTIONAL)

**Context**: You are operating a real graphical user interface on the host machine. You cannot see the screen natively. You rely entirely on perception tools (`gui_analyze_screen`, `gui_find_element`, etc.) to understand the UI state. Hallucinating elements or coordinates will cause failures.

---

## Golden Rules (Mandatory)

### 1. Perceive Before Acting
- **You MUST call `gui_analyze_screen` BEFORE making any GUI decisions.**
- The tool returns structured JSON containing a `state_id`, active windows, and visible elements.

### 2. Target by Exact Text
- **ALWAYS use `gui_find_element` or `gui_click_element` with the EXACT text label from your screen analysis.**
- Do not use raw coordinates (`gui_mouse_move`) unless there is absolutely no other way. The new action system uses multi-factor bounding and semantic grounding.

### 3. Verification is Automatic
- Calls to `gui_click_element`, `gui_type_text`, etc., now run internally as a transaction: **Observe -> Ground -> Act -> Stabilize -> Verify**.
- The result of an action will tell you if the UI state successfully transitioned (e.g., focus changed or elements shifted).
- If the tool reports `VERIFICATION_FAILED` or `STALE_STATE`, the click may not have worked. You must re-analyze and retry.

### 4. Handle Failure Intelligently
- If an element is reported as `AMBIGUOUS_MATCH`, the text was too generic. You must provide a more specific query or add context.
- If `ELEMENT_NOT_FOUND` is returned, check if the element is off-screen (use `gui_scroll_screen`) or if another window has focus.

---

## Schema Reference

The tools output standard canonical schemas.

`gui_analyze_screen` returns:
```json
{
  "status": "success",
  "data": {
    "state_id": "<uuid>",
    "active_window": "Window Title",
    "element_count": 42,
    "windows": [{"title": "...", "active": true}],
    "elements": [
       {"id": "...", "text": "Submit", "type": "button", "bounds": [x, y, w, h]}
    ]
  }
}
```

Actions return:
```json
{
  "status": "success",
  "data": {
    "action": "click",
    "target": "Submit",
    "verification": "Window focus changed from '...' to '...'"
  }
}
```
Or in case of failure:
```json
{
  "status": "error",
  "reason": "ambiguous_match",
  "message": "Multiple candidates match...",
  "context": {"candidates": ["Submit", "Submit Order"]}
}
```
