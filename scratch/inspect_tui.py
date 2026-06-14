import asyncio
from tui import AgenticIDE

def print_widget_tree(widget, level=0):
    indent = "  " * level
    # Get styles
    h_style = widget.styles.height
    w_style = widget.styles.width
    # Print widget info
    print(f"{indent}- {widget.__class__.__name__} (id={widget.id!r}, classes={list(widget.classes)})")
    print(f"{indent}  Region: {widget.region} | Visible: {widget.visible} | Display: {widget.display}")
    print(f"{indent}  CSS Sizing: width={w_style}, height={h_style}")
    
    # Recurse children
    for child in widget.children:
        print_widget_tree(child, level + 1)

async def inspect():
    app = AgenticIDE()
    async with app.run_test() as pilot:
        await pilot.pause(0.5)
        
        print("=== STACKED LAYOUT WIDGET TREE ===")
        print_widget_tree(app.screen)
        
        try:
            stopwatch = app.query_one("#work-stopwatch")
            print("\n=== Stopwatch Widget ===")
            print("Visible:", stopwatch.visible)
            print("Display:", stopwatch.display)
            print("Region:", stopwatch.region)
        except Exception as e:
            print("Error finding stopwatch widget:", e)
        
        try:
            timer = app.query_one("#work-timer")
            print("\n=== Timer Widget ===")
            print("Visible:", timer.visible)
            print("Display:", timer.display)
            print("Region:", timer.region)
        except Exception as e:
            print("Error finding timer widget:", e)

if __name__ == "__main__":
    asyncio.run(inspect())
