"""
Headless tests for the V2 GUI subsystem (tools/gui package).

conftest.py mocks pyautogui globally, and all perception/screenshot helpers are
patched here, so these run without a display.
"""

import json
from unittest import mock

from tools.gui.config import GUIConfig
from tools.gui.models import BoundingBox, DisplayLayout, GUIState, GUIWindow, UIElement
from tools.gui import engine, perception


def _config(**overrides) -> GUIConfig:
    cfg = GUIConfig.load()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _element(text, x=0, y=0, w=100, h=30, source="atspi", type_="button") -> UIElement:
    return UIElement(
        id=text,
        text=text,
        type=type_,
        bounds=BoundingBox(x=x, y=y, width=w, height=h),
        source=source,
    )


def _window(title="Main Window", x=0, y=0, w=800, h=600) -> GUIWindow:
    return GUIWindow(
        id="1", title=title, bounds=BoundingBox(x=x, y=y, width=w, height=h), is_active=True
    )


def _state(elements, active_window=None, state_id="s1") -> GUIState:
    return GUIState(
        state_id=state_id,
        timestamp=0.0,
        screenshot_path=None,
        annotated_path=None,
        windows=[active_window] if active_window else [],
        active_window=active_window,
        elements=elements,
        layout=DisplayLayout(monitors=[], virtual_width=1366, virtual_height=768),
    )


def _mock_engine_deps(monkeypatch, elements):
    """Patch engine's perception + screenshot + window helpers to stay headless."""
    monkeypatch.setattr("tools.gui.engine.get_atspi_elements", lambda: elements)
    monkeypatch.setattr("tools.gui.engine.get_ocr_elements", lambda pil: [])
    monkeypatch.setattr("tools.gui.engine._get_active_windows", lambda: [])
    monkeypatch.setattr("tools.gui.engine._take_screenshot_pil", lambda *a, **k: None)
    monkeypatch.setattr(
        "tools.gui.engine.get_display_layout",
        lambda: DisplayLayout(monitors=[], virtual_width=1366, virtual_height=768),
    )


# ---------------------------------------------------------------------------
# Import + package integrity
# ---------------------------------------------------------------------------


def test_package_imports():
    from tools.gui import (  # noqa: F401
        gui_observe,
        gui_find,
        gui_action,
        capture_state,
        wait_for_stability,
        get_atspi_elements,
        get_ocr_elements,
        merge_elements,
    )

    assert callable(gui_observe)
    assert callable(gui_find)
    assert callable(gui_action)


# ---------------------------------------------------------------------------
# capture_state
# ---------------------------------------------------------------------------


def test_capture_state_headless(monkeypatch):
    elements = [_element("Submit"), _element("Cancel", x=200, y=0)]
    _mock_engine_deps(monkeypatch, elements)

    state = engine.capture_state(_config(save_debug_artifacts=False))

    assert state.state_id
    assert len(state.elements) == 2
    assert state.elements[0].text == "Submit"
    assert state.elements[0].source == "atspi"


def test_capture_state_caps_elements(monkeypatch):
    elements = [_element(f"el{i}") for i in range(50)]
    _mock_engine_deps(monkeypatch, elements)

    state = engine.capture_state(_config(save_debug_artifacts=False, max_elements=10))

    assert len(state.elements) == 10


# ---------------------------------------------------------------------------
# perception
# ---------------------------------------------------------------------------


def test_merge_elements_dedupes_by_center():
    atspi = [_element("Submit", x=0, y=0, w=100, h=30)]
    ocr = [
        _element("Submit", x=10, y=5, w=80, h=20, source="ocr"),  # center inside atspi
        _element("Footer", x=500, y=600, w=50, h=20, source="ocr"),  # outside
    ]

    merged = perception.merge_elements(atspi, ocr)

    assert [e.text for e in merged] == ["Submit", "Footer"]
    assert merged[1].source == "merged"


def test_merge_elements_no_duplicates_when_empty():
    assert perception.merge_elements([], []) == []


# ---------------------------------------------------------------------------
# gui_find / gui_action (via actions.py with mocked capture_state)
# ---------------------------------------------------------------------------


def test_gui_find_success(monkeypatch):
    from tools.gui.actions import gui_find

    elements = [
        _element("Save"),
        _element("Cancel", x=200, y=0),
        _element("Open", x=400, y=0),
    ]
    monkeypatch.setattr(
        "tools.gui.actions.capture_state", lambda cfg: _state(elements, active_window=_window())
    )

    result = json.loads(gui_find("Save", _config()))

    assert result["status"] == "success"
    assert result["data"]["target"]["text"] == "Save"


def test_gui_find_not_found(monkeypatch):
    from tools.gui.actions import gui_find

    monkeypatch.setattr(
        "tools.gui.actions.capture_state", lambda cfg: _state([], active_window=_window())
    )

    result = json.loads(gui_find("Missing", _config()))

    assert result["status"] == "error"
    assert result["reason"] == "element_not_found"


def test_gui_action_click_verifies_transition(monkeypatch):
    from tools.gui.actions import gui_action

    before = _state([_element("OK")], active_window=_window("Window A"), state_id="before")
    after = _state([_element("OK")], active_window=_window("Window B"), state_id="after")

    monkeypatch.setattr(
        "tools.gui.actions.capture_state", mock.Mock(side_effect=[before, after])
    )
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)
    monkeypatch.setattr("tools.gui.actions.emit_click", lambda *a, **k: None)

    result = json.loads(gui_action("OK", "click", {}, _config()))

    assert result["status"] == "success"
    assert result["data"]["action"] == "click"
    assert "Window focus changed" in result["data"]["verification"]


def test_gui_action_unknown_action(monkeypatch):
    from tools.gui.actions import gui_action

    monkeypatch.setattr(
        "tools.gui.actions.capture_state", lambda cfg: _state([_element("OK")])
    )
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)

    result = json.loads(gui_action("OK", "swipe", {}, _config()))

    assert result["status"] == "error"
    assert result["reason"] == "invalid_action"


# ---------------------------------------------------------------------------
# wait_for_stability
# ---------------------------------------------------------------------------


def test_wait_for_stability_timeout_no_raise(monkeypatch):
    # Element signature keeps changing → never stabilizes → times out, no raise
    monkeypatch.setattr(
        "tools.gui.engine.get_atspi_elements",
        mock.Mock(side_effect=lambda: [_element(f"churn{i}") for i in range(3)]),
    )
    monkeypatch.setattr("time.sleep", lambda s: None)

    cfg = _config(
        action_timeout_seconds=0.2,
        stability_poll_seconds=0.01,
        stability_required_polls=3,
    )

    # No exception == success
    engine.wait_for_stability(cfg)


# ---------------------------------------------------------------------------
# Extended Action & Verification Tests
# ---------------------------------------------------------------------------


def test_gui_action_type_in_place_verification(monkeypatch):
    from tools.gui.actions import gui_action

    input_el = _element("Search Input", x=50, y=50, w=200, h=40, type_="input")
    state = _state([input_el], active_window=_window())

    monkeypatch.setattr("tools.gui.actions.capture_state", mock.Mock(return_value=state))
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)
    click_mock = mock.Mock()
    type_mock = mock.Mock()
    monkeypatch.setattr("tools.gui.actions.emit_click", click_mock)
    monkeypatch.setattr("tools.gui.actions.emit_type", type_mock)

    result = json.loads(gui_action("Search Input", "type", {"text": "ProjectYolo"}, _config()))

    assert result["status"] == "success"
    assert result["data"]["action"] == "type"
    assert "Search Input" in result["data"]["target"]
    assert "successfully typed" in result["data"]["verification"]
    type_mock.assert_called_once_with("ProjectYolo")


def test_gui_action_double_click(monkeypatch):
    from tools.gui.actions import gui_action

    icon_el = _element("My File.txt", x=100, y=100, w=60, h=60, type_="icon")
    state = _state([icon_el], active_window=_window())

    monkeypatch.setattr("tools.gui.actions.capture_state", mock.Mock(return_value=state))
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)
    click_mock = mock.Mock()
    monkeypatch.setattr("tools.gui.actions.emit_click", click_mock)

    result = json.loads(gui_action("My File.txt", "double_click", {}, _config()))

    assert result["status"] == "success"
    assert result["data"]["action"] == "double_click"
    click_mock.assert_called_once_with(130, 130, button="left", clicks=2)


def test_gui_action_press_key(monkeypatch):
    from tools.gui.actions import gui_action

    state = _state([], active_window=_window())
    monkeypatch.setattr("tools.gui.actions.capture_state", mock.Mock(return_value=state))
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)
    key_mock = mock.Mock()
    monkeypatch.setattr("tools.gui.actions.emit_key", key_mock)

    # Key via query or action_args
    result = json.loads(gui_action("Return", "press_key", {}, _config()))

    assert result["status"] == "success"
    assert result["data"]["action"] == "press_key"
    key_mock.assert_called_once_with("Return")


def test_gui_action_drag(monkeypatch):
    from tools.gui.actions import gui_action

    handle = _element("Slider Handle", x=50, y=100, w=20, h=20, type_="slider")
    state = _state([handle], active_window=_window())

    monkeypatch.setattr("tools.gui.actions.capture_state", mock.Mock(return_value=state))
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)
    drag_mock = mock.Mock()
    monkeypatch.setattr("tools.gui.actions.emit_drag", drag_mock)

    result = json.loads(gui_action("Slider Handle", "drag", {"to_x": 250, "to_y": 100}, _config()))

    assert result["status"] == "success"
    assert result["data"]["action"] == "drag"
    drag_mock.assert_called_once_with(60, 110, 250, 100, duration=0.5, button="left")


def test_gui_action_in_place_click_verification(monkeypatch):
    from tools.gui.actions import gui_action

    btn = _element("Toggle Option", x=50, y=50, w=100, h=30, type_="checkbox")
    state = _state([btn], active_window=_window())

    monkeypatch.setattr("tools.gui.actions.capture_state", mock.Mock(return_value=state))
    monkeypatch.setattr("tools.gui.actions.wait_for_stability", lambda cfg: None)
    monkeypatch.setattr("tools.gui.actions.emit_click", lambda *a, **k: None)

    result = json.loads(gui_action("Toggle Option", "click", {}, _config()))

    assert result["status"] == "success"
    assert "successfully executed on checkbox 'Toggle Option'" in result["data"]["verification"]


def test_spatial_grounding_word_boundaries():
    from tools.gui.grounding import ground_element

    # "Desktop" should NOT trigger "top" spatial penalty when bounds.y > 300
    desktop_el = _element("Desktop", x=100, y=800, w=120, h=40, type_="button")
    res = ground_element("Desktop", [desktop_el], _config(), active_window=_window())

    assert res.status == "success"
    assert res.target.text == "Desktop"
    assert res.confidence >= 0.70


def test_get_display_layout_fallbacks(monkeypatch):
    import sys
    from tools.gui.backend import get_display_layout

    # Mock all underlying display probes failing
    monkeypatch.setitem(sys.modules, "Xlib.display", None)
    monkeypatch.setattr("pyautogui.size", mock.Mock(side_effect=Exception("No GUI display")))
    monkeypatch.setattr("subprocess.run", mock.Mock(side_effect=FileNotFoundError("xrandr not found")))

    layout = get_display_layout()
    assert layout.virtual_width >= 800
    assert layout.virtual_height >= 600
    assert len(layout.monitors) >= 1

