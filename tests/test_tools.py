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
    
    alignment = tools.validate_tool_schema_alignment()
    assert alignment["schemas_without_handlers"] == []
    
    # Filter out chaos test tools registered globally during test runs
    handlers = [h for h in alignment["handlers_without_schemas"] if not h.startswith("chaos_")]
    assert handlers == []


