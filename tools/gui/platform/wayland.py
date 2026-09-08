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
        if "hyprland" in desktop or "hyprland" in session:
            return "hyprland"
        if "sway" in desktop or "sway" in session:
            return "sway"
        if "gnome" in desktop or "gnome" in session:
            return "gnome"
        if "kde" in desktop or "plasma" in desktop:
            return "kde"
        if shutil.which("hyprctl"):
            return "hyprland"
        if shutil.which("swaymsg"):
            return "sway"
        if shutil.which("gnome-screenshot"):
            return "gnome"
        if shutil.which("spectacle"):
            return "kde"
        return "generic"

    # -----------------------------------------------------------------------
    # Screen Capture Cascade
    # -----------------------------------------------------------------------
    def take_screenshot(self, save_path: Optional[str] = None) -> Image.Image:
        """Capture screen using grim, gnome-screenshot, portal, or XWayland fallback."""
        if save_path:
            temp_dest = save_path
        else:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_dest = tmp.name

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
        if not save_path:
            try:
                os.remove(temp_dest)
            except Exception:
                pass
        from tools.gui_ops import _raw_x11_take_screenshot
        return _raw_x11_take_screenshot(save_path)


    def _finalize_image(self, temp_dest: str, save_path: Optional[str]) -> Image.Image:
        try:
            img = Image.open(temp_dest)
            img.load()
            return img
        finally:
            if not save_path:
                try:
                    os.remove(temp_dest)
                except Exception:
                    pass

    # -----------------------------------------------------------------------
    # Input Simulation Cascade
    # -----------------------------------------------------------------------
    def emit_click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> None:
        btn_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
        btn_code = btn_map.get(button.lower(), "0xC0")

        if shutil.which("ydotool"):
            try:
                if x is not None and y is not None:
                    subprocess.run(["ydotool", "mousemove", "--absolute", str(x), str(y)], check=True, timeout=2)
                for _ in range(clicks):
                    subprocess.run(["ydotool", "click", btn_code], check=True, timeout=2)
                return
            except Exception as e:
                audit_log("wayland_emit_click", {"error": str(e)}, "warning", "ydotool failed, trying fallback")

        # Fallback to PyAutoGUI
        if pyautogui is not None:
            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
        else:
            raise RuntimeError("Wayland click failed: neither ydotool nor pyautogui available")

    def emit_move(self, x: int, y: int, duration: float = 0.0) -> None:
        if shutil.which("ydotool"):
            try:
                subprocess.run(["ydotool", "mousemove", "--absolute", str(x), str(y)], check=True, timeout=2)
                return
            except Exception as e:
                audit_log("wayland_emit_move", {"error": str(e)}, "warning", "ydotool failed, trying fallback")

        if pyautogui is not None:
            pyautogui.moveTo(x, y, duration=duration)
            return

        raise RuntimeError("Wayland move failed: neither ydotool nor pyautogui available")

    def emit_type(self, text: str, interval: float = 0.0) -> None:
        if shutil.which("wtype"):
            try:
                subprocess.run(["wtype", "--", text], check=True, timeout=3)
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
        if shutil.which("ydotool"):
            try:
                # Click down, move, click up
                subprocess.run(["ydotool", "mousemove", "--absolute", str(start_x), str(start_y)], check=True, timeout=2)
                subprocess.run(["ydotool", "click", "0x40"], check=True, timeout=2) # left button down
                subprocess.run(["ydotool", "mousemove", "--absolute", str(end_x), str(end_y)], check=True, timeout=2)
                subprocess.run(["ydotool", "click", "0x80"], check=True, timeout=2) # left button up
                return
            except Exception as e:
                audit_log("wayland_emit_drag", {"error": str(e)}, "warning", "ydotool failed, trying fallback")

        if pyautogui is not None:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration)
            return

        raise RuntimeError("Wayland drag failed: neither ydotool nor pyautogui available")

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
        from tools.gui_ops import _raw_x11_get_active_windows
        return _raw_x11_get_active_windows()


    def _extract_sway_windows(self, node: dict) -> List[Dict[str, Any]]:
        windows = []
        if node.get("name") and node.get("type") in ("con", "floating_con") and (node.get("nodes") or []) == []:
            rect = node.get("rect", {})
            windows.append({
                "id": str(node.get("id", "")),
                "x": int(rect.get("x", 0)),
                "y": int(rect.get("y", 0)),
                "w": int(rect.get("width", 0)),
                "h": int(rect.get("height", 0)),
                "title": str(node.get("name", "")),
            })
        for child in node.get("nodes") or []:
            windows.extend(self._extract_sway_windows(child))
        for child in node.get("floating_nodes") or []:
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
                    try:
                        role = win_node.get_role()
                        if role in (Atspi.Role.FRAME, Atspi.Role.WINDOW, Atspi.Role.DIALOG):
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
                status_file = os.path.join(os.path.dirname(mode_file), "status")
                if os.path.exists(status_file):
                    try:
                        with open(status_file, "r") as sf:
                            if sf.read().strip().lower() != "connected":
                                continue
                    except Exception:
                        continue
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
