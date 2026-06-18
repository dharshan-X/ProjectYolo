import os
from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer, Horizontal
from textual.widgets import Static, Markdown, Input, LoadingIndicator, Button, Label
from tools.base import format_log_line

class ChatMessage(Static):
    """A single chat message widget."""
    def __init__(self, role: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self._content = content

    def compose(self) -> ComposeResult:
        role_class = f"role-{self.role.lower()}"
        yield Static(self.role.upper(), classes=f"message-role {role_class}")
        yield Markdown(self._content, classes=f"message-content {role_class}")

class ChatWidget(Vertical):
    """A widget to display a list of chat messages."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_assistant_msg = None
        self.loading_indicator = None

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="message-list"):
            yield Vertical(id="message-container")

    def show_loading(self):
        if not self.loading_indicator:
            container = self.query_one("#message-container", Vertical)
            self.loading_indicator = LoadingIndicator()
            container.mount(self.loading_indicator)
            self.loading_indicator.scroll_visible()

    def hide_loading(self):
        if self.loading_indicator:
            self.loading_indicator.remove()
            self.loading_indicator = None

    def append_message(self, role: str, content: str):
        self.hide_loading()
        container = self.query_one("#message-container", Vertical)
        new_msg = ChatMessage(role=role, content=content)
        container.mount(new_msg)
        new_msg.scroll_visible()
        if role == "assistant":
            self.last_assistant_msg = new_msg
        else:
            self.last_assistant_msg = None

    async def update_live_message(self, content: str):
        self.hide_loading()
        if self.last_assistant_msg is not None:
            # Markdown update might be awaitable in newer Textual versions
            update_task = self.last_assistant_msg.query_one(Markdown).update(content)
            import inspect
            import asyncio
            if inspect.isawaitable(update_task):
                await update_task
            self.last_assistant_msg.scroll_visible()
            # Force UI to process events and render immediately
            await asyncio.sleep(0)
        else:
            self.append_message("assistant", content)
            import asyncio
            await asyncio.sleep(0)

    def end_live_message(self):
        self.hide_loading()
        self.last_assistant_msg = None

class UserInput(Input):

    """A custom input widget for user prompts."""
    pass

class WorkWidget(Vertical):
    """A widget to display agent activity and system health."""
    def compose(self) -> ComposeResult:
        yield Static("No tool running", id="current-tool", classes="work-subpanel")
        yield Static("Background Tasks", id="background-tasks", classes="work-subpanel")
        yield Static("System Health", id="system-health", classes="work-subpanel")

    def update_tool(self, tool_name: str, args: dict):
        tool_panel = self.query_one("#current-tool", Static)
        args_str = str(args)
        if len(args_str) > 25:
            args_str = args_str[:22] + "..."
        tool_panel.update(f"[b]Tool:[/b] {tool_name} [i]{args_str}[/i]")

    def update_background_tasks(self, tasks: list):
        tasks_panel = self.query_one("#background-tasks", Static)
        if not tasks:
            tasks_panel.update("[b]Tasks:[/b] None")
            return
        
        content = "[b]Tasks:[/b]\n"
        for task_id, objective, status, _created_at in tasks:
            content += f"- {task_id[:6]}: {objective[:12]} ({status})\n"
        tasks_panel.update(content.rstrip())

    def update_health(self, health: dict):
        health_panel = self.query_one("#system-health", Static)
        content = "[b]System Health:[/b]\n"
        content += f"LLM: {health.get('llm_provider')} ({health.get('model_name')})\n"
        content += f"Tokens: {health.get('total_tokens', 0)} | Tasks: {health.get('running_background_tasks')} | Crons: {health.get('active_crons')}"
        if health.get('db_error'):
            content += f"\nDB Error: {health.get('db_error')}"
        health_panel.update(content)

class LogWidget(Vertical):
    """A widget to display logs from agent_log.txt."""
    def compose(self) -> ComposeResult:
        yield Static("Log Activity", id="log-title")
        yield ScrollableContainer(Static("", id="log-content"), id="log-scroll")

    def update_logs(self, log_path: str):
        content_panel = self.query_one("#log-content", Static)
        try:
            if not os.path.exists(log_path):
                content_panel.update("Log file not found.")
                return
            
            with open(log_path, "r") as f:
                # Read last 50 lines for better context
                lines = f.readlines()
                last_lines = [format_log_line(line.strip()) for line in lines[-50:]]
                content_panel.update("\n".join(last_lines))
                # Auto-scroll to bottom
                self.query_one("#log-scroll").scroll_end(animate=False)
        except Exception as e:
            content_panel.update(f"Error reading logs: {e}")


import time

class StopwatchWidget(Static):
    """A stopwatch widget with lap-time recording."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.start_time = 0.0
        self.elapsed = 0.0
        self.running = False
        self.laps = []
        self.update_timer = None

    def on_mount(self) -> None:
        self.update_laps_display()

    def on_unmount(self) -> None:
        # Cancel the refresh interval so it doesn't outlive the widget
        # (leaked Textual timers keep firing on the event loop otherwise).
        if self.update_timer:
            self.update_timer.stop()
            self.update_timer = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="widget-header"):
            yield Label("Stopwatch", classes="widget-title")
            yield Label("00:00.00", id="stopwatch-display", classes="time-display")
        with Horizontal(classes="controls-row"):
            yield Button("Start", id="stopwatch-toggle", variant="success")
            yield Button("Lap", id="stopwatch-lap")
            yield Button("Reset", id="stopwatch-reset", variant="error")
        yield Static("", id="stopwatch-laps", classes="laps-display")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "stopwatch-toggle":
            if not self.running:
                # Start
                self.running = True
                self.start_time = time.time() - self.elapsed
                event.button.label = "Pause"
                event.button.variant = "warning"
                self.update_timer = self.set_interval(0.05, self.update_display)
            else:
                # Pause
                self.running = False
                self.elapsed = time.time() - self.start_time
                event.button.label = "Resume"
                event.button.variant = "success"
                if self.update_timer:
                    self.update_timer.stop()
        elif button_id == "stopwatch-reset":
            self.running = False
            self.start_time = 0.0
            self.elapsed = 0.0
            self.laps = []
            if self.update_timer:
                self.update_timer.stop()
            self.query_one("#stopwatch-display", Label).update("00:00.00")
            toggle_btn = self.query_one("#stopwatch-toggle", Button)
            toggle_btn.label = "Start"
            toggle_btn.variant = "success"
            self.query_one("#stopwatch-laps", Static).update("No laps yet")
        elif button_id == "stopwatch-lap":
            if self.running or self.elapsed > 0:
                current_time = (time.time() - self.start_time) if self.running else self.elapsed
                self.laps.append(current_time)
                self.update_laps_display()

    def update_display(self) -> None:
        if self.running:
            current_time = time.time() - self.start_time
            self.query_one("#stopwatch-display", Label).update(self.format_time(current_time))

    def update_laps_display(self) -> None:
        laps_widget = self.query_one("#stopwatch-laps", Static)
        if not self.laps:
            laps_widget.display = False
            return
        
        laps_widget.display = True
        # Show recent laps, e.g. last 3
        lap_lines = []
        for i, lap_time in enumerate(reversed(self.laps)):
            lap_num = len(self.laps) - i
            lap_lines.append(f"Lap {lap_num:02d}: {self.format_time(lap_time)}")
        
        display_lines = lap_lines[:3]
        if len(lap_lines) > 3:
            display_lines.append("...")
        laps_widget.update("\n".join(display_lines))

    def format_time(self, seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        return f"{mins:02d}:{secs:02d}.{centiseconds:02d}"


class TimerWidget(Static):
    """A countdown timer widget."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.duration = 0  # remaining time in seconds
        self.running = False
        self.countdown_timer = None
        self.is_flashing = False
        self.flash_timer = None

    def on_unmount(self) -> None:
        # Cancel intervals so they don't outlive the widget (leaked Textual
        # timers keep firing on the event loop otherwise).
        if self.countdown_timer:
            self.countdown_timer.stop()
            self.countdown_timer = None
        if self.flash_timer:
            self.flash_timer.stop()
            self.flash_timer = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="widget-header"):
            yield Label("Timer", classes="widget-title")
            yield Label("00:00", id="timer-display", classes="time-display")
        with Horizontal(classes="controls-row"):
            yield Button("Start", id="timer-toggle", variant="success")
            yield Button("Reset", id="timer-reset", variant="error")
        with Horizontal(classes="presets-row"):
            yield Button("+10s", id="timer-add-10s", classes="btn-preset")
            yield Button("+1m", id="timer-add-1m", classes="btn-preset")
            yield Button("+5m", id="timer-add-5m", classes="btn-preset")
        yield Input(placeholder="Custom (e.g. 5:00)", id="timer-input")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "timer-toggle":
            if self.duration <= 0:
                self.parse_input_time()
            
            if self.duration > 0:
                if not self.running:
                    self.running = True
                    event.button.label = "Pause"
                    event.button.variant = "warning"
                    self.countdown_timer = self.set_interval(1.0, self.decrement_timer)
                    self.stop_alarm()
                else:
                    self.running = False
                    event.button.label = "Resume"
                    event.button.variant = "success"
                    if self.countdown_timer:
                        self.countdown_timer.stop()
        elif button_id == "timer-reset":
            self.running = False
            self.duration = 0
            if self.countdown_timer:
                self.countdown_timer.stop()
            self.stop_alarm()
            self.update_display()
            toggle_btn = self.query_one("#timer-toggle", Button)
            toggle_btn.label = "Start"
            toggle_btn.variant = "success"
        elif button_id == "timer-add-10s":
            self.adjust_duration(10)
        elif button_id == "timer-add-1m":
            self.adjust_duration(60)
        elif button_id == "timer-add-5m":
            self.adjust_duration(300)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "timer-input":
            self.parse_input_time()
            event.input.value = ""

    def parse_input_time(self) -> None:
        val = self.query_one("#timer-input", Input).value.strip()
        if not val:
            return
        
        try:
            if ":" in val:
                parts = val.split(":")
                if len(parts) == 2:
                    m, s = int(parts[0]), int(parts[1])
                    self.duration = m * 60 + s
                elif len(parts) == 3:
                    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                    self.duration = h * 3600 + m * 60 + s
            else:
                self.duration = int(val)
            
            self.stop_alarm()
            self.update_display()
        except ValueError:
            pass

    def adjust_duration(self, seconds: int) -> None:
        self.duration += seconds
        if self.duration < 0:
            self.duration = 0
        self.stop_alarm()
        self.update_display()

    def decrement_timer(self) -> None:
        if self.running and self.duration > 0:
            self.duration -= 1
            self.update_display()
            if self.duration == 0:
                self.running = False
                if self.countdown_timer:
                    self.countdown_timer.stop()
                toggle_btn = self.query_one("#timer-toggle", Button)
                toggle_btn.label = "Start"
                toggle_btn.variant = "success"
                self.trigger_alarm()

    def update_display(self) -> None:
        mins = self.duration // 60
        secs = self.duration % 60
        self.query_one("#timer-display", Label).update(f"{mins:02d}:{secs:02d}")

    def trigger_alarm(self) -> None:
        self.is_flashing = True
        self.flash_timer = self.set_interval(0.5, self.toggle_flash_class)

    def stop_alarm(self) -> None:
        self.is_flashing = False
        if self.flash_timer:
            self.flash_timer.stop()
            self.flash_timer = None
        self.remove_class("timer-ringing")

    def toggle_flash_class(self) -> None:
        if self.is_flashing:
            if "timer-ringing" in self.classes:
                self.remove_class("timer-ringing")
            else:
                self.add_class("timer-ringing")

