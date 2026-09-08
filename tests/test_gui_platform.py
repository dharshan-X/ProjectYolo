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
    from tools.gui.platform.x11 import X11Backend
    assert platform_pkg.X11Backend is X11Backend


def test_x11_try_xlib_display_success(monkeypatch):
    import sys
    from types import SimpleNamespace
    from tools.gui.platform.x11 import _try_xlib_display

    mock_screen = SimpleNamespace(root=SimpleNamespace(get_geometry=lambda: SimpleNamespace(width=2560, height=1440)))
    mock_display_inst = SimpleNamespace(screen=lambda: mock_screen)
    mock_xlib = SimpleNamespace(display=SimpleNamespace(Display=lambda: mock_display_inst))
    monkeypatch.setitem(sys.modules, "Xlib", mock_xlib)
    monkeypatch.setitem(sys.modules, "Xlib.display", mock_xlib.display)

    layout = _try_xlib_display()
    assert layout is not None
    assert layout.virtual_width == 2560
    assert layout.virtual_height == 1440
    assert layout.monitors[0].name == "x11-root"


def test_x11_try_pyautogui_display(monkeypatch):
    from tools.gui.platform.x11 import _try_pyautogui_display

    class MockPyAutoGUI:
        @staticmethod
        def size():
            return (1920, 1080)

    monkeypatch.setattr("tools.gui.platform.x11.pyautogui", MockPyAutoGUI)
    layout = _try_pyautogui_display()
    assert layout is not None
    assert layout.virtual_width == 1920
    assert layout.virtual_height == 1080
    assert layout.monitors[0].name == "pyautogui-screen"


def test_x11_try_xrandr_display(monkeypatch):
    import subprocess
    from tools.gui.platform.x11 import _try_xrandr_display

    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: "1920x1080\n")
    layout = _try_xrandr_display()
    assert layout is not None
    assert layout.virtual_width == 1920
    assert layout.virtual_height == 1080
    assert layout.monitors[0].name == "xrandr-screen"


def test_x11_single_key_press(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    pressed = []

    class MockPyAutoGUI:
        @staticmethod
        def press(k):
            pressed.append(k)

    monkeypatch.setattr("tools.gui.platform.x11.pyautogui", MockPyAutoGUI)
    backend.emit_key("Return")
    assert pressed == ["return"]


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


def test_x11_backend_screenshot(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    fake_img = object()
    monkeypatch.setattr("tools.gui_ops._take_screenshot_pil", lambda save_path=None: fake_img)
    img = backend.take_screenshot("dummy.png")
    assert img is fake_img


def test_x11_backend_windows(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    fake_windows = [{"id": "0x123", "title": "Test Window", "x": 0, "y": 0, "w": 800, "h": 600}]
    monkeypatch.setattr("tools.gui_ops._get_active_windows", lambda: fake_windows)
    windows = backend.get_active_windows()
    assert windows == fake_windows


def test_x11_backend_input_missing_pyautogui(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    monkeypatch.setattr("tools.gui.platform.x11.pyautogui", None)
    with pytest.raises(RuntimeError, match="pyautogui not available"):
        backend.emit_click(0, 0)
    with pytest.raises(RuntimeError, match="pyautogui not available"):
        backend.emit_type("test")
    with pytest.raises(RuntimeError, match="pyautogui not available"):
        backend.emit_key("enter")
    with pytest.raises(RuntimeError, match="pyautogui not available"):
        backend.emit_scroll(1, 0, 0)
    with pytest.raises(RuntimeError, match="pyautogui not available"):
        backend.emit_drag(0, 0, 10, 10)

