"""X11 platform backend implementation for ProjectYolo GUI tools."""

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
    """Attempt to discover geometry using python-xlib."""
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
    """Attempt to discover geometry using pyautogui.size()."""
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
    """Attempt to discover geometry by parsing xrandr output."""
    if os.name != "nt":
        try:
            output = subprocess.check_output(
                "xrandr | grep '*' | awk '{print $1}'", shell=True, text=True, timeout=2
            )
            res = output.strip().split("\n")[0].strip()
            if "x" in res:
                token = res.split()[0]
                if "x" in token:
                    w_str, h_str = token.split("x")
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
        from tools.gui_ops import _raw_x11_take_screenshot
        return _raw_x11_take_screenshot(save_path)

    def get_active_windows(self) -> List[Dict[str, Any]]:
        from tools.gui_ops import _raw_x11_get_active_windows
        return _raw_x11_get_active_windows()


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
