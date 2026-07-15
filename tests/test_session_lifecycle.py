import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session import Session, SessionManager


def _make_manager(timeout_minutes=60):
    with (
        patch("session.init_db"),
        patch("tools.memory_service.get_memory", return_value=MagicMock()),
    ):
        return SessionManager(timeout_minutes=timeout_minutes)


@pytest.mark.asyncio
async def test_clear_preserves_held_user_lock():
    manager = _make_manager()
    user_id = 17
    manager.sessions[user_id] = Session(user_id=user_id)
    lock = manager.get_lock(user_id)

    await lock.acquire()
    try:
        with patch("session.save_session"):
            manager.clear(user_id)

        assert lock.locked()
        assert manager.get_lock(user_id) is lock
        assert user_id not in manager.sessions
    finally:
        lock.release()

    assert manager.get_lock(user_id) is lock


def test_clear_then_reload_uses_fresh_session_defaults():
    persisted_sessions = {}

    def fake_save(
        user_id,
        history,
        yolo_mode,
        think_mode,
        think_mode_policy,
        pending_confirmations,
    ):
        persisted_sessions[user_id] = (
            list(history),
            yolo_mode,
            think_mode,
            think_mode_policy,
            list(pending_confirmations),
        )

    def fake_load(user_id):
        return persisted_sessions.get(user_id, (None, None, None, None, None))

    manager = _make_manager()
    user_id = 23
    manager.sessions[user_id] = Session(
        user_id=user_id,
        message_history=[{"role": "user", "content": "keep out"}],
        pending_confirmations=[{"id": "pending"}],
        yolo_mode=True,
        think_mode=False,
        think_mode_policy="force_off",
    )

    with (
        patch("session.save_session", side_effect=fake_save) as mock_save,
        patch("session.load_session", side_effect=fake_load),
    ):
        manager.clear(user_id)
        reloaded = manager.get_or_create(user_id)

    fresh = Session(user_id=user_id)
    assert reloaded.message_history == fresh.message_history
    assert reloaded.pending_confirmations == fresh.pending_confirmations
    assert reloaded.yolo_mode is fresh.yolo_mode
    assert reloaded.think_mode is fresh.think_mode
    assert reloaded.think_mode_policy == fresh.think_mode_policy
    mock_save.assert_called_once_with(
        user_id,
        fresh.message_history,
        fresh.yolo_mode,
        fresh.think_mode,
        fresh.think_mode_policy,
        fresh.pending_confirmations,
    )


@pytest.mark.asyncio
async def test_auto_expiry_continues_after_save_failure_and_propagates_cancellation():
    manager = _make_manager(timeout_minutes=60)
    expired_at = datetime.now(timezone.utc) - timedelta(hours=2)
    manager.sessions = {
        user_id: Session(user_id=user_id, last_active=expired_at)
        for user_id in (1, 2, 3)
    }
    save_attempts = []

    def save_with_failures(user_id, force=False):
        save_attempts.append((user_id, force))
        if user_id == 1:
            raise RuntimeError("database temporarily unavailable")
        if user_id == 3:
            raise asyncio.CancelledError

    sleep = AsyncMock(
        side_effect=[None, AssertionError("expiry loop swallowed cancellation")]
    )
    with (
        patch("session.asyncio.sleep", sleep),
        patch.object(manager, "save", side_effect=save_with_failures),
        pytest.raises(asyncio.CancelledError),
    ):
        await manager.auto_expiry_task()

    assert save_attempts == [(1, True), (2, True), (3, True)]
    assert 1 in manager.sessions
    assert 2 not in manager.sessions
    assert 3 in manager.sessions
