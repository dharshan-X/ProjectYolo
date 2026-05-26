import asyncio
import os
import sys

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tui import AgenticIDE

async def capture():
    app = AgenticIDE()
    async with app.run_test() as pilot:
        await pilot.pause(1.0)
        # Export HTML representation
        html = app.export_html()
        os.makedirs("scratch", exist_ok=True)
        with open("scratch/tui_capture.html", "w") as f:
            f.write(html)
        
        # Export text representation
        text = app.export_text()
        with open("scratch/tui_capture.txt", "w") as f:
            f.write(text)
            
        print("TUI screens captured successfully!")

if __name__ == "__main__":
    asyncio.run(capture())
