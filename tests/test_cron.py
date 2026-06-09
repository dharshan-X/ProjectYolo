import pytest
from pathlib import Path
from unittest.mock import MagicMock
import sqlite3
import tools.database_ops as db_ops
from tools.cron_ops import schedule_daily_task, schedule_task, get_scheduled_tasks, cancel_scheduled_task
from tools.database_ops import add_cron, get_due_crons, update_cron_run, list_crons, delete_cron, init_db

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    # Direct database path to a temp file
    test_db = tmp_path / "test_yolo_v2.db"
    monkeypatch.setattr(db_ops, "DB_PATH", test_db)
    
    # Reset the shared connection so it points to the new test db
    monkeypatch.setattr(db_ops, "_shared_conn", None)
    
    # Initialize the db schema
    init_db()
    
    yield test_db
    
    # Clean up connection
    with db_ops._conn_lock:
        if db_ops._shared_conn:
            db_ops._shared_conn.close()
            db_ops._shared_conn = None

def test_add_cron_and_list():
    user_id = 123
    desc = "Clean temporary files"
    interval = 30
    
    # Verify no tasks initially
    assert len(list_crons(user_id)) == 0
    
    # Add task
    add_cron(user_id, desc, interval)
    
    # Verify listed
    tasks = list_crons(user_id)
    assert len(tasks) == 1
    cron_id, task_desc, next_run = tasks[0]
    assert task_desc == desc
    assert next_run is not None

def test_invalid_interval():
    with pytest.raises(ValueError):
        add_cron(123, "Invalid interval", -5)
    with pytest.raises(ValueError):
        add_cron(123, "Invalid interval", 0)

def test_cron_ops_wrappers():
    user_id = 456
    
    # Schedule task
    res = schedule_task(user_id, "Backup database", 60)
    assert "successfully" in res
    assert "every 60 minutes" in res
    
    # Schedule daily task
    res_daily = schedule_daily_task(user_id, "Daily report")
    assert "successfully" in res_daily
    assert "every day" in res_daily
    
    # Get scheduled tasks
    tasks_str = get_scheduled_tasks(user_id)
    assert "Backup database" in tasks_str
    assert "Daily report" in tasks_str
    
    # Cancel task
    # First find the ID
    tasks = list_crons(user_id)
    assert len(tasks) == 2
    cron_id_1 = tasks[0][0]
    
    cancel_res = cancel_scheduled_task(user_id, cron_id_1)
    assert f"Scheduled task `{cron_id_1}` has been cancelled" in cancel_res
    
    # Get again and verify it's gone
    tasks_str_after = get_scheduled_tasks(user_id)
    assert f"ID `{cron_id_1}`" not in tasks_str_after

def test_due_crons_and_update(tmp_path, monkeypatch):
    user_id = 789
    
    # Directly insert a cron with a past next_run so it's due
    with db_ops._conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO crons (user_id, task_description, interval_minutes, next_run) VALUES (?, ?, ?, datetime('now', '-5 minutes'))",
            (user_id, "Past task", 10)
        )
    
    due = get_due_crons()
    assert len(due) >= 1
    past_cron = [c for c in due if c[2] == "Past task"]
    assert len(past_cron) == 1
    cron_id, uid, desc, interval = past_cron[0]
    assert uid == user_id
    assert desc == "Past task"
    assert interval == 10
    
    # Update cron run
    update_cron_run(cron_id, interval)
    
    # Verify no longer due (since next_run is now set to 10 minutes in the future)
    due_after = get_due_crons()
    past_cron_after = [c for c in due_after if c[0] == cron_id]
    assert len(past_cron_after) == 0


def test_timezone_formatting():
    from tools.cron_ops import format_utc_to_local
    from datetime import datetime, timezone
    
    # Test valid UTC string from SQLite standard format
    local_str = format_utc_to_local("2026-05-20 12:40:37")
    expected = datetime.strptime("2026-05-20 12:40:37", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    assert local_str == expected
    
    # Test ISO format with Z
    iso_z_str = format_utc_to_local("2026-05-20T12:40:37Z")
    assert iso_z_str == expected

    # Test naive ISO format (treated as UTC)
    iso_naive_str = format_utc_to_local("2026-05-20T12:40:37")
    assert iso_naive_str == expected

    # Test invalid / fallback
    assert format_utc_to_local("") == "Never"
    assert format_utc_to_local(None) == "Never"
    assert format_utc_to_local("invalid date string") == "invalid date string"

