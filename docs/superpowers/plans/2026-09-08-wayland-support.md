# Wayland Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement universal Wayland support across ProjectYolo's GUI automation subsystem (`tools/gui/` and `tools/gui_ops.py`) and Electron desktop client (`desktop/`).

**Architecture:** A pluggable platform abstraction layer under `tools/gui/platform/` with an abstract base class (`PlatformBackend`), auto-detection factory, universal Wayland driver (`grim`, `gnome-screenshot`, `ydotool`, `wtype`, AT-SPI2, compositor IPC), X11 driver fallback, seamless delegation in `backend.py` and `gui_ops.py`, and Chromium Ozone platform auto-configuration in `desktop/main.js`.

**Tech Stack:** Python 3.10+, PIL/Pillow, AT-SPI2, ydotool, wtype, grim, PyAutoGUI, Electron 32 (Ozone Wayland).

## Global Constraints
- Target python version: Python 3.10+ in `.venv`.
- Zero breaking changes to public GUI APIs (`gui_observe`, `gui_find`, `gui_action`, `gui_screenshot`, etc.).
- Audit logging: Every tool action calls `audit_log` on success and error.
- Graceful degradation: If a Wayland tool is missing or fails, fall back to the next tier in the cascade.
- All new code must have full automated unit tests in `tests/test_gui_platform.py`.

---

### Task 1: Platform Base Interface & Auto-Detection Factory

**Files:**
- Create: `tools/gui/platform/base.py`
- Create: `tools/gui/platform/factory.py`
- Create: `tools/gui/platform/__init__.py`
- Test: `tests/test_gui_platform.py`

**Interfaces:**
- Consumes: `tools.gui.models.DisplayLayout`, `tools.gui.models.Monitor`
- Produces: `PlatformBackend` ABC, `get_platform_backend() -> PlatformBackend`, `reset_platform_backend() -> None`

- [ ] **Step 1: Write the failing test for platform factory and base interface**

```python
# tests/test_gui_platform.py
import os
import pytest
from tools.gui.models import DisplayLayout, Monitor
from tools.gui.platform.base import PlatformBackend
from tools.gui.platform.factory import get_platform_backend, reset_platform_backend

def test_platform_backend_abc():
    class IncompleteBackend(PlatformBackend):
        pass

    with pytest.raises(TypeError):
        IncompleteBackend()

def test_factory_detection_wayland(monkeypatch):
    reset_platform_backend()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("YOLO_GUI_BACKEND", raising=False)
    backend = get_platform_backend()
    assert backend.__class__.__name__ == "WaylandBackend"

def test_factory_detection_x11(monkeypatch):
    reset_platform_backend()
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("YOLO_GUI_BACKEND", raising=False)
    backend = get_platform_backend()
    assert backend.__class__.__name__ == "X11Backend"

def test_factory_override(monkeypatch):
    reset_platform_backend()
    monkeypatch.setenv("YOLO_GUI_BACKEND", "x11")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    backend = get_platform_backend()
    assert backend.__class__.__name__ == "X11Backend"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_platform.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.gui.platform.base'`

- [ ] **Step 3: Implement `base.py`, `factory.py`, and `__init__.py`**

```python
# tools/gui/platform/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from PIL import Image
from tools.gui.models import DisplayLayout

class PlatformBackend(ABC):
    """Abstract interface for OS-level GUI perception and interaction."""

    @abstractmethod
    def get_display_layout(self) -> DisplayLayout:
        """Discover connected monitors and screen geometry."""
        pass

    @abstractmethod
    def take_screenshot(self, save_path: Optional[str] = None) -> Image.Image:
        """Capture the screen as a PIL Image."""
        pass

    @abstractmethod
    def get_active_windows(self) -> List[Dict[str, Any]]:
        """Return list of active windows with geometry and title."""
        pass

    @abstractmethod
    def emit_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """Emit mouse click."""
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
        """Scroll mouse wheel."""
        pass

    @abstractmethod
    def emit_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> None:
        """Drag mouse cursor from start to end coordinates."""
        pass
```

```python
# tools/gui/platform/factory.py
import os
from typing import Optional
from tools.gui.platform.base import PlatformBackend

_CACHED_BACKEND: Optional[PlatformBackend] = None

def get_platform_backend() -> PlatformBackend:
    """Resolve and cache the platform backend according to environment."""
    global _CACHED_BACKEND
    if _CACHED_BACKEND is not None:
        return _CACHED_BACKEND

    override = os.getenv("YOLO_GUI_BACKEND", "").lower().strip()
    is_wayland = bool(
        os.getenv("WAYLAND_DISPLAY")
        or os.getenv("XDG_SESSION_TYPE", "").lower() == "wayland"
    )

    if override == "wayland" or (override == "" and is_wayland):
        from tools.gui.platform.wayland import WaylandBackend
        _CACHED_BACKEND = WaylandBackend()
    else:
        from tools.gui.platform.x11 import X11Backend
        _CACHED_BACKEND = X11Backend()

    return _CACHED_BACKEND

def reset_platform_backend() -> None:
    """Reset cached backend singleton (used in testing)."""
    global _CACHED_BACKEND
    _CACHED_BACKEND = None
```

```python
# tools/gui/platform/__init__.py
from .base import PlatformBackend
from .factory import get_platform_backend, reset_platform_backend

__all__ = ["PlatformBackend", "get_platform_backend", "reset_platform_backend"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_gui_platform.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/gui/platform/ tests/test_gui_platform.py
git commit -m "feat(gui): implement platform backend interface and factory"
```

---

### Task 2: X11 Platform Backend Implementation

**Files:**
- Create: `tools/gui/platform/x11.py`
- Test: `tests/test_gui_platform.py`

**Interfaces:**
- Consumes: `tools.gui.platform.base.PlatformBackend`
- Produces: `X11Backend`

- [ ] **Step 1: Write test for X11Backend**

Add to `tests/test_gui_platform.py`:
```python
def test_x11_backend_display_layout(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    monkeypatch.setenv("GUI_DEFAULT_WIDTH", "1280")
    monkeypatch.setenv("GUI_DEFAULT_HEIGHT", "720")
    monkeypatch.setattr("tools.gui.platform.x11._try_xlib_display", lambda: None)
    monkeypatch.setattr("tools.gui.platform.x11._try_pyautogui_display", lambda: None)
    monkeypatch.setattr("tools.gui.platform.x11._try_xrandr_display", lambda: None)
    layout = backend.get_display_layout()
    assert layout.virtual_width == 1280
    assert layout.virtual_height == 720

def test_x11_backend_input(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    clicked = []
    typed = []
    pressed = []
    scrolled = []
    dragged = []

    class MockPyAutoGUI:
        @staticmethod
        def click(x, y, button="left", clicks=1):
            clicked.append((x, y, button, clicks))
        @staticmethod
        def write(text, interval=0.0):
            typed.append((text, interval))
        @staticmethod
        def press(k):
            pressed.append(k)
        @staticmethod
        def hotkey(*keys):
            pressed.append("+".join(keys))
        @staticmethod
        def moveTo(x, y):
            pass
        @staticmethod
        def scroll(clicks):
            scrolled.append(clicks)
        @staticmethod
        def dragTo(x, y, duration=0.5):
            dragged.append((x, y, duration))

    monkeypatch.setattr("tools.gui.platform.x11.pyautogui", MockPyAutoGUI)
    backend.emit_click(10, 20, "left", 1)
    backend.emit_type("hello")
    backend.emit_key("ctrl+c")
    backend.emit_scroll(5, 100, 200)
    backend.emit_drag(0, 0, 50, 50, 0.2)

    assert clicked == [(10, 20, "left", 1)]
    assert typed == [("hello", 0.0)]
    assert pressed == ["ctrl+c"]
    assert scrolled == [5]
    assert dragged == [(50, 50, 0.2)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_platform.py -k "test_x11" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.gui.platform.x11'`

- [ ] **Step 3: Implement `tools/gui/platform/x11.py`**

Encapsulate X11 logic ported cleanly from `backend.py` and `gui_ops.py`:
```python
# tools/gui/platform/x11.py
import os
import subprocess
from typing import Any, Dict, List, Optional
from PIL import Image
from tools.gui.models import DisplayLayout, Monitor
from tools.gui.platform.base import PlatformBackend

try:
    import pyautogui
except Exception:
    pyautogui = None

def _try_xlib_display() -> Optional[DisplayLayout]:
    try:
        import Xlib.display
        d = Xlib.display.Display()
        s = d.screen()
        geom = s.root.get_geometry()
        w, h = geom.width, geom.height
        if w > 0 and h > 0:
            return DisplayLayout(
                monitors=[Monitor(name="x11-root", x=0, y=0, width=w, height=h, is_primary=True)],
                virtual_width=w,
                virtual_height=h,
            )
    except Exception:
        pass
    return None

def _try_pyautogui_display() -> Optional[DisplayLayout]:
    if pyautogui is not None:
        try:
            w, h = pyautogui.size()
            if w > 0 and h > 0:
                return DisplayLayout(
                    monitors=[Monitor(name="pyautogui-screen", x=0, y=0, width=w, height=h, is_primary=True)],
                    virtual_width=w,
                    virtual_height=h,
                )
        except Exception:
            pass
    return None

def _try_xrandr_display() -> Optional[DisplayLayout]:
    if os.name != "nt":
        try:
            output = subprocess.check_output(
                "xrandr | grep '*' | awk '{print $1}'", shell=True, text=True, timeout=2
            )
            res = output.strip().split("\n")[0]
            if "x" in res:
                w_str, h_str = res.split("x")
                w, h = int(w_str), int(h_str)
                return DisplayLayout(
                    monitors=[Monitor(name="xrandr-screen", x=0, y=0, width=w, height=h, is_primary=True)],
                    virtual_width=w,
                    virtual_height=h,
                )
        except Exception:
            pass
    return None

class X11Backend(PlatformBackend):
    """Platform implementation targeting X11 and XWayland."""

    def get_display_layout(self) -> DisplayLayout:
        layout = _try_xlib_display() or _try_pyautogui_display() or _try_xrandr_display()
        if layout:
            return layout
        default_w = int(os.getenv("GUI_DEFAULT_WIDTH", "1920"))
        default_h = int(os.getenv("GUI_DEFAULT_HEIGHT", "1080"))
        return DisplayLayout(
            monitors=[Monitor(name="default-screen", x=0, y=0, width=default_w, height=default_h, is_primary=True)],
            virtual_width=default_w,
            virtual_height=default_h,
        )

    def take_screenshot(self, save_path: Optional[str] = None) -> Image.Image:
        from tools.gui_ops import _take_screenshot_pil
        return _take_screenshot_pil(save_path)

    def get_active_windows(self) -> List[Dict[str, Any]]:
        from tools.gui_ops import _get_active_windows
        return _get_active_windows()

    def emit_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def emit_type(self, text: str, interval: float = 0.0) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        pyautogui.write(text, interval=interval)

    def emit_key(self, key: str) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        if "+" in key:
            keys = [k.strip().lower() for k in key.split("+")]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key.strip().lower())

    def emit_scroll(self, clicks: int, x: int, y: int) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)

    def emit_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=duration)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_gui_platform.py -k "test_x11" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/gui/platform/x11.py tests/test_gui_platform.py
git commit -m "feat(gui): implement X11 platform backend"
```

---

### Task 3: Universal Wayland Platform Backend

**Files:**
- Create: `tools/gui/platform/wayland.py`
- Test: `tests/test_gui_platform.py`

**Interfaces:**
- Consumes: `tools.gui.platform.base.PlatformBackend`
- Produces: `WaylandBackend`

- [ ] **Step 1: Write tests for WaylandBackend**

Add to `tests/test_gui_platform.py`:
```python
def test_wayland_screenshot_grim_cascade(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    test_img = Image.new("RGB", (100, 100), color="blue")
    img_path = tmp_path / "test_screenshot.png"
    test_img.save(img_path)

    backend = WaylandBackend()

    # Mock grim found and succeeding
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/grim" if cmd == "grim" else None)
    def mock_run(args, **kwargs):
        dest = args[1]
        test_img.save(dest)
        class Res:
            returncode = 0
        return Res()

    monkeypatch.setattr("subprocess.run", mock_run)
    img = backend.take_screenshot()
    assert img.size == (100, 100)

def test_wayland_input_ydotool(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    commands = []
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ydotool" if cmd == "ydotool" else None)
    monkeypatch.setattr("subprocess.run", lambda args, **k: commands.append(args))

    backend.emit_click(150, 250, "left", 1)
    backend.emit_type("hello")
    backend.emit_scroll(3, 100, 100)

    assert any("mousemove" in c for c in commands)
    assert any("click" in c for c in commands)
    assert any("type" in c for c in commands)

def test_wayland_active_windows_hyprctl(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    sample_json = '[{"address": "0x123", "at": [100, 200], "size": [800, 600], "title": "Editor"}]'
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/hyprctl" if cmd == "hyprctl" else None)
    monkeypatch.setattr("subprocess.check_output", lambda args, **k: sample_json)

    windows = backend.get_active_windows()
    assert len(windows) == 1
    assert windows[0]["title"] == "Editor"
    assert windows[0]["x"] == 100
    assert windows[0]["w"] == 800
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_platform.py -k "test_wayland" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.gui.platform.wayland'`

- [ ] **Step 3: Implement `tools/gui/platform/wayland.py`**

```python
# tools/gui/platform/wayland.py
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional
from PIL import Image

from tools.base import audit_log
from tools.gui.models import DisplayLayout, Monitor
from tools.gui.platform.base import PlatformBackend
from tools.gui_ops import _is_blank_screenshot_image

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
except (ImportError, ValueError):
    Atspi = None

class WaylandBackend(PlatformBackend):
    """Universal Wayland driver supporting GNOME, Hyprland, Sway, KDE, and wlroots."""

    def __init__(self):
        self.compositor = self._detect_compositor()

    def _detect_compositor(self) -> str:
        desktop = os.getenv("XDG_CURRENT_DESKTOP", "").lower()
        session = os.getenv("DESKTOP_SESSION", "").lower()
        if "hyprland" in desktop or "hyprland" in session or shutil.which("hyprctl"):
            return "hyprland"
        if "sway" in desktop or "sway" in session or shutil.which("swaymsg"):
            return "sway"
        if "gnome" in desktop or "gnome" in session or shutil.which("gnome-screenshot"):
            return "gnome"
        if "kde" in desktop or "plasma" in desktop or shutil.which("spectacle"):
            return "kde"
        return "generic"

    # -----------------------------------------------------------------------
    # Screen Capture Cascade
    # -----------------------------------------------------------------------
    def take_screenshot(self, save_path: Optional[str] = None) -> Image.Image:
        """Capture screen using grim, gnome-screenshot, portal, or XWayland fallback."""
        temp_dest = save_path or os.path.join(tempfile.gettempdir(), f"wayland_shot_{os.getpid()}_{id(self)}.png")

        # 1. Grim (wlroots / Hyprland / Sway)
        if shutil.which("grim"):
            try:
                res = subprocess.run(["grim", temp_dest], capture_output=True, timeout=3)
                if res.returncode == 0 and not _is_blank_screenshot_image(temp_dest):
                    return self._finalize_image(temp_dest, save_path)
            except Exception:
                pass

        # 2. GNOME Screenshot
        if shutil.which("gnome-screenshot"):
            try:
                res = subprocess.run(["gnome-screenshot", "-f", temp_dest], capture_output=True, timeout=3)
                if res.returncode == 0 and not _is_blank_screenshot_image(temp_dest):
                    return self._finalize_image(temp_dest, save_path)
            except Exception:
                pass

        # 3. Spectacle (KDE)
        if shutil.which("spectacle"):
            try:
                res = subprocess.run(["spectacle", "-b", "-n", "-o", temp_dest], capture_output=True, timeout=3)
                if res.returncode == 0 and not _is_blank_screenshot_image(temp_dest):
                    return self._finalize_image(temp_dest, save_path)
            except Exception:
                pass

        # 4. Fallback to XWayland capture via scrot or pyautogui
        from tools.gui_ops import _take_screenshot_pil
        return _take_screenshot_pil(save_path)

    def _finalize_image(self, temp_dest: str, save_path: Optional[str]) -> Image.Image:
        img = Image.open(temp_dest)
        img.load()
        if not save_path:
            try:
                os.remove(temp_dest)
            except Exception:
                pass
        return img

    # -----------------------------------------------------------------------
    # Input Simulation Cascade
    # -----------------------------------------------------------------------
    def emit_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        btn_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
        btn_code = btn_map.get(button.lower(), "0xC0")

        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "mousemove", "--absolute", str(x), str(y)], check=True, timeout=2)
                for _ in range(clicks):
                    subprocess.run(["ydotool", "click", btn_code], check=True, timeout=2)
                return
            except Exception as e:
                audit_log("wayland_emit_click", {"error": str(e)}, "warning", "ydotool failed, trying fallback")

        # Fallback to PyAutoGUI
        if pyautogui is not None:
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        else:
            raise RuntimeError("Wayland click failed: neither ydotool nor pyautogui available")

    def emit_type(self, text: str, interval: float = 0.0) -> None:
        if shutil.which("wtype"):
            try:
                subprocess.run(["wtype", text], check=True, timeout=3)
                return
            except Exception:
                pass

        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "type", text], check=True, timeout=3)
                return
            except Exception:
                pass

        if pyautogui is not None:
            pyautogui.write(text, interval=interval)
        else:
            raise RuntimeError("Wayland type failed: neither wtype, ydotool, nor pyautogui available")

    def emit_key(self, key: str) -> None:
        if shutil.which("wtype"):
            try:
                # wtype supports -k <key> and modifiers -M <mod>
                args = ["wtype"]
                if "+" in key:
                    parts = [p.strip().lower() for p in key.split("+")]
                    for mod in parts[:-1]:
                        args.extend(["-M", mod])
                    args.extend(["-k", parts[-1]])
                    for mod in reversed(parts[:-1]):
                        args.extend(["-m", mod])
                else:
                    args.extend(["-k", key.strip().lower()])
                subprocess.run(args, check=True, timeout=2)
                return
            except Exception:
                pass

        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "key", key], check=True, timeout=2)
                return
            except Exception:
                pass

        if pyautogui is not None:
            if "+" in key:
                keys = [k.strip().lower() for k in key.split("+")]
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key.strip().lower())
        else:
            raise RuntimeError("Wayland key press failed: no suitable input injector")

    def emit_scroll(self, clicks: int, x: int, y: int) -> None:
        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "mousemove", "--absolute", str(x), str(y)], check=True, timeout=2)
                # ydotool mousemove -w <wheel delta>
                subprocess.run(["ydotool", "mousemove", "-w", str(clicks)], check=True, timeout=2)
                return
            except Exception:
                pass

        if pyautogui is not None:
            pyautogui.moveTo(x, y)
            pyautogui.scroll(clicks)
        else:
            raise RuntimeError("Wayland scroll failed")

    def emit_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> None:
        if pyautogui is not None:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration)
            return

        if shutil.which("ydotool"):
            # Click down, move, click up
            subprocess.run(["ydotool", "mousemove", "--absolute", str(start_x), str(start_y)], check=True)
            subprocess.run(["ydotool", "click", "0x40"], check=True) # left button down
            subprocess.run(["ydotool", "mousemove", "--absolute", str(end_x), str(end_y)], check=True)
            subprocess.run(["ydotool", "click", "0x80"], check=True) # left button up
            return

        raise RuntimeError("Wayland drag failed: neither pyautogui nor ydotool available")

    # -----------------------------------------------------------------------
    # Window Discovery
    # -----------------------------------------------------------------------
    def get_active_windows(self) -> List[Dict[str, Any]]:
        windows: List[Dict[str, Any]] = []

        # 1. Hyprland
        if self.compositor == "hyprland" and shutil.which("hyprctl"):
            try:
                out = subprocess.check_output(["hyprctl", "clients", "-j"], text=True, timeout=2)
                data = json.loads(out)
                for c in data:
                    windows.append({
                        "id": str(c.get("address", "")),
                        "x": int(c.get("at", [0, 0])[0]),
                        "y": int(c.get("at", [0, 0])[1]),
                        "w": int(c.get("size", [0, 0])[0]),
                        "h": int(c.get("size", [0, 0])[1]),
                        "title": str(c.get("title", "")),
                    })
                if windows:
                    return windows
            except Exception:
                pass

        # 2. Sway
        if self.compositor == "sway" and shutil.which("swaymsg"):
            try:
                out = subprocess.check_output(["swaymsg", "-t", "get_tree"], text=True, timeout=2)
                tree = json.loads(out)
                windows = self._extract_sway_windows(tree)
                if windows:
                    return windows
            except Exception:
                pass

        # 3. AT-SPI2 Accessibility Frame Enumeration (Universal Wayland / D-Bus)
        atspi_windows = self._get_atspi_windows()
        if atspi_windows:
            return atspi_windows

        # 4. Fallback to XWayland window list (wmctrl / xdotool)
        from tools.gui_ops import _get_active_windows
        return _get_active_windows()

    def _extract_sway_windows(self, node: dict) -> List[Dict[str, Any]]:
        windows = []
        if node.get("name") and node.get("type") in ("con", "floating_con") and node.get("nodes") == []:
            rect = node.get("rect", {})
            windows.append({
                "id": str(node.get("id", "")),
                "x": int(rect.get("x", 0)),
                "y": int(rect.get("y", 0)),
                "w": int(rect.get("width", 0)),
                "h": int(rect.get("height", 0)),
                "title": str(node.get("name", "")),
            })
        for child in node.get("nodes", []):
            windows.extend(self._extract_sway_windows(child))
        for child in node.get("floating_nodes", []):
            windows.extend(self._extract_sway_windows(child))
        return windows

    def _get_atspi_windows(self) -> List[Dict[str, Any]]:
        if Atspi is None:
            return []
        try:
            desktop = Atspi.get_desktop(0)
            if not desktop:
                return []
            windows = []
            for i in range(desktop.get_child_count()):
                app_node = desktop.get_child_at_index(i)
                if not app_node:
                    continue
                for j in range(app_node.get_child_count()):
                    win_node = app_node.get_child_at_index(j)
                    if not win_node:
                        continue
                    role = win_node.get_role()
                    if role in (Atspi.Role.FRAME, Atspi.Role.WINDOW, Atspi.Role.DIALOG):
                        try:
                            ext = win_node.get_extents(Atspi.CoordType.SCREEN)
                            if ext.width > 10 and ext.height > 10:
                                windows.append({
                                    "id": f"{i}_{j}",
                                    "x": ext.x,
                                    "y": ext.y,
                                    "w": ext.width,
                                    "h": ext.height,
                                    "title": win_node.get_name() or "",
                                })
                        except Exception:
                            continue
            return windows
        except Exception:
            return []

    # -----------------------------------------------------------------------
    # Display Layout Detection
    # -----------------------------------------------------------------------
    def get_display_layout(self) -> DisplayLayout:
        # 1. Hyprland monitors
        if shutil.which("hyprctl"):
            try:
                out = subprocess.check_output(["hyprctl", "monitors", "-j"], text=True, timeout=2)
                data = json.loads(out)
                monitors = []
                max_w, max_h = 0, 0
                for m in data:
                    x, y = int(m.get("x", 0)), int(m.get("y", 0))
                    w, h = int(m.get("width", 0)), int(m.get("height", 0))
                    monitors.append(Monitor(
                        name=str(m.get("name", "mon")),
                        x=x, y=y, width=w, height=h,
                        is_primary=bool(m.get("focused", False))
                    ))
                    max_w = max(max_w, x + w)
                    max_h = max(max_h, y + h)
                if monitors:
                    return DisplayLayout(monitors=monitors, virtual_width=max_w, virtual_height=max_h)
            except Exception:
                pass

        # 2. Sway outputs
        if shutil.which("swaymsg"):
            try:
                out = subprocess.check_output(["swaymsg", "-t", "get_outputs"], text=True, timeout=2)
                data = json.loads(out)
                monitors = []
                max_w, max_h = 0, 0
                for o in data:
                    rect = o.get("rect", {})
                    x, y = int(rect.get("x", 0)), int(rect.get("y", 0))
                    w, h = int(rect.get("width", 0)), int(rect.get("height", 0))
                    monitors.append(Monitor(
                        name=str(o.get("name", "mon")),
                        x=x, y=y, width=w, height=h,
                        is_primary=bool(o.get("primary", False))
                    ))
                    max_w = max(max_w, x + w)
                    max_h = max(max_h, y + h)
                if monitors:
                    return DisplayLayout(monitors=monitors, virtual_width=max_w, virtual_height=max_h)
            except Exception:
                pass

        # 3. Physical DRM modes (/sys/class/drm)
        try:
            import glob
            for mode_file in glob.glob("/sys/class/drm/card*-*/modes"):
                with open(mode_file, "r") as f:
                    line = f.readline().strip()
                    if "x" in line:
                        parts = line.split("x")
                        w, h = int(parts[0]), int(parts[1])
                        if w > 0 and h > 0:
                            return DisplayLayout(
                                monitors=[Monitor(name="drm-monitor", x=0, y=0, width=w, height=h, is_primary=True)],
                                virtual_width=w,
                                virtual_height=h
                            )
        except Exception:
            pass

        # 4. Fallback safe default
        default_w = int(os.getenv("GUI_DEFAULT_WIDTH", "1920"))
        default_h = int(os.getenv("GUI_DEFAULT_HEIGHT", "1080"))
        return DisplayLayout(
            monitors=[Monitor(name="default-screen", x=0, y=0, width=default_w, height=default_h, is_primary=True)],
            virtual_width=default_w,
            virtual_height=default_h,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_gui_platform.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/gui/platform/wayland.py tests/test_gui_platform.py
git commit -m "feat(gui): implement universal Wayland platform backend"
```

---

### Task 4: Wire Backend and GUI Operations to Platform Layer

**Files:**
- Modify: `tools/gui/backend.py`
- Modify: `tools/gui_ops.py:321-360`
- Modify: `tools/gui_ops.py:640-710`
- Test: `tests/test_gui_v2.py`

**Interfaces:**
- Consumes: `tools.gui.platform.get_platform_backend()`
- Produces: Seamless delegation of `emit_click`, `emit_type`, `emit_key`, `emit_scroll`, `emit_drag`, `get_display_layout`, `_take_screenshot_pil`, `_get_active_windows`

- [ ] **Step 1: Write integration tests for platform delegation**

Add to `tests/test_gui_platform.py`:
```python
def test_backend_delegation_to_platform(monkeypatch):
    import tools.gui.backend as backend
    from tools.gui.platform.factory import reset_platform_backend

    reset_platform_backend()
    calls = []

    class MockBackend:
        def get_display_layout(self):
            calls.append("layout")
            return DisplayLayout(monitors=[], virtual_width=1000, virtual_height=800)
        def emit_click(self, *a, **k):
            calls.append("click")
        def emit_type(self, *a, **k):
            calls.append("type")
        def emit_key(self, *a, **k):
            calls.append("key")
        def emit_scroll(self, *a, **k):
            calls.append("scroll")
        def emit_drag(self, *a, **k):
            calls.append("drag")

    monkeypatch.setattr("tools.gui.backend.get_platform_backend", lambda: MockBackend())

    assert backend.get_display_layout().virtual_width == 1000
    backend.emit_click(1, 2)
    backend.emit_type("abc")
    backend.emit_key("enter")
    backend.emit_scroll(1, 0, 0)
    backend.emit_drag(0, 0, 1, 1)

    assert calls == ["layout", "click", "type", "key", "scroll", "drag"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_platform.py -k "test_backend_delegation" -v`
Expected: FAIL with `AttributeError: module 'tools.gui.backend' has no attribute 'get_platform_backend'`

- [ ] **Step 3: Update `tools/gui/backend.py` to delegate to platform backend**

Modify `tools/gui/backend.py` so that all functions forward to `get_platform_backend()`:
```python
# tools/gui/backend.py
from tools.gui.models import DisplayLayout
from tools.gui.platform import get_platform_backend

def get_display_layout() -> DisplayLayout:
    """Discover display layout via active platform backend."""
    return get_platform_backend().get_display_layout()

def emit_click(x: int, y: int, button: str = "left", clicks: int = 1):
    try:
        get_platform_backend().emit_click(x=x, y=y, button=button, clicks=clicks)
    except Exception as e:
        raise RuntimeError(f"Backend emit_click failed: {e}")

def emit_type(text: str, interval: float = 0.0):
    try:
        get_platform_backend().emit_type(text=text, interval=interval)
    except Exception as e:
        raise RuntimeError(f"Backend emit_type failed: {e}")

def emit_key(key: str):
    """Press a key or combination like 'enter', 'tab', 'esc', 'ctrl+c'."""
    try:
        get_platform_backend().emit_key(key=key)
    except Exception as e:
        raise RuntimeError(f"Backend emit_key failed: {e}")

def emit_scroll(clicks: int, x: int, y: int):
    try:
        get_platform_backend().emit_scroll(clicks=clicks, x=x, y=y)
    except Exception as e:
        raise RuntimeError(f"Backend emit_scroll failed: {e}")

def emit_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5):
    """Drag from start coordinates to end coordinates."""
    try:
        get_platform_backend().emit_drag(start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y, duration=duration)
    except Exception as e:
        raise RuntimeError(f"Backend emit_drag failed: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_gui_platform.py -v && .venv/bin/pytest tests/test_gui_v2.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tools/gui/backend.py tests/test_gui_platform.py
git commit -m "refactor(gui): delegate backend primitives through platform layer"
```

---

### Task 5: Electron Desktop App Wayland Support

**Files:**
- Modify: `desktop/main.js`
- Modify: `desktop/package.json`
- Test: `tests/test_desktop_wayland.py`

**Interfaces:**
- Consumes: Environment variables `WAYLAND_DISPLAY`, `XDG_SESSION_TYPE`, `YOLO_ELECTRON_OZONE`
- Produces: Native Wayland rendering configuration via Chromium Ozone switches before Electron window initialization

- [ ] **Step 1: Write test for desktop Wayland configuration**

Create `tests/test_desktop_wayland.py`:
```python
# tests/test_desktop_wayland.py
import subprocess
from pathlib import Path

def test_electron_main_js_ozone_switches():
    main_js = Path("desktop/main.js").read_text()
    assert "ozone-platform-hint" in main_js
    assert "WaylandWindowDecorations" in main_js

def test_electron_package_json_scripts():
    pkg_json = Path("desktop/package.json").read_text()
    assert '"start"' in pkg_json
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_desktop_wayland.py -v`
Expected: FAIL with `AssertionError: assert 'ozone-platform-hint' in main_js`

- [ ] **Step 3: Update `desktop/main.js` with Ozone Wayland switches**

Add at the top of `desktop/main.js` before `app.whenReady()`:
```javascript
// Configure Chromium Ozone platform for native Wayland support on Linux
if (process.platform === 'linux') {
  const isWayland = Boolean(process.env.WAYLAND_DISPLAY || process.env.XDG_SESSION_TYPE === 'wayland');
  const ozoneHint = process.env.YOLO_ELECTRON_OZONE || (isWayland ? 'auto' : 'x11');

  if (ozoneHint !== 'x11') {
    app.commandLine.appendSwitch('ozone-platform-hint', ozoneHint);
    app.commandLine.appendSwitch('enable-features', 'WaylandWindowDecorations');
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_desktop_wayland.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/main.js tests/test_desktop_wayland.py
git commit -m "feat(desktop): enable native Wayland Ozone support in Electron"
```

---

### Task 6: Full Regression Verification & Live Smoke Test

**Files:**
- Run complete test suite and live platform probe

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/test_gui_platform.py tests/test_gui_v2.py tests/test_desktop_wayland.py -v`
Expected: ALL PASS

- [ ] **Step 2: Live host smoke test**

Run: `.venv/bin/python -c "from tools.gui.platform import get_platform_backend; b = get_platform_backend(); print('Backend:', type(b).__name__); print('Layout:', b.get_display_layout())"`
Expected: Prints `Backend: WaylandBackend` on Wayland hosts without errors.

- [ ] **Step 3: Commit all changes and verify clean git status**

```bash
git status
```
