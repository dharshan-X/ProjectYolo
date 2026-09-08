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
        from .wayland import WaylandBackend

        _CACHED_BACKEND = WaylandBackend()
    else:
        from .x11 import X11Backend

        _CACHED_BACKEND = X11Backend()

    return _CACHED_BACKEND


def reset_platform_backend() -> None:
    """Reset cached backend singleton (used in testing)."""
    global _CACHED_BACKEND
    _CACHED_BACKEND = None
