import argparse
import asyncio
import sys
import os
from typing import Optional

try:
    import readline  # noqa: F401
except ImportError:
    pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

import agent
from session import SessionManager

console = Console()

async def watchdog_execute(coro, action_name):
    """Wait for a tool to complete, but periodically ask the user if they want to keep waiting."""
    task = asyncio.create_task(coro)
    interval = int(os.getenv("WATCHDOG_INTERVAL", "30"))
    
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=interval)
        except asyncio.TimeoutError:
            console.print(f"\n[bold yellow]yolo>[/bold yellow] Tool '{action_name}' is still running after {interval}s...")
            try:
                decision = await asyncio.to_thread(input, "Keep waiting for completion? (y/N/b): ")
                decision = decision.strip().lower()
            except (EOFError, KeyboardInterrupt):
                decision = "n"
            
            if decision in {"y", "yes", ""}:
                continue
            elif decision in {"b", "background"}:
                # We return a special status that tell the caller to background the turn
                return "__BACKGROUND__"
            else:
                task.cancel()
                return "Task cancelled by user."


async def repl(user_id: int, initial_prompt: Optional[str] = None) -> None:
    session_manager = SessionManager(timeout_minutes=60)
    session = session_manager.get_or_create(user_id)

    if not initial_prompt:
        console.print(Panel("[bold green]YOLO CLI Agentic IDE Ready[/bold green]\nType `exit` to quit.", expand=False))
    
    first_turn = True
    while True:
        try:
            if initial_prompt and first_turn:
                text = initial_prompt
                first_turn = False
            else:
                if initial_prompt: # Exit after first turn in non-interactive mode
                    break
                text = await asyncio.to_thread(input, "you> ")
                text = text.strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold red]bye[/bold red]")
            break

        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        current_prompt = text
        is_resume = False
        
        while True:
            try:
                last_full_content = ""
                
                async def cli_signal_handler(msg: str):
                    nonlocal last_full_content
                    if msg.startswith(agent.TUIMessage.STREAM + ":"):
                        content = msg[len(agent.TUIMessage.STREAM) + 1:]
                        last_full_content = content
                        # For CLI we don't necessarily want to live-stream Markdown to avoid flickering
                        # but we can show status updates.
                    elif msg.startswith(agent.TUIMessage.TOOL_CALL + ":"):
                        import json
                        data = json.loads(msg[len(agent.TUIMessage.TOOL_CALL) + 1:])
                        console.print(f"[bold cyan]tool call>[/bold cyan] {data['name']}({data['args']})")

                response = await agent.run_agent_turn(
                    current_prompt if not is_resume else None,
                    session,
                    signal_handler=cli_signal_handler,
                    memory_service=session_manager.memory,
                )
                
                console.print("\n[bold green]yolo>[/bold green]")
                console.print(Markdown(response))
                console.print("-" * 20)
                
                session_manager.save(user_id)
                break # Turn completed successfully
            except agent.PendingConfirmationError as e:
                console.print(Panel(f"Action: [bold]{e.action}[/bold]\nPath: [cyan]{e.path}[/cyan]", title="Confirmation Needed", border_style="yellow"))
                try:
                    decision = await asyncio.to_thread(input, "Approve and wait for completion? (y/N/background): ")
                    decision = decision.strip().lower()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[bold red]Action denied.[/bold red]")
                    break
                
                if decision in {"y", "yes"}:
                    result = await watchdog_execute(
                        agent.execute_tool_direct(
                            e.action,
                            e.tool_args,
                            user_id,
                            signal_handler=None,
                            session=session,
                            confirmed=True,
                        ),
                        e.action
                    )
                    
                    if result == "__BACKGROUND__":
                        console.print("[bold yellow]yolo>[/bold yellow] Turning current mission into a background task...")
                        await agent.execute_tool_direct(
                            "run_background_mission",
                            {"objective": current_prompt},
                            user_id,
                            session=session
                        )
                        break # Exit interactive turn

                    console.print(f"[bold cyan]tool result>[/bold cyan]\n{result}")
                    
                    # Update history to replace [HITL_PENDING] with actual result
                    found = False
                    for msg in reversed(session.message_history):
                        if msg.get("role") == "tool" and msg.get("tool_call_id") == e.tool_call_id:
                            msg["content"] = result
                            found = True
                            break
                    if not found:
                        session.message_history.append({
                            "role": "tool",
                            "tool_call_id": e.tool_call_id,
                            "name": e.action,
                            "content": result
                        })
                    
                    session.mark_dirty()
                    session_manager.save(user_id)
                    is_resume = True # Continue the same turn
                    continue
                elif decision in {"b", "background"}:
                    console.print(f"[bold yellow]yolo>[/bold yellow] Backgrounding mission: {current_prompt}")
                    await agent.execute_tool_direct(
                        "run_background_mission",
                        {"objective": current_prompt},
                        user_id,
                        session=session
                    )
                    break # Exit interactive turn
                else:
                    console.print("[bold red]yolo> Action denied.[/bold red]")
                    found = False
                    for msg in reversed(session.message_history):
                        if msg.get("role") == "tool" and msg.get("tool_call_id") == e.tool_call_id:
                            msg["content"] = "Action denied by user."
                            found = True
                            break
                    if not found:
                        session.message_history.append({
                            "role": "tool",
                            "tool_call_id": e.tool_call_id,
                            "name": e.action,
                            "content": "Action denied by user."
                        })
                    session.mark_dirty()
                    session_manager.save(user_id)
                    is_resume = True
                    continue
            except Exception as e:
                console.print(f"[bold red]yolo> Error: {e}[/bold red]")
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Yolo personal CLI")
    parser.add_argument("--user-id", type=int, default=1, help="Local CLI user id")
    parser.add_argument("--tui", action="store_true", default=True, help="Launch TUI interface (default)")
    parser.add_argument("--no-tui", action="store_false", dest="tui", help="Disable TUI and use classic REPL")
    parser.add_argument("prompt", nargs="?", help="Optional prompt to run non-interactively")
    args = parser.parse_args()
    
    # If a prompt is provided, run it once and exit (non-interactive mode)
    if args.prompt:
        asyncio.run(repl(args.user_id, initial_prompt=args.prompt))
        return

    # If tui is enabled and we are in an interactive terminal, launch TUI
    if args.tui and sys.stdin.isatty():
        try:
            from tui import AgenticIDE
            app = AgenticIDE()
            app.run()
        except ImportError:
            print("TUI dependencies not found. Falling back to REPL.")
            asyncio.run(repl(args.user_id))
    else:
        # Fallback to REPL
        asyncio.run(repl(args.user_id))


if __name__ == "__main__":
    main()
