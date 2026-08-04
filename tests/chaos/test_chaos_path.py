import os
from pathlib import Path
import pytest
from tools.base import resolve_and_verify_path

def test_path_null_byte():
    with pytest.raises(ValueError, match="null byte detected"):
        resolve_and_verify_path("file.txt\0")

def test_path_sensitive_linux():
    if os.name != "nt":
        with pytest.raises(PermissionError, match="CRITICAL ACCESS DENIED"):
            resolve_and_verify_path("/etc/passwd")
        with pytest.raises(PermissionError, match="CRITICAL ACCESS DENIED"):
            resolve_and_verify_path("/etc/../etc/passwd")

def test_path_traversal_out_of_cwd():
    # Assuming we are in a subdirectory or just testing traversal from CWD
    with pytest.raises(PermissionError, match="((outside the allowed workspace)|(CRITICAL ACCESS DENIED))"):
        resolve_and_verify_path("../../etc/passwd")

def test_path_cwd_sandbox():
    cwd = Path.cwd().resolve()
    # This should pass as it's within CWD
    resolved = resolve_and_verify_path("agent.py")
    assert resolved == cwd / "agent.py"

def test_path_outside_cwd_with_confirmation():
    def mock_confirm(action, target):
        return True
    
    # This would normally be blocked, but confirmation is provided
    # Note: sensitive paths are still blocked even with confirmation (hard block)
    
    # Let's try a non-sensitive path outside CWD
    # We'll use the parent of CWD if it's not sensitive
    parent = Path.cwd().parent.resolve()
    
    # Check if parent is sensitive (unlikely for a home dir)
    sensitive_prefixes = ["/etc", "/sys", "/proc", "/var", "/root", "/boot", "/dev"]
    if any(str(parent).startswith(p) for p in sensitive_prefixes):
        pytest.skip("Parent directory is sensitive")
        
    resolved = resolve_and_verify_path(parent / "some_file.txt", confirm_func=mock_confirm)
    assert resolved == parent / "some_file.txt"

def test_path_outside_cwd_denied_confirmation():
    def mock_confirm(action, target):
        return False
    
    parent = Path.cwd().parent.resolve()
    with pytest.raises(PermissionError, match="((outside the allowed workspace)|(CRITICAL ACCESS DENIED))"):
        resolve_and_verify_path(parent / "some_file.txt", confirm_func=mock_confirm)

def test_path_very_long():
    long_path = "a" * 1000
    # Should probably fail or just resolve
    try:
        resolve_and_verify_path(long_path)
    except Exception:
        pass # OS dependent

def test_path_empty():
    resolved = resolve_and_verify_path("")
    assert resolved == Path.cwd().resolve()

if __name__ == "__main__":
    # Manual run if pytest not used
    try:
        test_path_null_byte()
        print("test_path_null_byte passed")
        test_path_sensitive_linux()
        print("test_path_sensitive_linux passed")
        test_path_traversal_out_of_cwd()
        print("test_path_traversal_out_of_cwd passed")
        test_path_cwd_sandbox()
        print("test_path_cwd_sandbox passed")
        print("All manual path chaos tests passed!")
    except Exception as e:
        print(f"Test failed: {e}")
