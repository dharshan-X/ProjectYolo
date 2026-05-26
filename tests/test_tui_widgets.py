import pytest
from textual.app import App, ComposeResult
from tui_widgets import StopwatchWidget, TimerWidget
from textual.widgets import Label, Button, Input

class StopwatchApp(App):
    def compose(self) -> ComposeResult:
        yield StopwatchWidget(id="stopwatch")

class TimerApp(App):
    def compose(self) -> ComposeResult:
        yield TimerWidget(id="timer")

@pytest.mark.asyncio
async def test_stopwatch():
    app = StopwatchApp()
    async with app.run_test() as pilot:
        stopwatch = app.query_one("#stopwatch", StopwatchWidget)
        assert stopwatch.running is False
        assert stopwatch.elapsed == 0.0
        
        display = stopwatch.query_one("#stopwatch-display", Label)
        assert display.content == "00:00.00"
        
        # Start stopwatch
        await pilot.click("#stopwatch-toggle")
        await pilot.pause(0.1)
        assert stopwatch.running is True
        
        # Capture a lap
        await pilot.click("#stopwatch-lap")
        await pilot.pause(0.1)
        assert len(stopwatch.laps) == 1
        
        # Pause stopwatch
        await pilot.click("#stopwatch-toggle")
        await pilot.pause(0.1)
        assert stopwatch.running is False
        
        # Reset stopwatch
        await pilot.click("#stopwatch-reset")
        await pilot.pause(0.1)
        assert stopwatch.running is False
        assert stopwatch.elapsed == 0.0
        assert len(stopwatch.laps) == 0

@pytest.mark.asyncio
async def test_timer():
    app = TimerApp()
    async with app.run_test() as pilot:
        timer = app.query_one("#timer", TimerWidget)
        assert timer.duration == 0
        assert timer.running is False
        
        # Test preset buttons
        await pilot.click("#timer-add-10s")
        await pilot.pause(0.1)
        assert timer.duration == 10
        
        await pilot.click("#timer-add-1m")
        await pilot.pause(0.1)
        assert timer.duration == 70
        
        # Reset timer
        await pilot.click("#timer-reset")
        await pilot.pause(0.1)
        assert timer.duration == 0
        
        # Set custom duration via text input
        input_widget = timer.query_one("#timer-input", Input)
        input_widget.focus()
        await pilot.press(*"1:30")
        await pilot.press("enter")
        await pilot.pause(0.1)
        
        assert timer.duration == 90
        
        # Toggle start/pause
        await pilot.click("#timer-toggle")
        await pilot.pause(0.1)
        assert timer.running is True
        
        await pilot.click("#timer-toggle")
        await pilot.pause(0.1)
        assert timer.running is False
        
        # Reset
        await pilot.click("#timer-reset")
        await pilot.pause(0.1)
        assert timer.duration == 0
