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
        try:
            from tools.gui.platform.wayland import WaylandBackend
        except ImportError:
            class WaylandBackend(PlatformBackend):
                """Placeholder until WaylandBackend is implemented."""
                def get_display_layout(self): pass
                def take_screenshot(self, save_path=None): pass
                def get_active_windows(self): return []
                def emit_click(self, x, y, button="left", clicks=1): pass
                def emit_type(self, text, interval=0.0): pass
                def emit_key(self, key): pass
                def emit_scroll(self, clicks, x, y): pass
                def emit_drag(self, start_x, start_y, end_x, end_y, duration=0.5): pass

        _CACHED_BACKEND = WaylandBackend()
    else:
        from .x11 import X11Backend

        _CACHED_BACKEND = X11Backend()

    return _CACHED_BACKEND


def reset_platform_backend() -> None:
    """Reset cached backend singleton (used in testing)."""
    global _CACHED_BACKEND
    _CACHED_BACKEND = None
