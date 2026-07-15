import os
import sys
from unittest.mock import patch, MagicMock
sys.modules['discord'] = MagicMock()

from discord_gateway import _is_allowed_user

def test_discord_auth_empty_env():
    with patch.dict(os.environ, {"DISCORD_ALLOWED_USER_IDS": ""}):
        assert _is_allowed_user(12345) is False

def test_discord_auth_missing_env():
    with patch.dict(os.environ, {}):
        if "DISCORD_ALLOWED_USER_IDS" in os.environ:
            del os.environ["DISCORD_ALLOWED_USER_IDS"]
        assert _is_allowed_user(12345) is False

def test_discord_auth_allowed_user():
    with patch.dict(os.environ, {"DISCORD_ALLOWED_USER_IDS": "12345,67890"}):
        assert _is_allowed_user(12345) is True
        assert _is_allowed_user(67890) is True

def test_discord_auth_denied_user():
    with patch.dict(os.environ, {"DISCORD_ALLOWED_USER_IDS": "12345,67890"}):
        assert _is_allowed_user(99999) is False
        assert _is_allowed_user(11111) is False
