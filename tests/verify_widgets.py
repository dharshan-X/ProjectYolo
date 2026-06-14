from pathlib import Path

def test_widgets_integration():
    # 1. Verify HTML elements in index.html
    index_html = Path("desktop/renderer/index.html").read_text()
    assert "widgets-toggle-btn" in index_html, "Missing widgets-toggle-btn in index.html"
    assert "widgets-panel" in index_html, "Missing widgets-panel in index.html"
    assert "desktop-stopwatch" in index_html, "Missing desktop-stopwatch in index.html"
    assert "desktop-timer" in index_html, "Missing desktop-timer in index.html"
    assert "desktop-stopwatch-display" in index_html, "Missing stopwatch display element"
    assert "desktop-timer-display" in index_html, "Missing timer display element"

    # 2. Verify styles in styles.css
    styles_css = Path("desktop/renderer/styles.css").read_text()
    assert ".widgets-panel" in styles_css, "Missing widgets panel styling"
    assert "timer-pulse" in styles_css, "Missing timer alarm keyframes pulse animation"
    assert "timer-ringing" in styles_css, "Missing timer ringing styling class"

    # 3. Verify JavaScript logic in app.js
    app_js = Path("desktop/renderer/app.js").read_text()
    assert "widgetsPanel" in app_js, "Missing widgetsPanel DOM selector in app.js"
    assert "stopwatchState" in app_js, "Missing stopwatchState declaration"
    assert "timerState" in app_js, "Missing timerState declaration"
    assert "formatStopwatchTime" in app_js, "Missing formatStopwatchTime function"
    assert "formatTimerTime" in app_js, "Missing formatTimerTime function"
    assert "startStopwatch" in app_js, "Missing startStopwatch function"
    assert "startTimer" in app_js, "Missing startTimer function"
    assert "widgetsToggleBtn" in app_js, "Missing widgetsToggleBtn listeners"
    
    print("✅ Programmatic verification of Stopwatch & Timer integration passed!")

if __name__ == "__main__":
    try:
        test_widgets_integration()
        print("\nALL WIDGET INTEGRATION VERIFICATIONS PASSED")
    except AssertionError as e:
        print(f"\nVERIFICATION FAILED: {e}")
        exit(1)
