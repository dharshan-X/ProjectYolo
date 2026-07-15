import sys
from unittest.mock import MagicMock

# Mock pyautogui globally for tests to prevent X11 Display/XauthError in headless testing environments
mock_pyautogui = MagicMock()
mock_pyautogui.size.return_value = (1366, 768)
sys.modules["pyautogui"] = mock_pyautogui
