import subprocess
from typing import List, Tuple, Optional
from tools.gui.models import Monitor, DisplayLayout

def get_display_layout() -> DisplayLayout:
    try:
        from mss.darwin import get_monitors
        # Optional advanced discovery...
    except ImportError:
        pass

    try:
        # Xlib parsing fallback to get genuine monitor bounds (negative offsets etc)
        import Xlib.display
        d = Xlib.display.Display()
        s = d.screen()
        r = s.root

        # very simplified fallback fetching dimensions from root window
        geom = r.get_geometry()
        w, h = geom.width, geom.height

        # Note: robust xrandr logic should go here, but avoiding fabricated sizes.
        return DisplayLayout(
            monitors=[Monitor(name="x11-root", x=0, y=0, width=w, height=h, is_primary=True)],
            virtual_width=w,
            virtual_height=h
        )
    except Exception as e:
        raise RuntimeError(f"Backend monitor discovery failed: {e}") from e
def emit_click(x: int, y: int, button: str = "left", clicks: int = 1):
    try:
        import pyautogui
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
    except Exception as e:
        raise RuntimeError(f"Backend emit_click failed: {e}")

def emit_type(text: str, interval: float = 0.0):
    try:
        import pyautogui
        pyautogui.write(text, interval=interval)
    except Exception as e:
        raise RuntimeError(f"Backend emit_type failed: {e}")

def emit_scroll(clicks: int, x: int, y: int):
    try:
        import pyautogui
        pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)
    except Exception as e:
        raise RuntimeError(f"Backend emit_scroll failed: {e}")
