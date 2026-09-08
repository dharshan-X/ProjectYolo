from tools.gui.models import DisplayLayout
from tools.gui.platform import get_platform_backend


def get_display_layout() -> DisplayLayout:
    """Discover display layout via active platform backend."""
    return get_platform_backend().get_display_layout()


def emit_click(x: int, y: int, button: str = "left", clicks: int = 1):
    try:
        get_platform_backend().emit_click(x=x, y=y, button=button, clicks=clicks)
    except Exception as e:
        raise RuntimeError(f"Backend emit_click failed: {e}") from e


def emit_type(text: str, interval: float = 0.0):
    try:
        get_platform_backend().emit_type(text=text, interval=interval)
    except Exception as e:
        raise RuntimeError(f"Backend emit_type failed: {e}") from e


def emit_key(key: str):
    """Press a key or combination like 'enter', 'tab', 'esc', 'ctrl+c'."""
    try:
        get_platform_backend().emit_key(key=key)
    except Exception as e:
        raise RuntimeError(f"Backend emit_key failed: {e}") from e


def emit_scroll(clicks: int, x: int, y: int):
    try:
        get_platform_backend().emit_scroll(clicks=clicks, x=x, y=y)
    except Exception as e:
        raise RuntimeError(f"Backend emit_scroll failed: {e}") from e


def emit_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5, **kwargs):
    """Drag from start coordinates to end coordinates."""
    try:
        get_platform_backend().emit_drag(start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y, duration=duration)
    except Exception as e:
        raise RuntimeError(f"Backend emit_drag failed: {e}") from e


