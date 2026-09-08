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
    from tools.gui.platform.wayland import WaylandBackend
    assert platform_pkg.WaylandBackend is WaylandBackend


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
    monkeypatch.setattr("tools.gui_ops._raw_x11_take_screenshot", lambda save_path=None: fake_img)
    img = backend.take_screenshot("dummy.png")
    assert img is fake_img


def test_x11_backend_windows(monkeypatch):
    from tools.gui.platform.x11 import X11Backend
    backend = X11Backend()
    fake_windows = [{"id": "0x123", "title": "Test Window", "x": 0, "y": 0, "w": 800, "h": 600}]
    monkeypatch.setattr("tools.gui_ops._raw_x11_get_active_windows", lambda: fake_windows)
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


# ===========================================================================
# WaylandBackend Tests
# ===========================================================================

def test_wayland_detect_compositor(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend

    # Hyprland via env
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    monkeypatch.delenv("DESKTOP_SESSION", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert WaylandBackend().compositor == "hyprland"

    # Sway via env
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "")
    monkeypatch.setenv("DESKTOP_SESSION", "sway")
    assert WaylandBackend().compositor == "sway"

    # GNOME via env
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.delenv("DESKTOP_SESSION", raising=False)
    assert WaylandBackend().compositor == "gnome"

    # KDE via env
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE-Plasma")
    assert WaylandBackend().compositor == "kde"

    # Hyprland via binary
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.delenv("DESKTOP_SESSION", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/hyprctl" if cmd == "hyprctl" else None)
    assert WaylandBackend().compositor == "hyprland"

    # Sway via binary
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/swaymsg" if cmd == "swaymsg" else None)
    assert WaylandBackend().compositor == "sway"

    # GNOME via binary
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/gnome-screenshot" if cmd == "gnome-screenshot" else None)
    assert WaylandBackend().compositor == "gnome"

    # KDE via binary
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/spectacle" if cmd == "spectacle" else None)
    assert WaylandBackend().compositor == "kde"

    # Generic fallback
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert WaylandBackend().compositor == "generic"


def test_wayland_screenshot_grim_cascade(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    test_img = Image.new("RGB", (100, 100), color="blue")
    backend = WaylandBackend()

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


def test_wayland_screenshot_gnome_screenshot(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    test_img = Image.new("RGB", (200, 150), color="green")
    backend = WaylandBackend()

    # grim not found, gnome-screenshot found
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/gnome-screenshot" if cmd == "gnome-screenshot" else None)

    def mock_run(args, **kwargs):
        dest = args[2]  # gnome-screenshot -f <dest>
        test_img.save(dest)

        class Res:
            returncode = 0

        return Res()

    monkeypatch.setattr("subprocess.run", mock_run)
    img = backend.take_screenshot()
    assert img.size == (200, 150)


def test_wayland_screenshot_spectacle(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    test_img = Image.new("RGB", (300, 200), color="red")
    backend = WaylandBackend()

    # spectacle found
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/spectacle" if cmd == "spectacle" else None)

    def mock_run(args, **kwargs):
        dest = args[4]  # spectacle -b -n -o <dest>
        test_img.save(dest)

        class Res:
            returncode = 0

        return Res()

    monkeypatch.setattr("subprocess.run", mock_run)
    img = backend.take_screenshot()
    assert img.size == (300, 200)


def test_wayland_screenshot_xwayland_fallback(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    backend = WaylandBackend()
    fake_img = Image.new("RGB", (50, 50), color="black")

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr("tools.gui_ops._raw_x11_take_screenshot", lambda save_path=None: fake_img)

    img = backend.take_screenshot()
    assert img is fake_img


def test_wayland_screenshot_blank_image_cascades(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    backend = WaylandBackend()
    fallback_img = Image.new("RGB", (64, 64), color="yellow")

    # grim is found, but produces blank image
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/grim" if cmd == "grim" else None)

    def mock_run(args, **kwargs):
        dest = args[1]
        blank = Image.new("RGB", (10, 10), color="black")
        blank.save(dest)

        class Res:
            returncode = 0

        return Res()

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("tools.gui.platform.wayland._is_blank_screenshot_image", lambda path: True)
    monkeypatch.setattr("tools.gui_ops._raw_x11_take_screenshot", lambda save_path=None: fallback_img)

    img = backend.take_screenshot()
    assert img is fallback_img



def test_wayland_screenshot_save_path(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    from PIL import Image

    test_img = Image.new("RGB", (100, 100), color="blue")
    save_dest = str(tmp_path / "saved.png")
    backend = WaylandBackend()

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/grim" if cmd == "grim" else None)

    def mock_run(args, **kwargs):
        dest = args[1]
        assert dest == save_dest
        test_img.save(dest)

        class Res:
            returncode = 0

        return Res()

    monkeypatch.setattr("subprocess.run", mock_run)

    img = backend.take_screenshot(save_path=save_dest)
    assert os.path.exists(save_dest)
    assert img.size == (100, 100)


def test_wayland_input_ydotool(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    commands = []
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ydotool" if cmd == "ydotool" else None)
    monkeypatch.setattr("subprocess.run", lambda args, **k: commands.append(args))

    backend.emit_click(150, 250, "left", 1)
    backend.emit_click(150, 250, "right", 2)
    backend.emit_click(150, 250, "middle", 1)
    backend.emit_type("hello")
    backend.emit_key("Return")
    backend.emit_scroll(3, 100, 100)

    assert ["ydotool", "mousemove", "--absolute", "150", "250"] in commands
    assert ["ydotool", "click", "0xC0"] in commands
    assert ["ydotool", "click", "0xC1"] in commands
    assert ["ydotool", "click", "0xC2"] in commands
    assert ["ydotool", "type", "hello"] in commands
    assert ["ydotool", "key", "Return"] in commands
    assert ["ydotool", "mousemove", "-w", "3"] in commands


def test_wayland_input_wtype(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    commands = []
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/wtype" if cmd == "wtype" else None)
    monkeypatch.setattr("subprocess.run", lambda args, **k: commands.append(args))

    backend.emit_type("test typing")
    backend.emit_key("Return")
    backend.emit_key("Ctrl+Shift+T")

    assert ["wtype", "test typing"] in commands
    assert ["wtype", "-k", "return"] in commands
    assert ["wtype", "-M", "ctrl", "-M", "shift", "-k", "t", "-m", "shift", "-m", "ctrl"] in commands


def test_wayland_input_pyautogui_fallback(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    clicked = []
    typed = []
    pressed = []
    hotkeyed = []
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
        def press(key):
            pressed.append(key)

        @staticmethod
        def hotkey(*keys):
            hotkeyed.append(keys)

        @staticmethod
        def moveTo(x, y):
            pass

        @staticmethod
        def scroll(clicks):
            scrolled.append(clicks)

        @staticmethod
        def dragTo(x, y, duration=0.5):
            dragged.append((x, y, duration))

    monkeypatch.setattr("tools.gui.platform.wayland.pyautogui", MockPyAutoGUI)

    backend.emit_click(10, 20, "left", 1)
    backend.emit_type("fallback text", interval=0.05)
    backend.emit_key("Escape")
    backend.emit_key("Ctrl+C")
    backend.emit_scroll(-2, 50, 50)
    backend.emit_drag(10, 20, 100, 200, duration=0.3)

    assert clicked == [(10, 20, "left", 1)]
    assert typed == [("fallback text", 0.05)]
    assert pressed == ["escape"]
    assert hotkeyed == [("ctrl", "c")]
    assert scrolled == [-2]
    assert dragged == [(100, 200, 0.3)]


def test_wayland_input_ydotool_drag_without_pyautogui(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    commands = []
    monkeypatch.setattr("tools.gui.platform.wayland.pyautogui", None)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ydotool" if cmd == "ydotool" else None)
    monkeypatch.setattr("subprocess.run", lambda args, **k: commands.append(args))

    backend.emit_drag(10, 20, 100, 200)
    assert ["ydotool", "mousemove", "--absolute", "10", "20"] in commands
    assert ["ydotool", "click", "0x40"] in commands
    assert ["ydotool", "mousemove", "--absolute", "100", "200"] in commands
    assert ["ydotool", "click", "0x80"] in commands


def test_wayland_input_ydotool_drag_fallback_to_pyautogui(monkeypatch):
    import subprocess
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ydotool" if cmd == "ydotool" else None)

    def mock_run_fail(*args, **kwargs):
        raise subprocess.SubprocessError("ydotoold not running")

    monkeypatch.setattr("subprocess.run", mock_run_fail)

    dragged = []

    class MockPyAutoGUI:
        @staticmethod
        def moveTo(x, y):
            pass

        @staticmethod
        def dragTo(x, y, duration=0.5):
            dragged.append((x, y, duration))

    monkeypatch.setattr("tools.gui.platform.wayland.pyautogui", MockPyAutoGUI)

    backend.emit_drag(10, 20, 100, 200, duration=0.4)
    assert dragged == [(100, 200, 0.4)]


def test_wayland_input_missing_all_raises(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr("tools.gui.platform.wayland.pyautogui", None)

    with pytest.raises(RuntimeError, match="neither ydotool nor pyautogui available"):
        backend.emit_click(0, 0)
    with pytest.raises(RuntimeError, match="neither wtype, ydotool, nor pyautogui available"):
        backend.emit_type("fail")
    with pytest.raises(RuntimeError, match="no suitable input injector"):
        backend.emit_key("enter")
    with pytest.raises(RuntimeError, match="Wayland scroll failed"):
        backend.emit_scroll(1, 0, 0)
    with pytest.raises(RuntimeError, match="Wayland drag failed"):
        backend.emit_drag(0, 0, 10, 10)


def test_wayland_active_windows_hyprctl(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    backend = WaylandBackend()

    sample_json = '[{"address": "0x123", "at": [100, 200], "size": [800, 600], "title": "Editor"}]'
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/hyprctl" if cmd == "hyprctl" else None)
    monkeypatch.setattr("subprocess.check_output", lambda args, **k: sample_json)

    windows = backend.get_active_windows()
    assert len(windows) == 1
    assert windows[0]["title"] == "Editor"
    assert windows[0]["x"] == 100
    assert windows[0]["y"] == 200
    assert windows[0]["w"] == 800
    assert windows[0]["h"] == 600
    assert windows[0]["id"] == "0x123"


def test_wayland_active_windows_sway(monkeypatch):
    import json
    from tools.gui.platform.wayland import WaylandBackend

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "sway")
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/swaymsg" if cmd == "swaymsg" else None)
    backend = WaylandBackend()

    tree_data = {
        "name": "root",
        "type": "root",
        "nodes": [
            {
                "name": "Terminal",
                "type": "con",
                "id": 42,
                "rect": {"x": 0, "y": 0, "width": 960, "height": 1080},
                "nodes": [],
            },
            {
                "name": "workspace 1",
                "type": "workspace",
                "nodes": [],
                "floating_nodes": [
                    {
                        "name": "FloatWin",
                        "type": "floating_con",
                        "id": 99,
                        "rect": {"x": 200, "y": 150, "width": 500, "height": 400},
                        "nodes": [],
                    }
                ],
            },
        ],
    }

    monkeypatch.setattr("subprocess.check_output", lambda args, **k: json.dumps(tree_data))

    windows = backend.get_active_windows()
    assert len(windows) == 2
    assert windows[0]["title"] == "Terminal"
    assert windows[0]["id"] == "42"
    assert windows[0]["w"] == 960
    assert windows[1]["title"] == "FloatWin"
    assert windows[1]["id"] == "99"
    assert windows[1]["w"] == 500


def test_wayland_active_windows_sway_with_none_nodes(monkeypatch):
    import json
    from tools.gui.platform.wayland import WaylandBackend

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "sway")
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/swaymsg" if cmd == "swaymsg" else None)
    backend = WaylandBackend()

    tree_data = {
        "name": "root",
        "type": "root",
        "nodes": [
            {
                "name": "Terminal",
                "type": "con",
                "id": 42,
                "rect": {"x": 0, "y": 0, "width": 800, "height": 600},
                "nodes": None,
                "floating_nodes": None,
            }
        ],
        "floating_nodes": None,
    }
    monkeypatch.setattr("subprocess.check_output", lambda args, **k: json.dumps(tree_data))

    windows = backend.get_active_windows()
    assert len(windows) == 1
    assert windows[0]["title"] == "Terminal"


def test_wayland_active_windows_atspi(monkeypatch):
    from types import SimpleNamespace
    from tools.gui.platform.wayland import WaylandBackend

    backend = WaylandBackend()
    backend.compositor = "gnome"
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    class MockRole:
        FRAME = 1
        WINDOW = 2
        DIALOG = 3
        PANEL = 4

    class MockExtents:
        def __init__(self, x, y, width, height):
            self.x = x
            self.y = y
            self.width = width
            self.height = height

    class MockWinNode:
        def __init__(self, name, role, ext):
            self._name = name
            self._role = role
            self._ext = ext

        def get_role(self):
            return self._role

        def get_name(self):
            return self._name

        def get_extents(self, coord_type):
            return self._ext

    class MockAppNode:
        def __init__(self, children):
            self._children = children

        def get_child_count(self):
            return len(self._children)

        def get_child_at_index(self, idx):
            return self._children[idx]

    class MockDesktop:
        def __init__(self, apps):
            self._apps = apps

        def get_child_count(self):
            return len(self._apps)

        def get_child_at_index(self, idx):
            return self._apps[idx]

    win1 = MockWinNode("Gnome App", MockRole.FRAME, MockExtents(50, 60, 800, 600))
    win2 = MockWinNode("Tiny", MockRole.FRAME, MockExtents(0, 0, 5, 5))  # too small
    app1 = MockAppNode([win1, win2])
    desktop = MockDesktop([app1])

    mock_atspi = SimpleNamespace(
        get_desktop=lambda idx: desktop,
        Role=MockRole,
        CoordType=SimpleNamespace(SCREEN=0),
    )
    monkeypatch.setattr("tools.gui.platform.wayland.Atspi", mock_atspi)

    windows = backend.get_active_windows()
    assert len(windows) == 1
    assert windows[0]["title"] == "Gnome App"
    assert windows[0]["x"] == 50
    assert windows[0]["y"] == 60
    assert windows[0]["w"] == 800
    assert windows[0]["h"] == 600
    assert windows[0]["id"] == "0_0"


def test_wayland_active_windows_fallback(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()
    backend.compositor = "generic"
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr("tools.gui.platform.wayland.Atspi", None)

    fake_windows = [{"id": "fallback_1", "title": "Fallback Win", "x": 0, "y": 0, "w": 640, "h": 480}]
    monkeypatch.setattr("tools.gui_ops._raw_x11_get_active_windows", lambda: fake_windows)

    windows = backend.get_active_windows()
    assert windows == fake_windows



def test_wayland_display_layout_hyprctl(monkeypatch):
    import json
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    sample_monitors = [
        {"name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080, "focused": True},
        {"name": "HDMI-A-1", "x": 1920, "y": 0, "width": 1920, "height": 1080, "focused": False},
    ]
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/hyprctl" if cmd == "hyprctl" else None)
    monkeypatch.setattr("subprocess.check_output", lambda args, **k: json.dumps(sample_monitors))

    layout = backend.get_display_layout()
    assert len(layout.monitors) == 2
    assert layout.virtual_width == 3840
    assert layout.virtual_height == 1080
    assert layout.monitors[0].is_primary is True
    assert layout.monitors[1].is_primary is False


def test_wayland_display_layout_sway(monkeypatch):
    import json
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    sample_outputs = [
        {"name": "eDP-1", "rect": {"x": 0, "y": 0, "width": 2560, "height": 1440}, "primary": True},
    ]
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/swaymsg" if cmd == "swaymsg" else None)
    monkeypatch.setattr("subprocess.check_output", lambda args, **k: json.dumps(sample_outputs))

    layout = backend.get_display_layout()
    assert len(layout.monitors) == 1
    assert layout.virtual_width == 2560
    assert layout.virtual_height == 1440
    assert layout.monitors[0].name == "eDP-1"
    assert layout.monitors[0].is_primary is True


def test_wayland_display_layout_drm(monkeypatch, tmp_path):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    monkeypatch.setattr("shutil.which", lambda cmd: None)

    fake_drm_mode = tmp_path / "modes"
    fake_drm_mode.write_text("1920x1200\n1680x1050\n")

    monkeypatch.setattr("glob.glob", lambda pattern: [str(fake_drm_mode)])

    layout = backend.get_display_layout()
    assert layout.virtual_width == 1920
    assert layout.virtual_height == 1200
    assert layout.monitors[0].name == "drm-monitor"
    assert layout.monitors[0].is_primary is True


def test_wayland_display_layout_fallback(monkeypatch):
    from tools.gui.platform.wayland import WaylandBackend
    backend = WaylandBackend()

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr("glob.glob", lambda pattern: [])
    monkeypatch.setenv("GUI_DEFAULT_WIDTH", "1366")
    monkeypatch.setenv("GUI_DEFAULT_HEIGHT", "768")

    layout = backend.get_display_layout()
    assert layout.virtual_width == 1366
    assert layout.virtual_height == 768
    assert layout.monitors[0].name == "default-screen"
    assert layout.monitors[0].is_primary is True


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


def test_backend_delegation_errors(monkeypatch):
    import tools.gui.backend as backend

    class FailingBackend:
        def emit_click(self, *a, **k):
            raise ValueError("click error")

        def emit_type(self, *a, **k):
            raise ValueError("type error")

        def emit_key(self, *a, **k):
            raise ValueError("key error")

        def emit_scroll(self, *a, **k):
            raise ValueError("scroll error")

        def emit_drag(self, *a, **k):
            raise ValueError("drag error")

    monkeypatch.setattr("tools.gui.backend.get_platform_backend", lambda: FailingBackend())

    with pytest.raises(RuntimeError, match="Backend emit_click failed: click error"):
        backend.emit_click(0, 0)

    with pytest.raises(RuntimeError, match="Backend emit_type failed: type error"):
        backend.emit_type("test")

    with pytest.raises(RuntimeError, match="Backend emit_key failed: key error"):
        backend.emit_key("Return")

    with pytest.raises(RuntimeError, match="Backend emit_scroll failed: scroll error"):
        backend.emit_scroll(1, 0, 0)

    with pytest.raises(RuntimeError, match="Backend emit_drag failed: drag error"):
        backend.emit_drag(0, 0, 1, 1)


def test_gui_ops_delegation_to_platform_backend(monkeypatch):
    import tools.gui_ops as gui_ops
    from tools.gui.platform.factory import reset_platform_backend
    from PIL import Image

    reset_platform_backend()
    calls = []
    fake_img = Image.new("RGB", (100, 100), color="blue")
    fake_windows = [{"id": "w1", "title": "Mock Win", "x": 10, "y": 10, "w": 500, "h": 400}]

    class MockPlatformBackend:
        def take_screenshot(self, save_path=None):
            calls.append(("take_screenshot", save_path))
            return fake_img

        def get_active_windows(self):
            calls.append(("get_active_windows",))
            return fake_windows

    mock_backend = MockPlatformBackend()
    monkeypatch.setattr("tools.gui.platform.factory._CACHED_BACKEND", mock_backend)

    # Verify _take_screenshot_pil delegates to active backend
    img = gui_ops._take_screenshot_pil("test.png")
    assert img is fake_img
    assert calls[0] == ("take_screenshot", "test.png")

    # Verify _get_active_windows delegates to active backend
    wins = gui_ops._get_active_windows()
    assert wins == fake_windows
    assert calls[1] == ("get_active_windows",)

    # Verify gui_screenshot delegates to active backend
    res = gui_ops.gui_screenshot("test_out.png")
    assert "Screenshot saved to test_out.png" in res
    assert calls[2] == ("take_screenshot", "test_out.png")
    if os.path.exists("test_out.png"):
        os.remove("test_out.png")


def test_engine_capture_state_delegates_to_platform_backend(monkeypatch):
    from tools.gui import engine
    from tools.gui.config import GUIConfig
    from tools.gui.models import DisplayLayout
    from tools.gui.platform.factory import reset_platform_backend
    from PIL import Image

    reset_platform_backend()
    calls = []
    fake_img = Image.new("RGB", (100, 100), color="blue")
    fake_windows = [{"id": "w1", "title": "Mock Window", "x": 0, "y": 0, "w": 800, "h": 600}]

    class MockPlatformBackend:
        def get_display_layout(self):
            calls.append("get_display_layout")
            return DisplayLayout(monitors=[], virtual_width=1920, virtual_height=1080)

        def take_screenshot(self, save_path=None):
            calls.append("take_screenshot")
            return fake_img

        def get_active_windows(self):
            calls.append("get_active_windows")
            return fake_windows

    mock_backend = MockPlatformBackend()
    monkeypatch.setattr("tools.gui.platform.factory._CACHED_BACKEND", mock_backend)
    monkeypatch.setattr("tools.gui.engine.get_atspi_elements", lambda: [])
    monkeypatch.setattr("tools.gui.engine.get_ocr_elements", lambda img: [])

    state = engine.capture_state(GUIConfig.load())

    assert "get_display_layout" in calls
    assert "take_screenshot" in calls
    assert "get_active_windows" in calls
    assert len(state.windows) == 1
    assert state.windows[0].title == "Mock Window"



def test_blank_screenshot_detection_in_memory():
    from PIL import Image
    from tools.gui_ops import _is_blank_screenshot_image

    # Pure black image in memory
    blank_img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    assert _is_blank_screenshot_image(blank_img) is True

    # Image with content
    non_blank_img = Image.new("RGB", (100, 100), color=(128, 200, 50))
    assert _is_blank_screenshot_image(non_blank_img) is False


def test_raw_x11_take_screenshot_blank_in_memory(monkeypatch):
    from PIL import Image
    import tools.gui_ops as gui_ops

    blank_img = Image.new("RGB", (50, 50), color=(0, 0, 0))
    monkeypatch.setattr("tools.gui_ops.pyautogui", type("MockPAG", (), {"screenshot": staticmethod(lambda: blank_img)}))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no scrot")))

    with pytest.raises(RuntimeError, match="blank"):
        gui_ops._raw_x11_take_screenshot(save_path=None)




