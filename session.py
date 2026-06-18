import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from tools.database_ops import init_db, load_session, save_session


@dataclass
class Session:
    user_id: int
    task_id: Optional[str] = None
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    pending_confirmations: List[Dict[str, Any]] = field(default_factory=list)
    yolo_mode: bool = False
    think_mode: bool = False
    think_mode_policy: str = "auto"
    llm_model: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Performance: track whether history needs sanitization. Set by `mark_dirty()`
    # whenever history is mutated; cleared after sanitize. Avoids O(n) rescan
    # on every LLM round when nothing changed.
    history_dirty: bool = True
    # Performance: hash of last persisted history payload, used to skip
    # redundant SQLite writes when save() is called multiple times per turn
    # (callbacks, status updates, etc.) without intervening changes.
    last_saved_signature: Optional[int] = None
    # Token / cost tracking – accumulated across the session lifetime.
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    llm_call_count: int = 0

    def mark_dirty(self) -> None:
        self.history_dirty = True


class SessionManager:
    def __init__(self, timeout_minutes: int = 60):
        self.sessions: Dict[int, Session] = {}
        self.locks: Dict[int, asyncio.Lock] = {}
        self.timeout_minutes = timeout_minutes

        # Ensure DB is ready
        init_db()

        # Use the global shared memory instance
        from tools.memory_service import get_memory

        self.memory = get_memory()

    def resolve_id(self, user_id: int) -> int:
        if os.getenv("YOLO_GLOBAL_MODE", "false").lower() == "true":
            return 0
        return user_id

    def get_lock(self, user_id: int) -> asyncio.Lock:
        user_id = self.resolve_id(user_id)
        return self.locks.setdefault(user_id, asyncio.Lock())

    def get_or_create(self, user_id: int) -> Session:
        user_id = self.resolve_id(user_id)
        if user_id not in self.sessions:
            # Try to load from DB first
            history, yolo_mode, think_mode, think_mode_policy, pending_confirmations = (
                load_session(user_id)
            )
            if history is not None:
                self.sessions[user_id] = Session(
                    user_id=user_id,
                    message_history=history,
                    pending_confirmations=pending_confirmations or [],
                    yolo_mode=yolo_mode,
                    think_mode=think_mode,
                    think_mode_policy=think_mode_policy or "auto",
                )
            else:
                self.sessions[user_id] = Session(user_id=user_id)

        session = self.sessions[user_id]
        session.last_active = datetime.now(timezone.utc)
        return session

    def save(self, user_id: int, force: bool = False):
        """Save a specific session to the database.

        Performance: computes a cheap signature of the relevant state and
        skips the write when nothing has changed since the previous save.
        This eliminates redundant full-history JSON re-serialization on the
        hot path (multiple `save()` calls per turn from bot callbacks).
        Pass `force=True` to bypass the cache (e.g., on shutdown/expiry).
        """
        user_id = self.resolve_id(user_id)
        if user_id not in self.sessions:
            return
        session = self.sessions[user_id]

        # Signature over the full persisted state so any mutation (including to
        # a middle message or the *content* of a pending confirmation) is
        # detected. This is the primary guard against dropping a save: the
        # earlier "len + last message only" version could miss in-place edits to
        # earlier messages when history_dirty had been cleared. Serializing here
        # costs the same O(n) as the save we're about to skip, so it's cheap
        # relative to the SQLite write it avoids.
        import json
        try:
            history_repr = json.dumps(session.message_history, sort_keys=True, default=str)
            pending_repr = json.dumps(session.pending_confirmations, sort_keys=True, default=str)
        except Exception:
            # Unserializable payload: never dedup, always persist.
            history_repr = None
            pending_repr = None

        signature = None if history_repr is None else hash(
            (
                len(session.message_history),
                hash(history_repr),
                session.yolo_mode,
                session.think_mode,
                session.think_mode_policy,
                hash(pending_repr),
            )
        )
        if (
            not force
            and signature is not None
            and not session.history_dirty
            and signature == session.last_saved_signature
        ):
            return

        save_session(
            user_id,
            session.message_history,
            session.yolo_mode,
            session.think_mode,
            session.think_mode_policy,
            session.pending_confirmations,
        )
        session.last_saved_signature = signature
        session.history_dirty = False

    def clear(self, user_id: int):
        user_id = self.resolve_id(user_id)
        if user_id in self.sessions:
            del self.sessions[user_id]
        if user_id in self.locks:
            del self.locks[user_id]
        # Also clear from DB for a true reset
        from tools.database_ops import save_session as db_save

        db_save(user_id, [], False, False, "auto", None)

    async def auto_expiry_task(self):
        """Background task to remove expired sessions from memory (but keep in DB)."""
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            expired_ids = [
                uid
                for uid, sess in self.sessions.items()
                if (now - sess.last_active).total_seconds() > self.timeout_minutes * 60
            ]
            for uid in expired_ids:
                lock = self.get_lock(uid)
                if lock.locked():
                    continue # Busy, skip this round
                    
                async with lock:
                    # Save to DB before dropping from memory (force to bypass dedup cache)
                    self.save(uid, force=True)
                    if uid in self.sessions:
                        del self.sessions[uid]
                    # We keep the lock in self.locks for future requests, 
                    # it will be reused by get_lock. Cleaning it up might
                    # cause a new lock to be created while we still hold this one.

