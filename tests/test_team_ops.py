import pytest
import asyncio
from tools.database_ops import add_worker_task, get_worker_status, update_worker_status, _conn_ctx, init_db
init_db()

@pytest.fixture
def cleanup_task():
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM background_tasks WHERE task_id = 'test_w_1'")
    yield
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM background_tasks WHERE task_id = 'test_w_1'")

def test_worker_lifecycle(cleanup_task):
    task_id = "test_w_1"
    add_worker_task(task_id, 123, "Backend", "Fix DB")
    status = get_worker_status(task_id)
    assert status["status"] == "running"
    
    update_worker_status(task_id, "needs_help", "I don't understand the schema")
    status = get_worker_status(task_id)
    assert status["status"] == "needs_help"
    assert status["result"] == "I don't understand the schema"

def test_swarm_id_storage():
    task_id = "test_w_swarm_store"
    # Ensure cleanup
    with _conn_ctx() as conn:
        conn.execute("DELETE FROM background_tasks WHERE task_id = ?", (task_id,))
    
    try:
        add_worker_task(task_id, 123, "Dev", "Write swarm tests", swarm_id="swarm_test_123")
        with _conn_ctx() as conn:
            row = conn.execute("SELECT swarm_id FROM background_tasks WHERE task_id = ?", (task_id,)).fetchone()
            assert row is not None
            assert row[0] == "swarm_test_123"
    finally:
        with _conn_ctx() as conn:
            conn.execute("DELETE FROM background_tasks WHERE task_id = ?", (task_id,))

def test_get_swarm_messages_order_and_limit():
    from tools.database_ops import add_swarm_message, get_swarm_messages
    swarm_id = "swarm_order_test"
    with _conn_ctx() as conn:
        conn.execute("DELETE FROM swarm_messages WHERE swarm_id = ?", (swarm_id,))
    
    try:
        # Insert 6 messages
        for i in range(6):
            add_swarm_message(swarm_id, f"w_{i}", "Role", f"Msg {i}")
        
        # Request limit 3
        msgs = get_swarm_messages(swarm_id, limit=3)
        assert len(msgs) == 3
        # Should be the LATEST 3 messages, returned in chronological order: Msg 3, Msg 4, Msg 5
        assert msgs[0]["message"] == "Msg 3"
        assert msgs[1]["message"] == "Msg 4"
        assert msgs[2]["message"] == "Msg 5"
    finally:
        with _conn_ctx() as conn:
            conn.execute("DELETE FROM swarm_messages WHERE swarm_id = ?", (swarm_id,))

@pytest.mark.asyncio
async def test_wait_for_swarm_message_no_stale():
    from tools.team_ops import wait_for_swarm_message
    from tools.database_ops import add_swarm_message
    swarm_id = "swarm_wait_test"
    with _conn_ctx() as conn:
        conn.execute("DELETE FROM swarm_messages WHERE swarm_id = ?", (swarm_id,))
        
    try:
        # 1. Add a message BEFORE waiting
        add_swarm_message(swarm_id, "w_old", "Role", "Old matching message")
        
        # 2. Wait for message matching "matching message" with a small timeout
        res = await wait_for_swarm_message(swarm_id, "matching message", timeout_seconds=1)
        assert "Match found immediately in past messages" in res
        
        # 3. If we wait for a pattern that does NOT exist in the past, and then broadcast it, it should match.
        async def broadcast_delayed():
            await asyncio.sleep(0.5)
            add_swarm_message(swarm_id, "w_new", "Role", "New matches here")
            
        task = asyncio.create_task(broadcast_delayed())
        res = await wait_for_swarm_message(swarm_id, "matches here", timeout_seconds=3)
        assert "Match found!" in res
        assert "New matches here" in res
        await task
        
    finally:
        with _conn_ctx() as conn:
            conn.execute("DELETE FROM swarm_messages WHERE swarm_id = ?", (swarm_id,))
