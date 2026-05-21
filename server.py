import argparse
import asyncio
import logging
import os

from discord_gateway import run_discord_gateway
from health_server import run_health_server

logger = logging.getLogger(__name__)

async def _serve(mode: str) -> None:
    tasks = []

    if mode in {"telegram", "all"}:
        from bot import main as telegram_main

        # Run telegram polling in a worker thread.
        tasks.append(asyncio.create_task(asyncio.to_thread(telegram_main)))

    if mode == "all":
        logger.warning(
            "Running multiple gateways in '--mode all'. Note: Telegram runs in a separate "
            "thread with its own event loop. Sessions and asyncio locks are NOT shared "
            "between gateways."
        )

    if mode in {"discord", "all"}:
        tasks.append(asyncio.create_task(run_discord_gateway()))

    if os.getenv("ENABLE_HEALTH_SERVER", "true").lower() == "true":
        host = os.getenv("HEALTH_SERVER_HOST", "0.0.0.0")
        port = int(os.getenv("HEALTH_SERVER_PORT", "8787"))
        tasks.append(
            asyncio.create_task(asyncio.to_thread(run_health_server, host, port))
        )

    if not tasks:
        raise RuntimeError("No gateway selected.")

    try:
        await asyncio.gather(*tasks)
    finally:
        # Graceful shutdown: cancel background missions and close DB
        from tools.background_ops import cancel_all_background_tasks
        from tools.database_ops import close_db
        await cancel_all_background_tasks()
        close_db()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Yolo gateway server wrapper (Telegram/Discord-ready).",
    )
    parser.add_argument(
        "--mode",
        choices=["telegram", "discord", "all"],
        default="telegram",
        help="Gateway mode to start.",
    )
    args = parser.parse_args()
    asyncio.run(_serve(args.mode))


if __name__ == "__main__":
    main()
