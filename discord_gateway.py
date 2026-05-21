import asyncio
import logging
import os

import discord
from tools.settings import load_settings

import agent
from session import SessionManager

load_settings()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

logger = logging.getLogger(__name__)

# Keep strong references to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task] = set()


def _is_allowed_user(user_id: int) -> bool:
    raw = os.getenv("DISCORD_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return True
    allowed = {int(v.strip()) for v in raw.split(",") if v.strip()}
    return user_id in allowed


class ConfirmationView(discord.ui.View):
    def __init__(self, session, user_id, session_manager):
        super().__init__(timeout=None)
        self.session = session
        self.user_id = user_id
        self.session_manager = session_manager

    @discord.ui.button(label="Confirm All", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        lock = self.session_manager.get_lock(self.user_id)
        async with lock:
            try:
                response = await agent.resolve_confirmations(
                    self.session, self.user_id, signal_handler=None, confirm_all=True
                )
                self.session_manager.save(self.user_id)
                await interaction.followup.send(response)
                self.stop()
            except Exception as e:
                await interaction.followup.send(f"Error: {e}")

    @discord.ui.button(label="Deny All", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your session!", ephemeral=True)
            return
        
        await interaction.response.defer()
        lock = self.session_manager.get_lock(self.user_id)
        async with lock:
            await agent.deny_confirmations(self.session, deny_all=True)
            response = await agent.run_agent_turn(
                None, self.session, signal_handler=None, memory_service=self.session_manager.memory
            )
            self.session_manager.save(self.user_id)
            await interaction.followup.send(response)
            self.stop()


class DiscordYoloClient(discord.Client):
    def __init__(self, session_manager: SessionManager):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.session_manager = session_manager

    async def on_ready(self):
        logger.info("Discord gateway online as %s", self.user)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not _is_allowed_user(message.author.id):
            return

        text = (message.content or "").strip()
        if not text:
            return

        user_id = int(message.author.id)
        lock = self.session_manager.get_lock(user_id)
        async with lock:
            session = self.session_manager.get_or_create(user_id)
            if session.pending_confirmations:
                view = ConfirmationView(session, user_id, self.session_manager)
                await message.reply(
                    f"You have {len(session.pending_confirmations)} pending actions. Resolve them first:",
                    view=view
                )
                return

            try:
                response = await agent.run_agent_turn(
                    text,
                    session,
                    signal_handler=None,
                    memory_service=self.session_manager.memory,
                )
            except agent.PendingConfirmationError as e:
                self.session_manager.save(user_id)
                view = ConfirmationView(session, user_id, self.session_manager)
                await message.reply(
                    f"⚠️ **Confirmation Required**\nAction: `{e.action}`\nPath: `{e.path}`",
                    view=view
                )
                return
            except Exception as ex:
                logger.exception("Discord turn failed")
                await message.reply(f"Error: {ex}")
                return

            self.session_manager.save(user_id)
            chunks = [
                response[i : i + 1900] for i in range(0, len(response), 1900)
            ] or ["(No response)"]
            for chunk in chunks:
                await message.reply(chunk)



async def run_discord_gateway() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.warning("DISCORD_BOT_TOKEN not set; Discord gateway disabled.")
        return

    session_manager = SessionManager(
        timeout_minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
    )
    task = asyncio.create_task(session_manager.auto_expiry_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    client = DiscordYoloClient(session_manager)
    await client.start(DISCORD_BOT_TOKEN)
