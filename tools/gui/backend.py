import subprocess
from typing import List, Tuple, Optional
from tools.gui.models import Monitor, DisplayLayout

def get_display_layout() -> DisplayLayout:
    # A simplified fallback layout if xrandr is unavailable
    try:
        # Just fallback to pyautogui size for now as the virtual display
        import pyautogui
        w, h = pyautogui.size()
        return DisplayLayout(
            monitors=[Monitor(name="default", x=0, y=0, width=w, height=h, is_primary=True)],
            virtual_width=w,
            virtual_height=h
        )
    except Exception:
        return DisplayLayout([], 1920, 1080)

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
