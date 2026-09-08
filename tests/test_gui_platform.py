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


def test_factory_override_wayland(monkeypatch):
    reset_platform_backend()
    monkeypatch.setenv("YOLO_GUI_BACKEND", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    backend = get_platform_backend()
    assert backend.__class__.__name__ == "WaylandBackend"


def test_factory_singleton_caching(monkeypatch):
    reset_platform_backend()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("YOLO_GUI_BACKEND", raising=False)
    backend1 = get_platform_backend()
    backend2 = get_platform_backend()
    assert backend1 is backend2


def test_factory_package_exports():
    import tools.gui.platform as platform_pkg
    assert platform_pkg.PlatformBackend is PlatformBackend
    assert platform_pkg.get_platform_backend is get_platform_backend
    assert platform_pkg.reset_platform_backend is reset_platform_backend
