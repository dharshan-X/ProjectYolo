from unittest.mock import MagicMock
from tools.base import get_mem0_config, audit_log

def test_get_mem0_config_active_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    
    config = get_mem0_config()
    
    assert config["llm"]["provider"] == "anthropic"
    assert config["embedder"]["provider"] == "openai"
    assert config["embedder"]["config"]["api_key"] == "openai-test-key"

def test_audit_log_stderr_fallback(capsys, monkeypatch):
    # Make the log file unwritable
    monkeypatch.setattr("builtins.open", MagicMock(side_effect=PermissionError("Permission denied")))
    
    audit_log("test_tool", {}, "success", "detail")
    
    captured = capsys.readouterr()
    assert "Failed to write audit log: Permission denied" in captured.err


def test_gui_tools_and_schema_alignment():
    import tools
    assert tools._GUI_AVAILABLE is True
    assert tools.gui_mouse_move is not None
    assert tools.gui_screenshot is not None
    # V2 transactional tools are exposed to the model
    assert tools.gui_observe is not None
    assert tools.gui_find is not None
    assert tools.gui_action is not None

    schema_names = {s["function"]["name"] for s in tools.TOOLS_SCHEMAS}
    # V2 tools present in schemas
    assert {"gui_observe", "gui_find", "gui_action"} <= schema_names
    # Retired V1 perception tools are no longer exposed to the model
    retired = {
        "gui_analyze_screen", "gui_find_element", "gui_click_element",
        "gui_observe_transition", "gui_scroll_screen", "gui_read_text_at",
    }
    assert not (retired & schema_names)

    alignment = tools.validate_tool_schema_alignment()
    assert alignment["schemas_without_handlers"] == []

    # Filter out chaos test tools registered globally during test runs
    handlers = [h for h in alignment["handlers_without_schemas"] if not h.startswith("chaos_")]
    assert handlers == []


def test_adjust_rate_limiting(monkeypatch):
    import os
    from tools import adjust_rate_limiting
    from llm_router import _get_rate_limiter
    import llm_router
    
    # Start fresh with a known RPM limit
    llm_router._GLOBAL_RATE_LIMITER = None
    monkeypatch.setenv("LLM_RPM_LIMIT", "25")
    
    limiter = _get_rate_limiter()
    assert limiter.rpm_limit == 25
    
    # Adjust using the new tool
    res = adjust_rate_limiting(50)
    assert "Successfully updated rate limit to 50" in res
    assert os.environ["LLM_RPM_LIMIT"] == "50"
    
    # Get the limiter again, it should have updated dynamically
    limiter = _get_rate_limiter()
    assert limiter.rpm_limit == 50


def test_gui_screenshot_rejects_blank_fallback(tmp_path, monkeypatch):
    from PIL import Image
    from tools.gui_ops import gui_screenshot

    target = tmp_path / "blank_screenshot.png"
    Image.new("RGB", (10, 10), color=(0, 0, 0)).save(target)

    monkeypatch.setattr("tools.gui_ops.pyautogui", MagicMock())
    monkeypatch.setattr(
        "tools.gui_ops.pyautogui.screenshot",
        MagicMock(side_effect=Exception("Can't connect to display")),
    )
    monkeypatch.setattr(
        "tools.gui_ops.subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0)),
    )

    result = gui_screenshot(str(target))

    assert "Error taking screenshot" in result
    assert "blank" in result or "headless" in result.lower()


def test_gui_click_and_spatial_scoring():
    import unittest.mock as mock
    from tools.gui_ops import _spatial_score_modifier, gui_mouse_click
    
    # 1. Test spatial score modifier
    # With a screen size of 1366x768
    with mock.patch("pyautogui.size", return_value=(1366, 768)):
        # Bottom/dock check
        bot_score_far = _spatial_score_modifier("Firefox icon in dock at bottom", 285, 303)
        bot_score_near = _spatial_score_modifier("Firefox icon in dock at bottom", 805, 801)
        # Near (bottom) should score significantly higher than far (top/middle)
        assert bot_score_near > bot_score_far

        # Coordinate matching
        coord_score_near = _spatial_score_modifier("Firefox at dock position 805,801", 805, 801)
        coord_score_far = _spatial_score_modifier("Firefox at dock position 805,801", 285, 303)
        assert coord_score_near > coord_score_far

    # 2. Test gui_mouse_click with coordinates
    with mock.patch("pyautogui.click") as mock_click:
        res = gui_mouse_click(button="left", clicks=1, x=805, y=801)
        assert "at (805, 801)" in res
        mock_click.assert_called_once_with(x=805, y=801, button="left", clicks=1)




