# Wayland Support for ProjectYolo GUI Subsystem and Electron Desktop

- **Date**: 2026-09-08
- **Status**: Approved / In Review
- **Target Subsystems**: `tools/gui/`, `tools/gui_ops.py`, `desktop/`

---

## 1. Overview

ProjectYolo runs autonomous agent tasks, desktop automation (perception and grounded interaction), and an Electron-based desktop chat interface. Currently, the GUI automation subsystem relies heavily on X11 tools (`Xlib`, `pyautogui`, `xdotool`, `wmctrl`, `xrandr`, `scrot`). When running under modern Linux Wayland compositors (such as GNOME/Mutter, Hyprland, Sway, or KDE Plasma), global input injection, screen capture, and window enumeration behave differently or fail due to Wayland security isolation.

This design introduces:
1. A modular **Platform Abstraction Layer** in `tools/gui/platform/` with universal auto-detection and graceful multi-tier fallbacks across Wayland and X11.
2. Robust Wayland drivers for screenshot capture (`grim`, `gnome-screenshot`, XDG Desktop Portal), input simulation (`ydotool`, `wtype`, PyAutoGUI fallback), window discovery (AT-SPI2 accessibility bus, `hyprctl`, `swaymsg`), and display layout detection.
3. Native Wayland rendering configuration for the **Electron Desktop App** (`desktop/`) via Chromium Ozone platform flags and Wayland window decorations.

---

## 2. Architecture & Directory Structure

We implement the driver hierarchy in `tools/gui/platform/`:

```
tools/gui/platform/
├── __init__.py           # Exports get_platform_backend, PlatformBackend, etc.
├── base.py               # Abstract base class: PlatformBackend
├── factory.py            # Environment inspection, auto-detection & backend caching
├── wayland.py            # Universal Wayland implementation
└── x11.py                # X11 implementation (encapsulating Xlib/pyautogui/wmctrl/scrot)
```

`tools/gui/backend.py` delegates its public functions (`get_display_layout`, `emit_click`, `emit_type`, `emit_key`, `emit_scroll`, `emit_drag`) directly to `get_platform_backend()`.
`tools/gui_ops.py` routes screenshot taking, window listing, and input primitives through `get_platform_backend()`.

---

## 3. Detailed Component Specifications

### 3.1 `PlatformBackend` ABC (`tools/gui/platform/base.py`)

All platform drivers implement the following interface:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from PIL import Image
from tools.gui.models import DisplayLayout

class PlatformBackend(ABC):
    @abstractmethod
    def get_display_layout(self) -> DisplayLayout:
        """Discover connected monitors and bounding geometry."""
        pass

    @abstractmethod
    def take_screenshot(self, save_path: Optional[str] = None) -> Image.Image:
        """Capture screen as PIL Image."""
        pass

    @abstractmethod
    def get_active_windows(self) -> List[Dict[str, Any]]:
        """List active desktop windows with coordinates and titles."""
        pass

    @abstractmethod
    def emit_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """Click mouse at specified coordinate."""
        pass

    @abstractmethod
    def emit_type(self, text: str, interval: float = 0.0) -> None:
        """Type text string."""
        pass

    @abstractmethod
    def emit_key(self, key: str) -> None:
        """Press key or key combination."""
        pass

    @abstractmethod
    def emit_scroll(self, clicks: int, x: int, y: int) -> None:
        """Scroll vertical wheel at position."""
        pass

    @abstractmethod
    def emit_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> None:
        """Drag mouse cursor from start to end coordinates."""
        pass
```

### 3.2 Platform Auto-Detection Factory (`tools/gui/platform/factory.py`)

1. **Environment Check**:
   - Explicit override: `YOLO_GUI_BACKEND` (`"wayland"` or `"x11"`).
   - Auto-detection: If `os.getenv("WAYLAND_DISPLAY")` or `os.getenv("XDG_SESSION_TYPE", "").lower() == "wayland"`, use `WaylandBackend`. Otherwise, use `X11Backend`.
2. **Caching**:
   - `get_platform_backend()` maintains a cached instance, resetable via `reset_platform_backend()` for testing.

### 3.3 Universal Wayland Implementation (`tools/gui/platform/wayland.py`)

#### A. Screen Capture Cascade
1. **`grim`**: If binary is found on `PATH`, executes `grim <tmp_path>` (works on wlroots, Hyprland, Sway).
2. **`gnome-screenshot`**: If binary is found on `PATH` and desktop is GNOME, executes `gnome-screenshot -f <tmp_path>`.
3. **XDG Desktop Portal D-Bus**: Calls `org.freedesktop.portal.Screenshot` if available.
4. **XWayland Fallback**: Invokes `pyautogui.screenshot()` / `scrot`.
5. Verifies image is non-blank via `_is_blank_screenshot_image`.

#### B. Input Simulation Cascade
1. **`ydotool`**:
   - Move: `ydotool mousemove --absolute <x> <y>`
   - Click: `ydotool click 0xC0` (left), `0xC1` (right), `0xC2` (middle)
   - Type: `ydotool type "<text>"`
   - Key: `ydotool key <key_sequence>`
2. **`wtype`**: Specialized for typing on wlroots compositors.
3. **PyAutoGUI Fallback**: Emits events to XWayland clients.

#### C. Active Window Discovery
1. **AT-SPI2 Accessibility**: Reads top-level frames (`Atspi.Role.FRAME`, `Atspi.Role.WINDOW`) via desktop accessibility D-Bus, retrieving position, dimensions, and window titles without compositor-specific privileges.
2. **Compositor IPC**:
   - Hyprland: `hyprctl clients -j`
   - Sway: `swaymsg -t get_tree`
3. **Fallback**: `wmctrl -l -G` / `xdotool` for XWayland windows.

#### D. Display Layout Detection
1. Queries compositor monitors:
   - Hyprland: `hyprctl monitors -j`
   - Sway: `swaymsg -t get_outputs`
   - `wlr-randr`
2. Reads physical DRM modes from `/sys/class/drm/card*-*/modes`.
3. Fallbacks to PyAutoGUI / `GUI_DEFAULT_WIDTH` & `GUI_DEFAULT_HEIGHT`.

### 3.4 X11 Implementation (`tools/gui/platform/x11.py`)

Preserves the existing implementations cleanly:
- Display layout: `Xlib.display.Display().screen().root.get_geometry()`, `xrandr`, PyAutoGUI.
- Screen capture: `pyautogui.screenshot()`, `scrot`.
- Windows: `wmctrl -l -G`, `xdotool`.
- Input: `pyautogui` clicks, typing, hotkeys, scrolling, drag.

### 3.5 Electron Desktop App Wayland Support (`desktop/main.js`)

Before `app.whenReady()` in `desktop/main.js`:
```javascript
if (process.platform === 'linux') {
  const isWayland = Boolean(process.env.WAYLAND_DISPLAY || process.env.XDG_SESSION_TYPE === 'wayland');
  const ozoneHint = process.env.YOLO_ELECTRON_OZONE || (isWayland ? 'auto' : 'x11');

  if (ozoneHint !== 'x11') {
    app.commandLine.appendSwitch('ozone-platform-hint', ozoneHint);
    app.commandLine.appendSwitch('enable-features', 'WaylandWindowDecorations');
  }
}
```

---

## 4. Error Handling & Graceful Degradation

1. **Missing Wayland Utilities**: If tools like `ydotool` or `grim` are absent or daemon is inactive, operations log informative diagnostics and degrade gracefully to PyAutoGUI or return actionable error messages (`BACKEND_ERROR` / `ELEMENT_NOT_FOUND`).
2. **Blank Screenshots**: If a screenshot utility outputs a solid black or empty file, the cascade tries the next available mechanism in the chain.
3. **Accessibility (AT-SPI2) Unavailability**: Falls back to OCR and compositor window queries if AT-SPI is uninitialized.

---

## 5. Testing & Verification

1. **`tests/test_gui_platform.py`**:
   - Platform backend factory detection (mocking `WAYLAND_DISPLAY`, `XDG_SESSION_TYPE`, `YOLO_GUI_BACKEND`).
   - Wayland screen capture fallback cascade (mocking `subprocess.run` for `grim`, `gnome-screenshot`, `portal`).
   - Wayland input emission with `ydotool` and `wtype`.
   - Wayland window discovery parsing (`hyprctl`, `swaymsg`, AT-SPI2).
   - Display layout discovery parsing.
   - X11 backend regressions.
2. **Regression Tests**:
   - `tests/test_gui_v2.py` (all 17 test cases continue to pass).
   - `tests/test_tools.py`.
3. **Host Smoke Testing**:
   - Execute layout detection and screenshot capture in the live host environment.
