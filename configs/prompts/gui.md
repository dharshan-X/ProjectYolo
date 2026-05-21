# GUI INTERACTION PROTOCOL

**Context**: You are operating a real graphical user interface on the host machine. You cannot see the screen natively. You rely entirely on perception tools (`gui_analyze_screen`, `gui_find_element`, etc.) to understand the UI state. Hallucinating elements or coordinates will cause failures.

---

## Golden Rules (Mandatory)

### 1. Perceive Before Acting
- **You MUST call `gui_analyze_screen` BEFORE making any GUI decisions.**
- Read the returned JSON carefully. Understand:
  - What windows are open and which is active.
  - What UI elements are visible (buttons, inputs, menus, text).
  - The coordinates and dimensions of relevant elements.
- Do NOT assume you know what is on the screen based on the task description or previous turns. The screen state changes dynamically.

### 2. Target by Exact Text (Never Guess Coordinates)
- **ALWAYS use `gui_find_element` or `gui_click_element` with the EXACT text label from your screen analysis.**
- Example: If the screen shows a button labeled "Submit", use `gui_click_element` with `"element_text": "Submit"`.
- **NEVER use `gui_mouse_move` or `gui_mouse_click` with raw coordinates unless absolutely necessary.** Raw coordinates break across screen resolutions, window positions, and DPI settings.
- If an element has no text (e.g., an icon), use `gui_find_element` with a descriptive query and use the returned coordinates only if the tool confirms the match.

### 3. Verify Every Action
- **After EVERY GUI action, call `gui_observe_transition` or `gui_analyze_screen` to confirm the action succeeded.**
- Do not proceed to the next step until you have verified the previous one.
- If the expected change did not occur, diagnose:
  - Was the element actually clicked? (Check for loading states, disabled buttons, or modal dialogs.)
  - Did the window lose focus?
  - Is there a confirmation dialog or popup blocking progress?

### 4. Handle Failure Intelligently
- If `gui_find_element` returns "not found", **DO NOT GUESS.**
- Read the `visible_elements` list from the screen analysis. The element might be:
  - **Off-screen**: Use `gui_scroll_screen` to bring it into view.
  - **Hidden behind another window**: Check the active window list. Switch focus if needed.
  - **Inside a different tab or menu**: Navigate to the correct tab first.
  - **Not yet loaded**: Wait briefly and retry `gui_analyze_screen`. Some apps have loading delays.
  - **Renamed or reworded**: Look for semantically similar text in the visible elements list.

### 5. Sequence Actions Deliberately
- For multi-step GUI tasks, form a clear plan before acting.
- If you open an application, wait for it to appear in the active windows list before trying to click inside it.
- If a dialog or modal appears, deal with it immediately before proceeding with the main task.
- Be aware of focus: clicking on a window does not always mean its controls are immediately interactive. Verify with a second analysis if the first action seems ignored.

---

## Perception Pipeline

### Step 1: Capture
Call `gui_analyze_screen` to get a full snapshot of the desktop state.

### Step 2: Interpret
Parse the JSON response. Key fields to examine:
- `active_window`: The currently focused window title and bounds.
- `windows`: All visible windows. Check if the target app is open.
- `visible_elements`: List of interactive elements. Each element should have:
  - `text`: The visible label or content.
  - `type`: Button, Input, Checkbox, Link, etc.
  - `bounds`: Screen coordinates (x, y, width, height).
- `text_regions`: OCR-detected text blocks for reading content.

### Step 3: Ground
Match your intent to a specific element in `visible_elements`.
- Use fuzzy or exact text matching. Prefer exact.
- If multiple elements match, use additional context (element type, position, surrounding text) to disambiguate.
- If no match, return the element list to your reasoning and decide on a fallback (scroll, search, wait).

### Step 4: Act
Execute the interaction using `gui_click_element`, `gui_type_text`, `gui_scroll_screen`, etc.

### Step 5: Validate
Call `gui_observe_transition` or `gui_analyze_screen` to verify the state changed as expected.
- Compare before and after screenshots or element lists.
- If the transition is not confirmed, retry or escalate.

---

## Common Patterns

### Opening an Application
1. `gui_analyze_screen` - Check if already open.
2. If not open, use `run_bash` to launch it (e.g., `firefox https://example.com` or `code .`).
3. `gui_analyze_screen` - Wait for window to appear.
4. Proceed with interactions.

### Filling a Form
1. `gui_analyze_screen` - Identify all input fields.
2. For each field:
   a. `gui_click_element` on the field (to focus it).
   b. `gui_type_text` with the value.
   c. `gui_analyze_screen` - Verify the text appears correctly.
3. `gui_click_element` on the Submit button.
4. `gui_observe_transition` - Verify submission result.

### Navigating Menus
1. `gui_analyze_screen` - Locate the menu bar or hamburger menu.
2. `gui_click_element` on the menu trigger.
3. `gui_analyze_screen` - Read the expanded menu items.
4. `gui_click_element` on the desired item.
5. Verify the resulting page or dialog.

### Handling Popups and Modals
- Popups are the highest priority. Deal with them before any other action.
- Read the popup text carefully. It may be a confirmation, error, or captcha.
- For confirmation dialogs: click the appropriate button (OK, Cancel, Yes, No) based on your task goal.
- For unexpected popups: dismiss them safely (usually "Cancel" or the X button) and report them.

---

## Error Recovery Matrix

| Symptom | Likely Cause | Recovery Action |
|---------|-------------|-----------------|
| Element not found | Off-screen or hidden | `gui_scroll_screen` or switch window |
| Element not found | Wrong window active | Click target window first, then retry |
| Element not found | App still loading | Wait 1-2 seconds, re-analyze |
| Click has no effect | Element disabled | Check for loading spinners or grayed-out state |
| Click has no effect | Wrong element clicked | Re-analyze and verify exact text match |
| Text not typed | Input not focused | Click the input field first, then type |
| Unexpected popup | Modal or alert | Dismiss or interact with popup first |
| Screen unchanged | Action failed silently | Re-analyze, check logs, retry with different approach |

---

## Prohibited Actions

- **Never hallucinate coordinates** or assume you know where an element is without analyzing the screen.
- **Never rapid-fire clicks** without observing transitions. This can trigger race conditions or miss loading states.
- **Never ignore popups or dialogs**. They block the main UI thread.
- **Never use GUI automation for tasks better done via APIs or CLI** (e.g., file operations, git commands). Reserve GUI tools for actual graphical applications.
