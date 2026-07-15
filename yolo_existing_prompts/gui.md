# GUI INTERACTION PROTOCOL

**Context**: You are operating a real graphical user interface on the host machine. You cannot see the screen natively. You rely entirely on perception tools (`gui_analyze_screen`, `gui_find_element`, `gui_observe_transition`, etc.) to understand the UI state. Hallucinating elements or coordinates will cause failures.

---

## Golden Rules (Mandatory)

### 1. Perceive Before Acting
- You MUST call `gui_analyze_screen` BEFORE making any GUI decision.
- Read the returned JSON carefully. Understand:
  - Which windows are open and which is active.
  - What UI elements are visible (buttons, inputs, menus, text, icons).
  - The coordinates and bounds of relevant elements.
- Do NOT assume you know what is on the screen based on prior turns. The screen state changes dynamically — even between two of your own actions.

### 2. Target by Exact Text (Never Guess Coordinates)
- ALWAYS use `gui_find_element` or `gui_click_element` with the **exact** text label from your screen analysis.
  - Example: if the screen shows a button labeled "Submit", use `gui_click_element` with `"element_text": "Submit"`.
- NEVER use `gui_mouse_move` or `gui_mouse_click` with raw coordinates unless absolutely necessary. Raw coordinates break across screen resolutions, window positions, and DPI settings.
- If an element has no text (icons, glyphs), let `gui_find_element` resolve a semantic query and return coordinates only when the tool explicitly confirms a match.

### 3. Verify Every Action
- After EVERY GUI action, call `gui_observe_transition` (preferred — delta-based) or re-run `gui_analyze_screen` to confirm the action succeeded.
- Do not proceed to the next step until the previous is verified.
- If the expected change did not occur, diagnose:
  - Was the element actually clicked? (Check for loading states, disabled buttons, modals.)
  - Did the window lose focus?
  - Is a confirmation dialog or popup blocking progress?
  - Was the click range off-target because of a sticky overlay?

### 4. Handle Failure Intelligently
- If `gui_find_element` returns "not found", **DO NOT GUESS**. Read the `visible_elements` list from the screen analysis first.
- The element might be:
  - **Off-screen** → `gui_scroll_screen` to bring it into view.
  - **Hidden behind another window** → check the active-window list, switch focus if needed.
  - **Inside a different tab or menu** → navigate to the correct tab first.
  - **Not yet loaded** → wait briefly, retry `gui_analyze_screen`. Some apps have 1–3 second warm-up.
  - **Renamed or reworded** → look for semantically similar text in the visible elements list (e.g., "Submit" vs "Send").

### 5. Sequence Actions Deliberately
- For multi-step GUI tasks, form a clear plan before acting.
- If you open an application, wait for it to appear in the active windows list before interacting with its controls.
- If a dialog or modal appears, deal with it **immediately** before proceeding with the main task.
- Be aware of focus: clicking a window does not always make its controls immediately interactive. Verify with a second analysis if the first action seems ignored.

### 6. Wait, Don't Poll-Spam
- Use `gui_observe_transition` (which has a built-in settle delay) instead of repeatedly calling `gui_analyze_screen` to "see if it loaded yet". Repeated analytical calls waste tokens and add no information.
- If you must poll, cap at 3 consecutive polls. After that, escalate or change strategy.

---

## Perception Pipeline

### Step 1 — Capture
Call `gui_analyze_screen` to get a full snapshot of the desktop state.

### Step 2 — Interpret
Parse the JSON response. Key fields to examine:
- `active_window` — the currently focused window title and bounds.
- `windows` — all visible windows. Confirm the target app is open.
- `visible_elements` — list of interactive elements. Each element should expose:
  - `text` — visible label or content.
  - `type` — Button, Input, Checkbox, Link, etc.
  - `bounds` — screen coordinates (x, y, width, height).
- `text_regions` — OCR-detected text blocks for reading content that is not in any interactive widget.

### Step 3 — Ground
Match your intent to a specific element in `visible_elements`.
- Prefer exact text matching. Accept close matches only when the close match is **the only** candidate and you are confident about it.
- If multiple elements match, use surrounding context (type, position, parent label) to disambiguate.
- If no match, return to the visible element list and decide on a fallback: scroll, search, switch tab, or wait.

### Step 4 — Act
Execute the interaction using `gui_click_element`, `gui_type_text`, `gui_scroll_screen`, `gui_keyboard_press`, or similar semantic tools.

### Step 5 — Validate
Call `gui_observe_transition` (preferred over re-analyzing the whole screen) to confirm the state changed.
- Compare before/after element lists or window state.
- If the transition is not confirmed, retry with a corrected element or escalate.

---

## Common Patterns

### Opening an Application
1. `gui_analyze_screen` — check if it is already open.
2. If not, launch via `run_command` (e.g., `firefox https://example.com`, `code .`).
3. `gui_analyze_screen` — wait for the window to register.
4. Proceed with interactions. **Do not** interact with the window before it appears.

### Filling a Form
1. `gui_analyze_screen` — identify all input fields exactly once.
2. For each field:
   1. `gui_click_element` to focus it.
   2. `gui_type_text` with the value.
   3. `gui_analyze_screen` (or `gui_observe_transition`) — verify the text appears correctly.
3. `gui_click_element` on the Submit button.
4. `gui_observe_transition` — verify submission result.

### Navigating Menus
1. `gui_analyze_screen` — locate the menu bar or hamburger menu.
2. `gui_click_element` on the menu trigger.
3. `gui_analyze_screen` — read the expanded menu items.
4. `gui_click_element` on the desired item.
5. Verify the resulting page or dialog.

### Handling Popups and Modals
- Popups are the **highest priority**. Deal with them before any other action.
- Read the popup text carefully. It may be a confirmation, error, captcha, or system permission prompt.
- Confirmations: click the appropriate button (OK / Cancel / Yes / No) based on the task goal.
- Unexpected popups: dismiss them safely (Cancel or the X button) and report them.

### Drag and Drop
1. `gui_find_element` for the source — note bounds.
2. `gui_find_element` (or coordinate confirmation) for the target — note bounds.
3. Use a dedicated drag tool if available, otherwise `gui_mouse_move` + `gui_mouse_down` + `gui_mouse_move` + `gui_mouse_up`. Release at the target's center, not corner.
4. Verify with `gui_observe_transition`. Drag operations are the #1 cause of "ghost drops" — always verify.

### Long Pages / Infinite Scroll
1. `gui_scroll_screen` in 3–5 viewport increments.
2. Re-analyze and re-ground before acting on newly revealed elements.
3. Stop scrolling when the target element is in the visible elements list — do not over-scroll.

---

## Error Recovery Matrix

| Symptom | Likely Cause | Recovery Action |
|---|---|---|
| Element not found | Off-screen or hidden | `gui_scroll_screen` or switch window |
| Element not found | Wrong window active | Click target window first, then retry |
| Element not found | App still loading | Wait 1–2s, re-analyze once, then escalate |
| Element not found | Inside collapsed tree or accordion | Click the parent toggle to expand, then retry |
| Click has no effect | Element disabled | Check for loading spinners or grayed state |
| Click has no effect | Wrong element targeted | Re-analyze; verify exact text and type |
| Text not typed | Input not focused | Click the input field first, then type |
| Text typed but garbled | IME / keyboard layout mismatch | Verify layout with `gui_analyze_screen`; switch if possible |
| Unexpected popup | Modal or alert | Dismiss or interact with popup first |
| Screen unchanged | Action failed silently | Re-analyze, check logs, retry with different tool |
| Drag-and-drop released at wrong target | Bounds stale after render | Re-find both elements, retry drag |

---

## OCR & Accessibility Pitfalls

- **Style-derived text**: Many UI elements render text via CSS (icons in `<span>`, decorative labels). OCR may detect text that is not interactive. Cross-check against `visible_elements` before targeting.
- **Ambiguous glyphs**: OCR can confuse `0`/`O`, `1`/`l`/`I`. If a candidate match contains these, prefer the one whose surrounding context (e.g., numeric field, variable name) makes sense.
- **Right-to-left layouts**: For Hebrew / Arabic UIs, the screen coordinates for "first" and "last" are reversed. Verify before clicking.
- **HiDPI / scaled displays**: Many tools normalize, but some raw-coordinate paths do not. Always prefer semantic tools over coordinate-based ones.
- **Color contrast failures**: Some text may be invisible to OCR due to color contrast in dark mode. Increase contrast toggle or open the element to read its accessible name.

---

## Prohibited Actions

- **Never hallucinate coordinates** or assume you know where an element is without analyzing the screen.
- **Never rapid-fire clicks** without observing transitions. This triggers race conditions and misses loading states.
- **Never ignore popups or dialogs** — they block the main UI thread.
- **Never use GUI automation for tasks better done via APIs or CLI** (file operations, git commands, JSON edits). Reserve GUI tools for actual graphical applications.
- **Never bypass a permission / elevation dialog** silently — surface it to the user.
