from tools.registry import register_tool
from tools.database_ops import add_cron, list_crons, delete_cron
from tools.base import audit_log


@register_tool()
def schedule_daily_task(user_id: int, task_description: str) -> str:
    """Schedule a recurring daily task (every 24 hours)."""
    try:
        interval_minutes = 24 * 60
        add_cron(user_id, task_description, interval_minutes)
        audit_log(
            "schedule_daily_task",
            {"task": task_description, "interval": interval_minutes},
            "success",
        )
        return f"Daily task scheduled successfully! I will run `{task_description}` every day."
    except Exception as e:
        audit_log("schedule_daily_task", {"task": task_description}, "error", str(e))
        return f"Error scheduling daily task: {e}"


@register_tool()
def schedule_task(user_id: int, task_description: str, interval_minutes: int) -> str:
    """Schedule a recurring autonomous task."""
    try:
        if interval_minutes <= 0:
            return "Error scheduling task: `interval_minutes` must be greater than 0."

        add_cron(user_id, task_description, interval_minutes)
        audit_log(
            "schedule_task",
            {"task": task_description, "interval": interval_minutes},
            "success",
        )
        return f"Task scheduled successfully! I will run `{task_description}` every {interval_minutes} minutes."
    except Exception as e:
        audit_log("schedule_task", {"task": task_description}, "error", str(e))
        return f"Error scheduling task: {e}"


def format_utc_to_local(utc_str: str) -> str:
    if not utc_str:
        return "Never"
    try:
        from datetime import datetime, timezone
        try:
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            utc_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        local_dt = utc_dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return utc_str


@register_tool()
def get_scheduled_tasks(user_id: int) -> str:
    """List all currently active scheduled tasks."""
    try:
        tasks = list_crons(user_id)
        if not tasks:
            return "You have no active scheduled tasks."

        output = "### Active Scheduled Tasks:\n\n"
        for cid, desc, next_run in tasks:
            local_next_run = format_utc_to_local(next_run)
            output += f"- ID `{cid}`: {desc} (Next run: `{local_next_run}`)\n"

        audit_log("get_scheduled_tasks", {}, "success")
        return output
    except Exception as e:
        return f"Error listing tasks: {e}"


@register_tool()
def cancel_scheduled_task(cron_id: int) -> str:
    """Permanently stop and delete a scheduled task by its ID."""
    try:
        deleted = delete_cron(cron_id)
        if not deleted:
            return f"No scheduled task found for ID `{cron_id}`."

        audit_log("cancel_scheduled_task", {"id": cron_id}, "success")
        return f"Scheduled task `{cron_id}` has been cancelled."
    except Exception as e:
        audit_log("cancel_scheduled_task", {"id": cron_id}, "error", str(e))
        return f"Error cancelling task: {e}"
