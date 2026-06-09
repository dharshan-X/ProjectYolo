import re

with open("desktop/renderer/app.js", "r") as f:
    content = f.read()

# 1. Remove widgetsToggleBtn declarations
content = re.sub(r"^\s*widgetsToggleBtn:\s*\$\('#widgets-toggle-btn'\),\n?", "", content, flags=re.MULTILINE)

# 2. Remove old renderActiveWidget logic for timer/stopwatch
old_render_logic = """    } else if (data.type === 'timer' || data.type === 'stopwatch') {
      // Auto-open the widgets panel in the sidebar
      if (dom.widgetsPanel && dom.widgetsPanel.classList.contains('collapsed')) {
        if (dom.widgetsToggleBtn) {
          dom.widgetsToggleBtn.click();
        } else {
          dom.widgetsPanel.classList.remove('collapsed');
          if (dom.workersPanel) dom.workersPanel.classList.add('collapsed');
        }
      }
      
      // Auto-configure the timer if duration is provided
      if (data.type === 'timer' && data.duration !== undefined) {
        if (typeof resetTimer === 'function') resetTimer();
        timerState.duration = parseInt(data.duration, 10);
        if (typeof updateTimerDisplay === 'function') updateTimerDisplay();
        
        if (data.action === 'start' && typeof startTimer === 'function') {
          startTimer();
        }
      } else if (data.type === 'stopwatch' && data.action === 'start') {
        if (typeof startStopwatch === 'function') startStopwatch();
      }
      
      return; // Do not render an inline widget"""

content = content.replace(old_render_logic, "")

# 3. Remove old global timer state and functions
# Lines 1094 to 1335 roughly
old_timer_funcs = re.search(r"// ── Stopwatch & Timer State ──.*?// ── Events ──", content, flags=re.DOTALL)
if old_timer_funcs:
    content = content.replace(old_timer_funcs.group(0), "// ── Events ──")

# 4. Remove widgetsToggleBtn event listeners
sidebar_events = re.search(r"if \(dom.widgetsToggleBtn && dom.widgetsPanel\).*?dom\.widgetsToggleBtn\.focus\(\);\s*\}\s*\}\);", content, flags=re.DOTALL)
if sidebar_events:
    content = content.replace(sidebar_events.group(0), "")

# 5. Inject markdown parser changes
old_markdown_parser = """              if (data && data.type && typeof renderActiveWidget === 'function') {
                // If it successfully parses and has a type, treat it as a widget
                renderActiveWidget(data);
                return `<div class="widget-placeholder"><em>[Interactive Widget Expanded]</em></div>`;
              }"""

new_markdown_parser = """              if (data && data.type) {
                if (data.type === 'timer') {
                  const widgetId = 'timer-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
                  const duration = data.duration !== undefined ? parseInt(data.duration, 10) : 0;
                  const autoStart = data.action === 'start';
                  return `
                    <div class="inline-widget utility-widget inline-timer" id="${widgetId}" data-duration="${duration}" data-autostart="${autoStart}" data-rendered="false">
                      <div class="utility-widget-header">
                        <span class="utility-widget-title">Timer</span>
                        <span class="utility-time-display timer-display">00:00</span>
                      </div>
                      <div class="utility-controls-row">
                        <button class="utility-btn success-btn timer-toggle-btn">Start</button>
                        <button class="utility-btn error-btn timer-reset-btn">Reset</button>
                      </div>
                      <div class="utility-presets-row">
                        <button class="preset-btn timer-add-10s">+10s</button>
                        <button class="preset-btn timer-add-1m">+1m</button>
                        <button class="preset-btn timer-add-5m">+5m</button>
                      </div>
                    </div>
                  `;
                } else if (data.type === 'stopwatch') {
                  const widgetId = 'stopwatch-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
                  const autoStart = data.action === 'start';
                  return `
                    <div class="inline-widget utility-widget inline-stopwatch" id="${widgetId}" data-autostart="${autoStart}" data-rendered="false">
                      <div class="utility-widget-header">
                        <span class="utility-widget-title">Stopwatch</span>
                        <span class="utility-time-display stopwatch-display">00:00.00</span>
                      </div>
                      <div class="utility-controls-row">
                        <button class="utility-btn success-btn stopwatch-toggle-btn">Start</button>
                        <button class="utility-btn stopwatch-lap-btn">Lap</button>
                        <button class="utility-btn error-btn stopwatch-reset-btn">Reset</button>
                      </div>
                      <div class="utility-laps-container stopwatch-laps"></div>
                    </div>
                  `;
                } else if (typeof renderActiveWidget === 'function') {
                  renderActiveWidget(data);
                  return `<div class="widget-placeholder"><em>[Interactive Widget Expanded]</em></div>`;
                }
              }"""

content = content.replace(old_markdown_parser, new_markdown_parser)

# 6. Inject new inline timer logic in initializeInlineWidgets
old_init_widgets = "  async function initializeInlineWidgets(container) {"

new_init_widgets = """  async function initializeInlineWidgets(container) {
    if (!container) return;

    // --- Inline Timers ---
    container.querySelectorAll('.inline-timer:not([data-rendered="true"])').forEach(el => {
      el.setAttribute('data-rendered', 'true');
      let duration = parseInt(el.getAttribute('data-duration') || '0', 10);
      let running = false;
      let intervalId = null;
      let isFlashing = false;

      const display = el.querySelector('.timer-display');
      const toggleBtn = el.querySelector('.timer-toggle-btn');
      const resetBtn = el.querySelector('.timer-reset-btn');

      const formatTime = (secs) => {
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      };

      const updateDisplay = () => { display.textContent = formatTime(duration); };
      updateDisplay();

      const triggerAlarm = () => {
        isFlashing = true;
        el.classList.add('timer-ringing');
        if (window.Notification && Notification.permission === 'granted') {
          new Notification('Timer Finished', { body: 'Your inline timer has ended!' });
        }
      };
      
      const stopAlarm = () => {
        isFlashing = false;
        el.classList.remove('timer-ringing');
      };

      const start = () => {
        if (duration <= 0 || running) return;
        running = true;
        toggleBtn.textContent = 'Pause';
        toggleBtn.className = 'utility-btn warning-btn';
        stopAlarm();
        intervalId = setInterval(() => {
          if (duration > 0) {
            duration--;
            updateDisplay();
            if (duration === 0) {
              pause();
              triggerAlarm();
            }
          }
        }, 1000);
      };

      const pause = () => {
        running = false;
        toggleBtn.textContent = duration > 0 ? 'Resume' : 'Start';
        toggleBtn.className = 'utility-btn success-btn';
        if (intervalId) { clearInterval(intervalId); intervalId = null; }
      };

      const reset = () => {
        pause();
        duration = 0;
        stopAlarm();
        updateDisplay();
      };

      const adjust = (secs) => {
        duration = Math.max(0, duration + secs);
        stopAlarm();
        updateDisplay();
        if (!running) toggleBtn.textContent = duration > 0 ? 'Resume' : 'Start';
      };

      toggleBtn.addEventListener('click', () => running ? pause() : start());
      resetBtn.addEventListener('click', reset);
      el.querySelector('.timer-add-10s')?.addEventListener('click', () => adjust(10));
      el.querySelector('.timer-add-1m')?.addEventListener('click', () => adjust(60));
      el.querySelector('.timer-add-5m')?.addEventListener('click', () => adjust(300));
      
      if (el.getAttribute('data-autostart') === 'true') {
        start();
      }
    });

    // --- Inline Stopwatches ---
    container.querySelectorAll('.inline-stopwatch:not([data-rendered="true"])').forEach(el => {
      el.setAttribute('data-rendered', 'true');
      let running = false;
      let startTime = 0;
      let elapsed = 0;
      let laps = [];
      let intervalId = null;

      const display = el.querySelector('.stopwatch-display');
      const toggleBtn = el.querySelector('.stopwatch-toggle-btn');
      const lapBtn = el.querySelector('.stopwatch-lap-btn');
      const resetBtn = el.querySelector('.stopwatch-reset-btn');
      const lapsContainer = el.querySelector('.stopwatch-laps');

      const formatTime = (ms) => {
        const totalSeconds = ms / 1000;
        const mins = Math.floor(totalSeconds / 60);
        const secs = Math.floor(totalSeconds % 60);
        const centi = Math.floor((ms % 1000) / 10);
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(centi).padStart(2, '0')}`;
      };

      const updateDisplay = () => {
        const currentElapsed = running ? (Date.now() - startTime) : elapsed;
        display.textContent = formatTime(currentElapsed);
      };

      const updateLaps = () => {
        lapsContainer.innerHTML = '';
        const reversedLaps = [...laps].reverse();
        reversedLaps.slice(0, 3).forEach((lapTime, i) => {
          const lapNum = laps.length - i;
          const row = document.createElement('div');
          row.className = 'utility-lap-row';
          row.innerHTML = `<span>Lap ${String(lapNum).padStart(2, '0')}</span><span>${formatTime(lapTime)}</span>`;
          lapsContainer.appendChild(row);
        });
        if (reversedLaps.length > 3) {
          const moreRow = document.createElement('div');
          moreRow.className = 'utility-lap-row';
          moreRow.style.justifyContent = 'center';
          moreRow.innerHTML = '<span style="color: var(--text-muted);">...</span>';
          lapsContainer.appendChild(moreRow);
        }
      };

      const start = () => {
        if (running) return;
        running = true;
        startTime = Date.now() - elapsed;
        toggleBtn.textContent = 'Pause';
        toggleBtn.className = 'utility-btn warning-btn';
        intervalId = setInterval(updateDisplay, 10);
      };

      const pause = () => {
        if (!running) return;
        running = false;
        elapsed = Date.now() - startTime;
        toggleBtn.textContent = 'Resume';
        toggleBtn.className = 'utility-btn success-btn';
        if (intervalId) { clearInterval(intervalId); intervalId = null; }
        updateDisplay();
      };

      const reset = () => {
        running = false;
        startTime = 0;
        elapsed = 0;
        laps = [];
        if (intervalId) { clearInterval(intervalId); intervalId = null; }
        display.textContent = '00:00.00';
        toggleBtn.textContent = 'Start';
        toggleBtn.className = 'utility-btn success-btn';
        lapsContainer.innerHTML = '';
      };

      const recordLap = () => {
        if (!running && elapsed === 0) return;
        const lapTime = running ? (Date.now() - startTime) : elapsed;
        laps.push(lapTime);
        updateLaps();
      };

      toggleBtn.addEventListener('click', () => running ? pause() : start());
      lapBtn.addEventListener('click', recordLap);
      resetBtn.addEventListener('click', reset);
      
      if (el.getAttribute('data-autostart') === 'true') {
        start();
      }
    });"""

content = content.replace(old_init_widgets, new_init_widgets)

with open("desktop/renderer/app.js", "w") as f:
    f.write(content)

print("Refactor completed.")
