import json
import os
import re
import subprocess
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.registry import register_tool
from tools.base import YOLO_ARTIFACTS, audit_log

"""
GUI Perception & Interaction Engine — UI-TARS-inspired.

Approach borrowed from ByteDance's UI-TARS:
  1. Perceive-before-act: always screenshot & OCR before interacting
  2. Set-of-Mark (SoM) overlay: draw numbered bounding boxes on detected elements
  3. Grounded actions: click by element description, not blind coordinates
  4. State-transition detection: diff before/after screenshots to confirm changes

Dependencies:
  pip:  pyautogui, pytesseract, opencv-python-headless, pillow
  sys:  tesseract-ocr  (apt install tesseract-ocr  /  pacman -S tesseract)
"""

# --------------- optional imports with graceful degradation ---------------
try:
    import Xlib.xauth
    import Xlib.error
    orig_get_best_auth = Xlib.xauth.Xauthority.get_best_auth
    def patched_get_best_auth(self, family, address, dispno, types=(b"MIT-MAGIC-COOKIE-1",)):
        try:
            return orig_get_best_auth(self, family, address, dispno, types)
        except Xlib.error.XNoAuthError:
            if dispno != '':
                try:
                    return orig_get_best_auth(self, family, address, '', types)
                except Xlib.error.XNoAuthError:
                    pass
            raise
    Xlib.xauth.Xauthority.get_best_auth = patched_get_best_auth
except Exception:
    pass

try:
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = False
except Exception:
    pyautogui = None  # type: ignore

try:
    import pytesseract  # type: ignore
except ImportError:
    pytesseract = None  # type: ignore

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore
    np = None  # type: ignore

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore

try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
except (ImportError, ValueError):
    Atspi = None



# ======================================================================
# Constants
# ======================================================================
_SOM_COLORS = [
    (255, 0, 0),
    (0, 200, 0),
    (0, 100, 255),
    (255, 165, 0),
    (148, 0, 211),
    (0, 206, 209),
    (255, 20, 147),
    (50, 205, 50),
    (255, 215, 0),
    (30, 144, 255),
    (220, 20, 60),
    (0, 128, 128),
]

_ARTIFACTS_DIR = YOLO_ARTIFACTS


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _check_pyautogui():
    if pyautogui is None:
        raise ImportError("pyautogui is not installed. `pip install pyautogui pillow`")


def _check_ocr():
    if pytesseract is None:
        raise ImportError("pytesseract is not installed. `pip install pytesseract`")
    # Check that the tesseract binary exists
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        raise ImportError(
            "tesseract-ocr binary not found on PATH. "
            "Install it: `sudo apt install tesseract-ocr` or `sudo pacman -S tesseract`"
        )


# ======================================================================
# 1) Original low-level primitives  (unchanged API)
# ======================================================================


@register_tool()
def gui_mouse_move(x: int, y: int, duration: float = 0.0) -> str:
    """Move the mouse cursor to a specific (x, y) coordinate."""
    _check_pyautogui()
    try:
        pyautogui.moveTo(x, y, duration=duration)
        audit_log("gui_mouse_move", {"x": x, "y": y}, "success", "Mouse moved")
        return f"Moved mouse to ({x}, {y})"
    except Exception as e:
        audit_log("gui_mouse_move", {"x": x, "y": y}, "error", str(e))
        return f"Error: {e}"


@register_tool()
def gui_mouse_click(button: str = "left", clicks: int = 1) -> str:
    """Click the mouse."""
    _check_pyautogui()
    try:
        pyautogui.click(button=button, clicks=clicks)
        audit_log(
            "gui_mouse_click",
            {"button": button, "clicks": clicks},
            "success",
            "Mouse clicked",
        )
        return f"Clicked {button} button {clicks} time(s)"
    except Exception as e:
        audit_log(
            "gui_mouse_click", {"button": button, "clicks": clicks}, "error", str(e)
        )
        return f"Error: {e}"


@register_tool()
def gui_type_text(text: str, interval: float = 0.0) -> str:
    """Type a string of characters."""
    _check_pyautogui()
    try:
        pyautogui.write(text, interval=interval)
        audit_log("gui_type_text", {"text_len": len(text)}, "success", "Text typed")
        return f"Typed text of length {len(text)}"
    except Exception as e:
        audit_log("gui_type_text", {}, "error", str(e))
        return f"Error: {e}"


@register_tool()
def gui_press_key(key: str) -> str:
    """Press a single key or a combination (e.g., 'enter', 'ctrl+c')."""
    _check_pyautogui()
    try:
        if "+" in key:
            keys = key.split("+")
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
        audit_log("gui_press_key", {"key": key}, "success", "Key pressed")
        return f"Pressed key(s): {key}"
    except Exception as e:
        audit_log("gui_press_key", {"key": key}, "error", str(e))
        return f"Error: {e}"


@register_tool()
def gui_screenshot(save_path: str = "screenshot.png") -> str:
    """Take a screenshot using scrot as a fallback if pyautogui fails on Linux."""
    try:
        pyautogui.screenshot(save_path)
        audit_log(
            "gui_screenshot",
            {"path": save_path, "method": "pyautogui"},
            "success",
            "Screenshot taken",
        )
        return f"Screenshot saved to {save_path}"
    except Exception:
        try:
            subprocess.run(["scrot", save_path], check=True)
            audit_log(
                "gui_screenshot",
                {"path": save_path, "method": "scrot"},
                "success",
                "Screenshot taken",
            )
            return f"Screenshot saved to {save_path} (via scrot)"
        except Exception as e:
            audit_log("gui_screenshot", {"path": save_path}, "error", str(e))
            return f"Error taking screenshot: {e}"


@register_tool()
def gui_send_screenshot() -> str:
    """Take a screenshot of the current screen and send it directly to the UI as an artifact."""
    try:
        ts = _ts()
        path = _ARTIFACTS_DIR / f"gui_share_{ts}.png"
        gui_screenshot(str(path))
        return f"__SEND_FILE__:{path.resolve()}"
    except Exception as e:
        return f"Error sending screenshot: {e}"


@register_tool()
def gui_get_screen_size() -> str:
    """Get the screen resolution. Uses xrandr as fallback."""
    _check_pyautogui()
    try:
        width, height = pyautogui.size()
        return f"Screen size is {width}x{height}"
    except Exception:
        try:
            output = subprocess.check_output(
                "xrandr | grep '*' | awk '{print $1}'", shell=True, text=True
            )
            res = output.strip().split("\n")[0]
            return f"Screen size is {res} (via xrandr)"
        except Exception as e:
            return f"Error: {e}"


# ======================================================================
# 2) Perception helpers (internal)
# ======================================================================


def _take_screenshot_pil(save_path: Optional[str] = None) -> "Image.Image":
    """Capture the screen and return a PIL Image."""
    _check_pyautogui()
    if Image is None:
        raise ImportError("Pillow is not installed. `pip install pillow`")
    
    try:
        img = pyautogui.screenshot()
        if save_path:
            img.save(save_path)
        return img
    except Exception as e:
        if os.name != "nt":
            import tempfile
            temp_path = save_path or os.path.join(tempfile.gettempdir(), f"screenshot_{int(time.time())}.png")
            try:
                subprocess.run(["scrot", temp_path], check=True)
                img = Image.open(temp_path)
                img.load()
                if not save_path:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return img
            except Exception as scrot_err:
                raise RuntimeError(f"Screenshot failed. PyAutoGUI error: {e}. Scrot error: {scrot_err}")
        else:
            raise e


def _ocr_image(
    pil_img: "Image.Image",
    region: Optional[Tuple[int, int, int, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Run Tesseract OCR on a PIL Image and return a list of detected elements.
    Each element: {id, text, type, bbox: [x, y, w, h], center: [cx, cy]}
    """
    _check_ocr()

    if region:
        pil_img = pil_img.crop(
            (region[0], region[1], region[0] + region[2], region[1] + region[3])
        )

    # Use pytesseract to get bounding-box-level data
    data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
    if not data or "text" not in data:
        return []

    elements: List[Dict[str, Any]] = []
    n = len(data["text"])
    idx = 0

    # Group words into lines for more meaningful elements
    current_line: List[str] = []
    current_bbox: Optional[List[int]] = None
    current_line_num = -1
    current_block_num = -1

    def _flush_line():
        """Flush accumulated words into an element."""
        nonlocal idx, current_line, current_bbox, current_line_num, current_block_num
        if current_line and current_bbox:
            merged_text = " ".join(current_line)
            if merged_text.strip():
                bx, by, bw, bh = current_bbox
                if region:
                    bx += region[0]
                    by += region[1]
                elements.append(
                    {
                        "id": idx,
                        "text": merged_text,
                        "type": _classify_element(merged_text),
                        "bbox": [bx, by, bw, bh],
                        "center": [bx + bw // 2, by + bh // 2],
                    }
                )
                idx += 1
        current_line = []
        current_bbox = None
        current_line_num = -1
        current_block_num = -1

    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = int(data["conf"][i]) if str(data["conf"][i]) != "-1" else 0
        line_num = data["line_num"][i]
        block_num = data["block_num"][i]
        x, y, w, h = (
            data["left"][i],
            data["top"][i],
            data["width"][i],
            data["height"][i],
        )

        if conf < 30 or not text:
            _flush_line()
            continue

        # New line/block or fresh start after flush → begin a new element
        if (
            block_num != current_block_num
            or line_num != current_line_num
            or current_bbox is None
        ):
            _flush_line()
            current_line = [text]
            current_bbox = [x, y, w, h]
            current_line_num = line_num
            current_block_num = block_num
        else:
            # Same line — extend
            current_line.append(text)
            new_right = max(current_bbox[0] + current_bbox[2], x + w)
            new_bottom = max(current_bbox[1] + current_bbox[3], y + h)
            current_bbox[0] = min(current_bbox[0], x)
            current_bbox[1] = min(current_bbox[1], y)
            current_bbox[2] = new_right - current_bbox[0]
            current_bbox[3] = new_bottom - current_bbox[1]

    # Flush last line
    _flush_line()

    return elements


def _get_atspi_elements(region: Optional[Tuple[int, int, int, int]] = None) -> List[Dict[str, Any]]:
    """Traverse the AT-SPI2 accessibility tree to find interactive UI elements."""
    if Atspi is None:
        return []
    
    try:
        desktop = Atspi.get_desktop(0)
    except Exception:
        return []
        
    if not desktop:
        return []

    elements = []
    idx = 0

    def traverse(node):
        nonlocal idx
        if not node:
            return

        try:
            # Check defunct
            state = node.get_state_set()
            if state.contains(Atspi.StateType.DEFUNCT):
                return
                
            # Filter for interactive or text roles
            role = node.get_role()
            role_name = node.get_role_name()
            
            # Extract basic info
            name = node.get_name() or ""
            
            # We care about things we can click or read
            interesting_roles = [
                Atspi.Role.PUSH_BUTTON, Atspi.Role.MENU_ITEM, Atspi.Role.TEXT, 
                Atspi.Role.ENTRY, Atspi.Role.LINK, Atspi.Role.CHECK_BOX, 
                Atspi.Role.RADIO_BUTTON, Atspi.Role.COMBO_BOX, Atspi.Role.LABEL,
                Atspi.Role.PAGE_TAB, Atspi.Role.TABLE_CELL
            ]
            
            is_interesting = role in interesting_roles
            has_text = bool(name.strip())
            
            if (is_interesting or has_text) and state.contains(Atspi.StateType.VISIBLE):
                extents = node.get_extents(Atspi.CoordType.SCREEN)
                x, y, w, h = extents.x, extents.y, extents.width, extents.height
                
                # Check region
                if w > 0 and h > 0:
                    in_region = True
                    if region:
                        rx, ry, rw, rh = region
                        if x + w < rx or x > rx + rw or y + h < ry or y > ry + rh:
                            in_region = False
                            
                    if in_region:
                        elem_type = "button_or_menu" if role in [Atspi.Role.PUSH_BUTTON, Atspi.Role.MENU_ITEM] else ("text" if role == Atspi.Role.TEXT else role_name)
                        display_text = name.strip() or role_name
                        elements.append({
                            "id": idx,
                            "text": display_text,
                            "type": elem_type,
                            "bbox": [x, y, w, h],
                            "center": [x + w // 2, y + h // 2],
                        })
                        idx += 1
                        
            # Traverse children
            for i in range(node.get_child_count()):
                traverse(node.get_child_at_index(i))
                
        except Exception:
            pass
            
    traverse(desktop)
    return elements


def _classify_element(text: str) -> str:
    """Heuristic element type classification."""
    t = text.strip().lower()
    if not t:
        return "unknown"
    # Single word, title case → likely button or menu item
    if len(t.split()) == 1 and text[0].isupper():
        return "button_or_menu"
    # URL-like
    if re.match(r"https?://", t) or ".com" in t or ".org" in t:
        return "url"
    # Path-like
    if "/" in t and " " not in t:
        return "path"
    # Numeric
    if re.match(r"^[\d.,:%]+$", t):
        return "numeric"
    # Short capitalized phrase → label/heading
    if len(t) < 40 and text[0].isupper():
        return "label"
    return "text"


def _get_active_windows() -> List[Dict[str, Any]]:
    """Query the window manager for the list of visible windows."""
    windows = []
    if os.name == "nt":
        try:
            import pygetwindow as gw  # type: ignore

            for w in gw.getAllWindows():
                if w.visible and w.title:
                    windows.append(
                        {
                            "id": str(w._hWnd),
                            "x": w.left,
                            "y": w.top,
                            "w": w.width,
                            "h": w.height,
                            "title": w.title,
                        }
                    )
        except ImportError:
            # If pygetwindow is missing, we can't do much on Windows without ctypes
            pass
        except Exception:
            pass
        return windows

    try:
        # Use wmctrl for window list (works on most X11 desktops)
        out = subprocess.check_output(["wmctrl", "-l", "-G"], text=True, timeout=3)
        for line in out.strip().splitlines():
            parts = line.split(None, 8)
            if len(parts) >= 9:
                windows.append(
                    {
                        "id": parts[0],
                        "x": int(parts[2]),
                        "y": int(parts[3]),
                        "w": int(parts[4]),
                        "h": int(parts[5]),
                        "title": parts[8],
                    }
                )
    except Exception:
        # Fallback: xdotool
        try:
            out = subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                text=True,
                timeout=3,
            )
            for wid in out.strip().splitlines()[:20]:
                try:
                    name = subprocess.check_output(
                        ["xdotool", "getwindowname", wid], text=True, timeout=1
                    ).strip()
                    geo = subprocess.check_output(
                        ["xdotool", "getwindowgeometry", "--shell", wid],
                        text=True,
                        timeout=1,
                    )
                    vals = dict(re.findall(r"(\w+)=(\d+)", geo))
                    windows.append(
                        {
                            "id": wid,
                            "x": int(vals.get("X", 0)),
                            "y": int(vals.get("Y", 0)),
                            "w": int(vals.get("WIDTH", 0)),
                            "h": int(vals.get("HEIGHT", 0)),
                            "title": name,
                        }
                    )
                except Exception:
                    pass
        except Exception:
            pass
    return windows


def _draw_som_overlay(
    pil_img: "Image.Image",
    elements: List[Dict[str, Any]],
    save_path: str,
) -> str:
    """Draw Set-of-Mark (SoM) numbered bounding boxes on the image and save."""
    if ImageDraw is None:
        return ""

    overlay = pil_img.copy()
    draw = ImageDraw.Draw(overlay)

    # Try to load a bold font
    font = None
    font_paths = []
    if os.name == "nt":
        font_paths = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ]
    else:
        font_paths = [
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]

    for p in font_paths:
        try:
            font = ImageFont.truetype(p, 14)
            break
        except Exception:
            continue

    if font is None:
        font = ImageFont.load_default()  # type: ignore

    for elem in elements:
        color = _SOM_COLORS[elem["id"] % len(_SOM_COLORS)]
        bx, by, bw, bh = elem["bbox"]
        # Draw rectangle
        draw.rectangle([bx, by, bx + bw, by + bh], outline=color, width=2)
        # Draw label background
        label = f"[{elem['id']}]"
        label_w = len(label) * 9
        draw.rectangle([bx, by - 18, bx + label_w, by], fill=color)
        draw.text((bx + 2, by - 16), label, fill=(255, 255, 255), font=font)

    overlay.save(save_path)
    return save_path


def _fuzzy_match(query: str, text: str) -> float:
    """Return similarity score 0-1 between query and text."""
    q = query.lower().strip()
    t = text.lower().strip()
    # Exact substring match → high score
    if q in t or t in q:
        return 0.95
    return SequenceMatcher(None, q, t).ratio()


# ======================================================================
# 3) New perception-grounded tools (UI-TARS-inspired)
# ======================================================================


@register_tool()
def gui_analyze_screen(
    save_path: str = "",
    region: str = "",
) -> str:
    """
    Perceive the current screen state — the MANDATORY first step before any GUI action.

    Returns structured JSON with:
      - screen_size: [width, height]
      - windows: list of visible windows with titles and positions
      - elements: list of detected text elements with id, text, type, bbox, center
      - screenshot_path: path to the raw screenshot
      - annotated_path: path to the SoM-annotated screenshot

    Parameters:
      save_path: optional custom save path for screenshots
      region: optional "x,y,w,h" to analyze a specific screen region
    """
    _check_pyautogui()
    ts = _ts()

    # Parse region
    parsed_region = None
    if region:
        try:
            parts = [int(x.strip()) for x in region.split(",")]
            if len(parts) == 4:
                parsed_region = tuple(parts)
        except ValueError:
            pass

    # Paths
    raw_path = save_path or str(_ARTIFACTS_DIR / f"screen_{ts}.png")
    annotated_path = str(Path(raw_path).with_stem(Path(raw_path).stem + "_som"))

    try:
        # Capture screenshot
        pil_img = _take_screenshot_pil(raw_path)
        screen_w, screen_h = pil_img.size

        # Try AT-SPI2 first
        elements = _get_atspi_elements(parsed_region)
        if not elements:
            # Fallback to OCR to detect elements
            elements = _ocr_image(pil_img, parsed_region)  # type: ignore

        # Get window list
        windows = _get_active_windows()

        # Draw SoM overlay
        som_path = ""
        if elements:
            som_path = _draw_som_overlay(pil_img, elements, annotated_path)

        # Compress representations to avoid token limits
        compressed_windows = [
            f"[{w['id']}] {w['title'][:40].strip() or 'unnamed'} @ ({w['x']},{w['y']}) {w['w']}x{w['h']}"
            for w in windows[:15]
        ]

        compressed_elements = [
            f"[{e['id']}] '{e['text'][:40]}' ({e['type']}) @ ({e['center'][0]},{e['center'][1]})"
            for e in elements[:80]
        ]

        result = {
            "screen_size": [screen_w, screen_h],
            "element_count": len(elements),
            "windows": compressed_windows,
            "elements": compressed_elements,
            "screenshot_path": raw_path,
            "annotated_path": som_path,
        }

        audit_log(
            "gui_analyze_screen",
            {"region": region},
            "success",
            f"{len(elements)} elements detected",
        )
        return json.dumps(result, separators=(",", ":"))

    except Exception as e:
        audit_log("gui_analyze_screen", {"region": region}, "error", str(e))
        return json.dumps({"error": str(e)})


@register_tool()
def gui_find_element(description: str) -> str:
    """
    Find a GUI element by natural language description.

    Captures a screenshot, runs OCR, and fuzzy-matches the description against
    all detected text elements. Returns the best match with coordinates.

    If no match is found, returns the full list of visible elements so the
    agent can pick the closest one — preventing hallucination.
    """
    _check_pyautogui()

    try:
        ts = _ts()
        raw_path = str(_ARTIFACTS_DIR / f"find_{ts}.png")
        pil_img = _take_screenshot_pil(raw_path)
        
        # Try AT-SPI2 first
        elements = _get_atspi_elements()
        if not elements:
            elements = _ocr_image(pil_img)

        if not elements:
            return json.dumps(
                {
                    "found": False,
                    "reason": "No text elements detected on screen. Screen may be blank or OCR failed.",
                    "screenshot_path": raw_path,
                }
            )

        # Score all elements against description
        scored = []
        for elem in elements:
            score = _fuzzy_match(description, elem["text"])
            scored.append((score, elem))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_elem = scored[0]

        if best_score >= 0.4:
            result = {
                "found": True,
                "match": best_elem,
                "confidence": round(best_score, 3),
                "center_x": best_elem["center"][0],
                "center_y": best_elem["center"][1],
            }
            audit_log(
                "gui_find_element",
                {"description": description},
                "success",
                f"Found '{best_elem['text']}' (confidence={best_score:.2f})",
            )
        else:
            result = {
                "found": False,
                "reason": f"No element matching '{description}' found on screen.",
                "best_candidate": {
                    "text": best_elem["text"],
                    "score": round(best_score, 3),
                },
                "visible_elements": [
                    {"id": e["id"], "text": e["text"], "type": e["type"]}
                    for e in elements[:30]
                ],
                "screenshot_path": raw_path,
            }
            audit_log(
                "gui_find_element",
                {"description": description},
                "not_found",
                f"Best: '{best_elem['text']}' ({best_score:.2f})",
            )

        return json.dumps(result, indent=2)

    except Exception as e:
        audit_log("gui_find_element", {"description": description}, "error", str(e))
        return json.dumps({"error": str(e)})


@register_tool()
def gui_click_element(
    description: str,
    button: str = "left",
    clicks: int = 1,
) -> str:
    """
    Perception-grounded click: find an element by description, then click its center.

    Flow: screenshot → OCR → fuzzy-match → move mouse → click.
    Returns what was clicked and exact coordinates. If the element is not found,
    returns the visible elements list instead of guessing.
    """
    _check_pyautogui()

    try:
        # Find the element
        find_result_raw = gui_find_element(description)
        find_result = json.loads(find_result_raw)

        if not find_result.get("found"):
            audit_log(
                "gui_click_element",
                {"description": description},
                "not_found",
                "Element not visible",
            )
            return json.dumps(
                {
                    "clicked": False,
                    "reason": find_result.get("reason", "Element not found on screen."),
                    "visible_elements": find_result.get("visible_elements", []),
                    "screenshot_path": find_result.get("screenshot_path", ""),
                },
                indent=2,
            )

        cx = find_result["center_x"]
        cy = find_result["center_y"]
        matched_text = find_result["match"]["text"]

        # Move and click
        pyautogui.moveTo(cx, cy, duration=0.15)
        time.sleep(0.05)
        pyautogui.click(cx, cy, button=button, clicks=clicks)

        result = {
            "clicked": True,
            "element_text": matched_text,
            "coordinates": [cx, cy],
            "button": button,
            "clicks": clicks,
            "confidence": find_result["confidence"],
        }
        audit_log(
            "gui_click_element",
            {"description": description, "x": cx, "y": cy},
            "success",
            f"Clicked '{matched_text}' at ({cx},{cy})",
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        audit_log("gui_click_element", {"description": description}, "error", str(e))
        return json.dumps({"error": str(e)})


@register_tool()
def gui_observe_transition(
    action_description: str = "",
    wait_seconds: float = 1.0,
) -> str:
    """
    Detect screen state changes by comparing before/after snapshots.

    Takes a 'before' screenshot + element map, waits, then takes an 'after'
    snapshot. Returns a structured diff showing new, removed, and changed elements.
    """
    _check_pyautogui()

    try:
        ts = _ts()

        # BEFORE state
        before_path = str(_ARTIFACTS_DIR / f"transition_before_{ts}.png")
        pil_before = _take_screenshot_pil(before_path)
        elements_before = _ocr_image(pil_before)
        texts_before = {e["text"] for e in elements_before}

        # Wait for the transition to complete
        time.sleep(max(0.2, min(wait_seconds, 10.0)))

        # AFTER state
        after_path = str(_ARTIFACTS_DIR / f"transition_after_{ts}.png")
        pil_after = _take_screenshot_pil(after_path)
        elements_after = _ocr_image(pil_after)
        texts_after = {e["text"] for e in elements_after}

        # Compute diff
        new_elements = [e for e in elements_after if e["text"] not in texts_before]
        removed_elements = [e for e in elements_before if e["text"] not in texts_after]

        # Check overall visual change using image comparison
        visual_changed = False
        change_percent = 0.0
        if cv2 is not None and np is not None:
            arr_before = np.array(pil_before)
            arr_after = np.array(pil_after)
            if arr_before.shape == arr_after.shape:
                diff = cv2.absdiff(arr_before, arr_after)
                change_percent = float(
                    round((np.count_nonzero(diff) / diff.size) * 100, 2)
                )
                visual_changed = bool(change_percent > 1.0)

        result = {
            "action": action_description,
            "visual_changed": visual_changed,
            "pixel_change_percent": change_percent,
            "elements_before_count": len(elements_before),
            "elements_after_count": len(elements_after),
            "new_elements": [
                {"text": e["text"], "type": e["type"], "center": e["center"]}
                for e in new_elements[:20]
            ],
            "removed_elements": [
                {"text": e["text"], "type": e["type"]} for e in removed_elements[:20]
            ],
            "before_screenshot": before_path,
            "after_screenshot": after_path,
        }

        audit_log(
            "gui_observe_transition",
            {"action": action_description},
            "success",
            f"changed={visual_changed}, new={len(new_elements)}, removed={len(removed_elements)}",
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        audit_log(
            "gui_observe_transition", {"action": action_description}, "error", str(e)
        )
        return json.dumps({"error": str(e)})


@register_tool()
def gui_scroll_screen(
    direction: str = "down",
    amount: int = 3,
    region: str = "",
) -> str:
    """
    Scroll the screen and return what is now visible via OCR.

    Unlike blind scrolling, this returns the actual post-scroll screen content
    so the agent knows what appeared/disappeared.
    """
    _check_pyautogui()

    try:
        scroll_val = -amount if direction == "down" else amount
        pyautogui.scroll(scroll_val)
        time.sleep(0.5)  # Wait for scroll animation

        # Capture and analyze post-scroll state
        ts = _ts()
        raw_path = str(_ARTIFACTS_DIR / f"scroll_{ts}.png")
        pil_img = _take_screenshot_pil(raw_path)

        parsed_region = None
        if region:
            try:
                parts = [int(x.strip()) for x in region.split(",")]
                if len(parts) == 4:
                    parsed_region = tuple(parts)
            except ValueError:
                pass

        elements = _ocr_image(pil_img, parsed_region)  # type: ignore

        result = {
            "scrolled": direction,
            "amount": amount,
            "visible_text_elements": len(elements),
            "elements": [
                {
                    "id": e["id"],
                    "text": e["text"],
                    "type": e["type"],
                    "center": e["center"],
                }
                for e in elements[:40]
            ],
            "screenshot_path": raw_path,
        }

        audit_log(
            "gui_scroll_screen",
            {"direction": direction, "amount": amount},
            "success",
            f"{len(elements)} elements visible after scroll",
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        audit_log("gui_scroll_screen", {"direction": direction}, "error", str(e))
        return json.dumps({"error": str(e)})


@register_tool()
def gui_read_text_at(x: int, y: int, width: int, height: int) -> str:
    """
    Read (OCR) the text at a specific screen region.

    Crops the region, runs OCR, and returns the exact text found.
    Prevents the agent from hallucinating text content.
    """
    _check_pyautogui()
    _check_ocr()

    try:
        ts = _ts()
        raw_path = str(_ARTIFACTS_DIR / f"readtext_{ts}.png")
        pil_img = _take_screenshot_pil(raw_path)

        region = (x, y, width, height)
        elements = _ocr_image(pil_img, region)

        full_text = " ".join(e["text"] for e in elements)

        result = {
            "region": {"x": x, "y": y, "width": width, "height": height},
            "text": full_text,
            "elements": elements[:20],
            "screenshot_path": raw_path,
        }

        audit_log(
            "gui_read_text_at",
            {"x": x, "y": y, "w": width, "h": height},
            "success",
            f"Read {len(full_text)} chars",
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        audit_log("gui_read_text_at", {"x": x, "y": y}, "error", str(e))
        return json.dumps({"error": str(e)})
