from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, Static, Button, Label
from textual.screen import ModalScreen
from tui_widgets import ChatWidget, UserInput, WorkWidget, LogWidget, StopwatchWidget, TimerWidget
import asyncio
import agent
from session import SessionManager
import json
import monitoring
from tools import database_ops

class ConfirmationModal(ModalScreen):
    """A modal screen for tool confirmations."""
    def __init__(self, confirmations: list):
        super().__init__()
        self.confirmations = confirmations

    def compose(self) -> ComposeResult:
        count = len(self.confirmations)
        title = "Confirmation Needed" if count == 1 else f"{count} Actions Need Confirmation"
        
        with Grid(id="modal-container"):
            yield Label(title, id="modal-title")
            
            with Vertical(id="modal-actions-list"):
                for i, p in enumerate(self.confirmations):
                    yield Label(f"{i+1}. {p['action']} -> {p['path']}", classes="modal-action-item")
            
            with Horizontal(id="modal-buttons"):
                if count == 1:
                    yield Button("Approve", variant="success", id="approve")
                    yield Button("Background", variant="primary", id="background")
                    yield Button("Deny", variant="error", id="deny")
                else:
                    yield Button("Approve All", variant="success", id="approve_all")
                    yield Button("Deny All", variant="error", id="deny_all")
                    yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

class ChatPanel(Static):
    """The panel for chat interaction."""
    def compose(self) -> ComposeResult:
        yield Static("Chat Panel", id="chat-title")
        yield ChatWidget(id="chat-widget")
        yield UserInput(placeholder="Ask me anything...", id="user-input")

class WorkPanel(Static):
    """The panel for work/code display."""
    def compose(self) -> ComposeResult:
        yield Static("Operations Dashboard", id="work-title")
        yield WorkWidget(id="work-widget")
        yield LogWidget(id="log-widget")
        yield StopwatchWidget(id="work-stopwatch")
        yield TimerWidget(id="work-timer")

def format_tool_call_for_chat(name: str, args: dict) -> str:
    if name == "read_file":
        return f"📖 **Reading file:** `{args.get('path', 'unknown')}`"
    elif name == "write_file":
        content = args.get("content", "")
        if len(content) > 500:
            content = content[:500] + "\n... (truncated)"
        return f"📝 **Writing to file:** `{args.get('path', 'unknown')}`\n```python\n{content}\n```"
    elif name == "edit_file":
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")
        diff_text = f"- {old_text}\n+ {new_text}"
        if len(diff_text) > 500:
            diff_text = diff_text[:500] + "\n... (truncated)"
        return f"✂️ **Editing file:** `{args.get('path', 'unknown')}`\n```diff\n{diff_text}\n```"
    elif name == "run_bash":
        cmd = args.get("command", "")
        return f"🖥️ **Running command:**\n```bash\n{cmd}\n```"
    elif name == "search_in_file":
        return f"🔍 **Searching in:** `{args.get('path', 'unknown')}` for pattern `{args.get('pattern', '')}`"
    elif name == "list_dir":
        return f"📂 **Listing directory:** `{args.get('path', 'unknown')}`"
    return ""

class AgenticIDE(App):
    """A Textual app for the Agentic IDE."""
    TITLE = "YOLO Agentic IDE"
    CSS_PATH = "tui.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "toggle_panel", "Toggle Work Panel")
    ]

    def on_mount(self) -> None:
        self.user_id = 1
        self.session_manager = SessionManager()
        self.session = self.session_manager.get_or_create(self.user_id)
        # Default TUI to YOLO mode for power users
        self.session.yolo_mode = True
        
        self.set_interval(2.0, self.refresh_dashboard)

    def action_toggle_panel(self) -> None:
        work_panel = self.query_one("#work-panel")
        chat_panel = self.query_one("#chat-panel")
        if work_panel.display:
            work_panel.display = False
            chat_panel.styles.width = "100%"
        else:
            work_panel.display = True
            chat_panel.styles.width = "65%"


    def refresh_dashboard(self) -> None:
        work_widget = self.query_one(WorkWidget)
        log_widget = self.query_one(LogWidget)
        
        # Update Health
        health = monitoring.build_health_payload(self.session)
        work_widget.update_health(health)
        
        # Update Background Tasks
        tasks = database_ops.list_background_tasks(user_id=1)
        work_widget.update_background_tasks(tasks)

        # Update Logs
        log_widget.update_logs("agent_log.txt")

    async def on_input_submitted(self, event: UserInput.Submitted) -> None:
        prompt = event.value
        if not prompt:
            return
        
        event.input.value = ""
        event.input.disabled = True
        chat_widget = self.query_one(ChatWidget)
        chat_widget.append_message("user", prompt)
        chat_widget.show_loading()
        
        # Run agent in background
        self.run_worker(self.run_agent(prompt))

    async def run_agent(self, prompt: str) -> None:
        chat_widget = self.query_one(ChatWidget)
        work_widget = self.query_one(WorkWidget)
        user_input = self.query_one(UserInput)
        
        async def signal_handler(msg: str):
            import threading
            is_main_thread = self._thread_id == threading.get_ident()
            
            if msg.startswith(agent.TUIMessage.STREAM + ":"):
                content = msg[len(agent.TUIMessage.STREAM) + 1:]
                if is_main_thread:
                    await chat_widget.update_live_message(content)
                else:
                    # BUG-29 fix: update_live_message is async, wrap with ensure_future
                    self.call_from_thread(lambda c=content: asyncio.ensure_future(chat_widget.update_live_message(c)))
            elif msg.startswith(agent.TUIMessage.TOOL_CALL + ":"):
                data = json.loads(msg[len(agent.TUIMessage.TOOL_CALL) + 1:])
                chat_msg = format_tool_call_for_chat(data["name"], data["args"])
                
                if is_main_thread:
                    work_widget.update_tool(data["name"], data["args"])
                    if chat_msg:
                        chat_widget.append_message("system", chat_msg)
                        chat_widget.show_loading()
                else:
                    self.call_from_thread(work_widget.update_tool, data["name"], data["args"])
                    if chat_msg:
                        def update_chat():
                            chat_widget.append_message("system", chat_msg)
                            chat_widget.show_loading()
                        self.call_from_thread(update_chat)
            elif msg.startswith(agent.TUIMessage.STATUS + ":"):
                # You could add a status bar update here
                pass
            elif msg.startswith("__STREAM_END__:"):
                if is_main_thread:
                    chat_widget.end_live_message()
                else:
                    self.call_from_thread(chat_widget.end_live_message)

        current_prompt = prompt
        is_resume = False
        
        try:
            while True:
                try:
                    await agent.run_agent_turn(
                        current_prompt if not is_resume else None, 
                        self.session, 
                        signal_handler=signal_handler,
                        memory_service=self.session_manager.memory
                    )
                    self.session_manager.save(self.user_id)
                    break
                except agent.PendingConfirmationError:
                    # session.pending_confirmations now contains ALL of them.
                    pending_list = list(self.session.pending_confirmations)
                    modal = ConfirmationModal(pending_list)
                    result = await self.push_screen(modal)  # type: ignore
                    
                    if result == "approve":
                        await agent.resolve_confirmations(
                            self.session, self.session.user_id, signal_handler=signal_handler, confirm_all=False, memory_service=self.session_manager.memory
                        )
                        is_resume = True
                        continue

                    elif result == "approve_all":
                        await agent.resolve_confirmations(
                            self.session, self.session.user_id, signal_handler=signal_handler, confirm_all=True, memory_service=self.session_manager.memory
                        )
                        is_resume = True
                        continue

                    elif result == "deny_all":
                        await agent.deny_confirmations(self.session, deny_all=True)
                        is_resume = True
                        continue

                    elif result == "deny":
                        await agent.deny_confirmations(self.session, deny_all=False)
                        is_resume = True
                        continue

                    elif result == "background":
                        # Background the whole mission
                        await agent.execute_tool_direct(
                            "run_background_mission",
                            {"objective": current_prompt},
                            self.session.user_id,
                            session=self.session
                        )
                        break
                    else:
                        # Deny or cancel
                        break
        finally:
            def reenable_input():
                user_input.disabled = False
                user_input.focus()
            
            import threading
            if self._thread_id == threading.get_ident():
                reenable_input()
            else:
                self.call_from_thread(reenable_input)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield ChatPanel(id="chat-panel")
            yield WorkPanel(id="work-panel")
        yield Footer()

if __name__ == "__main__":
    app = AgenticIDE()
    app.run()
