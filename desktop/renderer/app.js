/* ══════════════════════════════════════════════
   YOLO DESKTOP — Renderer Logic
   Shares sessions with Telegram/CLI via the
   same SessionManager → SQLite backend.
   ══════════════════════════════════════════════ */

(() => {
  'use strict';

  // ── State ──
  const state = {
    userId: 1,
    messages: [],       // { role, content, timestamp }
    sessions: [],       // [{ user_id, last_active }]
    isLoading: false,
    yoloMode: false,
    thinkMode: false,
    theme: 'dark',
    sidebarCollapsed: false, // Added for collapsible sidebar
    selectedFiles: [], // Added for visual chips
    activePaletteIndex: -1, // Added for keyboard navigation
    workerStates: {}, // Track task_id -> status
    bridgePort: 8790, // Default fallback
  };

  // ── Helpers ──
  function getFullUrl(url) {
    if (!url) return '';
    if (url.startsWith('/') && !url.startsWith('//')) {
      return `http://127.0.0.1:${state.bridgePort}${url}`;
    }
    return url;
  }

  window.openLink = (url) => {
    if (!url) return;
    const fullUrl = getFullUrl(url);
    if (fullUrl.startsWith('file://')) {
      // For local files, use openPath for better compatibility
      const filePath = fullUrl.replace('file://', '');
      window.yoloAPI.openPath(decodeURIComponent(filePath));
    } else {
      window.yoloAPI.openExternal(fullUrl);
    }
  };

  // State to hold the current widget payload
  window.activeWidgetData = null;

  function clearActiveWidget() {
    window.activeWidgetData = null;
    dom.activeWidgetContainer.innerHTML = '';
    dom.activeWidgetContainer.classList.add('hidden');
    dom.inputWrapper.classList.remove('hidden');
    dom.input.focus();
  }

  function renderActiveWidget(data) {
    window.activeWidgetData = data;
    const title = (data.text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    let contentHtml = '';

    if (data.type === 'choice') {
      const optionsHtml = (data.options || []).map(opt => {
        const labelText = typeof opt === 'object' && opt !== null ? (opt.label || '') : String(opt);
        const valueText = typeof opt === 'object' && opt !== null ? (opt.value || labelText) : String(opt);
        const label = labelText.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const val = valueText.replace(/"/g, '&quot;');
        return `<button class="widget-btn" data-widget-id="${data.id}" data-value="${val}">${label}</button>`;
      }).join('');
      
      let customInputHtml = '';
      if (data.allow_custom) {
        customInputHtml = `
          <div class="widget-custom-input-container">
            <input type="text" class="widget-custom-input" placeholder="Or type your own answer..." data-widget-id="${data.id}">
            <button class="widget-custom-send-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        `;
      }
      contentHtml = `<div class="widget-options">${optionsHtml}</div>${customInputHtml}`;
      
    } else if (data.type === 'confirm') {
      contentHtml = `
        <div class="widget-options confirm-options">
          <button class="widget-btn confirm-yes" data-widget-id="${data.id}" data-value="Yes">Yes</button>
          <button class="widget-btn confirm-no" data-widget-id="${data.id}" data-value="No">No</button>
        </div>
      `;
      
    } else if (data.type === 'multi-select') {
      const optionsHtml = (data.options || []).map(opt => {
        const labelText = typeof opt === 'object' && opt !== null ? (opt.label || '') : String(opt);
        const valueText = typeof opt === 'object' && opt !== null ? (opt.value || labelText) : String(opt);
        const label = labelText.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const val = valueText.replace(/"/g, '&quot;');
        return `<button class="widget-toggle-btn" data-widget-id="${data.id}" data-value="${val}">${label}</button>`;
      }).join('');
      contentHtml = `
        <div class="widget-options multi-options">${optionsHtml}</div>
        <button class="widget-submit-btn multi-submit" data-widget-id="${data.id}">Submit Selection</button>
      `;
      
    } else if (data.type === 'slider') {
      const min = data.min !== undefined ? data.min : 0;
      const max = data.max !== undefined ? data.max : 100;
      const step = data.step !== undefined ? data.step : 1;
      const val = data.value !== undefined ? data.value : Math.floor((min + max) / 2);
      
      contentHtml = `
        <div class="widget-slider-container">
          <div class="slider-header">
            <span class="slider-min">${min}</span>
            <span class="slider-val" id="slider-val-${data.id}">${val}</span>
            <span class="slider-max">${max}</span>
          </div>
          <input type="range" class="widget-slider" id="slider-${data.id}" min="${min}" max="${max}" step="${step}" value="${val}" data-widget-id="${data.id}">
        </div>
        <button class="widget-submit-btn slider-submit" data-widget-id="${data.id}">Submit</button>
      `;

    } else {
      console.warn('Unsupported widget type:', data.type);
      return;
    }

    dom.activeWidgetContainer.innerHTML = `
      <div class="dynamic-widget textbar-widget" id="widget-${data.id}" data-type="${data.type}">
        <div class="widget-title">${title}</div>
        ${contentHtml}
        <div class="widget-cancel" onclick="window.clearActiveWidget()">Cancel</div>
      </div>
    `;
    
    dom.inputWrapper.classList.add('hidden');
    dom.activeWidgetContainer.classList.remove('hidden');
    
    if (data.type === 'choice' && data.allow_custom) {
      const inputEl = dom.activeWidgetContainer.querySelector('.widget-custom-input');
      if (inputEl) inputEl.focus();
    }
  }

  // Expose to window so onclick works
  window.clearActiveWidget = clearActiveWidget;

  // ── DOM refs ──
  const $ = (sel) => document.querySelector(sel);
  const dom = {
    activeWidgetContainer: document.getElementById('active-widget-container'),
    inputWrapper: document.querySelector('.input-wrapper'),
    app: $('#app'),
    sidebar: $('#sidebar'),
    sessionList: $('#session-list'),
    newChatBtn: $('#new-chat-btn'),
    chatTitle: $('#chat-title'),
    chatSubtitle: $('#chat-subtitle'),
    messagesContainer: $('#messages-container'),
    messages: $('#messages'),
    welcome: $('#welcome-screen'),
    input: $('#message-input'),
    attachmentChips: $('#attachment-chips'), // Added
    sendBtn: $('#send-btn'),
    attachBtn: $('#attach-btn'),
    fileUpload: $('#file-upload'), // Added explicitly if not there
    attachMenu: $('#attach-menu'), // Added explicitly if not there
    modeToggle: $('#mode-toggle'),
    statusBar: $('#status-bar'),
    statusText: $('#status-text'),
    refreshBtn: $('#refresh-btn'),
    settingsBtn: $('#settings-btn'),
    settingsModal: $('#settings-modal'),
    closeSettings: $('#close-settings'),
    settingUserId: $('#setting-user-id'),
    settingMode: $('#setting-mode'),
    settingFontSize: $('#setting-font-size'),
    settingsNavItems: document.querySelectorAll('.settings-nav-item'),
    settingsPanels: document.querySelectorAll('.settings-panel'),
    settingsCategoryTitle: $('#settings-category-title'),
    btnConsolidate: $('#btn-consolidate'),
    btnWipeMemory: $('#btn-wipe-memory'),
    statL1: $('#stat-l1'),
    statL2: $('#stat-l2'),
    statL3: $('#stat-l3'),
    statL4: $('#stat-l4'),
    themeBtns: document.querySelectorAll('.theme-btn'),
    workersToggleBtn: $('#workers-toggle-btn'),
    workersPanel: $('#workers-panel'),
    closeWorkers: $('#close-workers'),
    tabWorkers: $('#tab-workers'),
    tabSwarms: $('#tab-swarms'),
    workersTabContent: $('#workers-tab-content'),
    swarmsTabContent: $('#swarms-tab-content'),
    workersListView: $('#workers-list-view'),
    workersList: $('#workers-list'),
    workerChatView: $('#worker-chat-view'),
    backToWorkers: $('#back-to-workers'),
    workerChatTitle: $('#worker-chat-title'),
    workerChatMessages: $('#worker-chat-messages'),
    swarmsListView: $('#swarms-list-view'),
    swarmsList: $('#swarms-list'),
    swarmChatView: $('#swarm-chat-view'),
    backToSwarms: $('#back-to-swarms'),
    swarmChatTitle: $('#swarm-chat-title'),
    swarmGraphContainer: $('#swarm-graph-container'),
    swarmChatMessages: $('#swarm-chat-messages'),
    voiceBtn: $('#voice-btn'),
    recordingIndicator: $('#recording-indicator'),
    fileUpload: $('#file-upload'),
    cancelVoiceBtn: $('#cancel-voice-btn'),
    recordingTime: $('.recording-time'),
    attachMenu: $('#attach-menu'),
    stopBtn: $('#stop-btn'),
    toggleSettingsSidebar: $('#toggle-settings-sidebar'),
    settingsSidebar: $('.settings-sidebar'),
    sidebarToggleBtn: $('#sidebar-toggle-btn'),
    widgetsPanel: $('#widgets-panel'),
    closeWidgets: $('#close-widgets'),
    stopwatchDisplay: $('#desktop-stopwatch-display'),
    stopwatchToggle: $('#desktop-stopwatch-toggle'),
    stopwatchLap: $('#desktop-stopwatch-lap'),
    stopwatchReset: $('#desktop-stopwatch-reset'),
    stopwatchLaps: $('#desktop-stopwatch-laps'),
    timerWidget: $('#desktop-timer'),
    timerDisplay: $('#desktop-timer-display'),
    timerToggle: $('#desktop-timer-toggle'),
    timerReset: $('#desktop-timer-reset'),
    timerAdd10s: $('#desktop-timer-add-10s'),
    timerAdd1m: $('#desktop-timer-add-1m'),
    timerAdd5m: $('#desktop-timer-add-5m'),
    timerInput: $('#desktop-timer-input'),
  };

  // ── Init ──
  function renderAttachmentChips() {
    if (!dom.attachmentChips) return;
    dom.attachmentChips.innerHTML = '';
    if (state.selectedFiles.length === 0) {
      dom.attachmentChips.classList.add('hidden');
      return;
    }
    dom.attachmentChips.classList.remove('hidden');
    state.selectedFiles.forEach((file, index) => {
      const chip = document.createElement('div');
      chip.className = 'attachment-chip';
      chip.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
        <span class="chip-name">${file.name}</span>
        <button class="remove-chip" data-index="${index}">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      `;
      chip.querySelector('.remove-chip').addEventListener('click', (e) => {
        e.stopPropagation();
        state.selectedFiles.splice(index, 1);
        renderAttachmentChips();
        if (state.selectedFiles.length === 0 && !dom.input.value.trim()) {
          dom.sendBtn.disabled = true;
        }
      });
      dom.attachmentChips.appendChild(chip);
    });
    
    if (typeof Motion !== 'undefined') {
      const chips = dom.attachmentChips.querySelectorAll('.attachment-chip');
      Motion.animate(chips, { opacity: [0, 1], scale: [0.9, 1] }, { duration: 0.2, delay: Motion.stagger(0.05) });
    }
  }

  async function init() {
    try {
      state.bridgePort = await window.yoloAPI.getBridgePort();
    } catch {}
    loadPrefs();
    applyTheme();
    applySidebarState();
    bindEvents();
    pollHealth(); // Detects user_id from backend, then hydrates session
    pollWorkers(); // Start background worker polling for notifications
    fetchSessions(); // Load session history
  }

  async function fetchSessions() {
    try {
      const data = await window.yoloAPI.getSessions();
      if (data && data.sessions) {
        state.sessions = data.sessions;
        renderSessions();
      }
    } catch {}
  }

  function renderSessions() {
    if (!dom.sessionList) return;
    dom.sessionList.innerHTML = '';
    
    // If no sessions, show a placeholder
    if (state.sessions.length === 0) {
      dom.sessionList.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:12px;">No history yet</div>';
      return;
    }

    state.sessions.forEach(s => {
      const item = document.createElement('div');
      item.className = `session-item ${s.user_id === state.userId ? 'active' : ''}`;
      item.dataset.id = s.user_id;
      
      const lastActive = new Date(s.last_active);
      const timeStr = lastActive.toLocaleDateString() === new Date().toLocaleDateString()
        ? formatTime(lastActive)
        : lastActive.toLocaleDateString();

      item.innerHTML = `
        <div class="session-name">Session ${s.user_id}</div>
        <div class="session-meta">${timeStr}</div>
      `;
      
      item.addEventListener('click', () => {
        if (state.userId === s.user_id) return;
        state.userId = s.user_id;
        savePrefs();
        hydrateFromSession();
      });

      // Hover animation
      item.addEventListener('mouseenter', () => {
        if (typeof Motion !== 'undefined') Motion.animate(item, { x: 4, backgroundColor: 'var(--bg-surface-hover)' }, { duration: 0.2 });
      });
      item.addEventListener('mouseleave', () => {
        if (typeof Motion !== 'undefined' && !item.classList.contains('active')) {
          Motion.animate(item, { x: 0, backgroundColor: 'transparent' }, { duration: 0.2 });
        } else if (typeof Motion !== 'undefined') {
          Motion.animate(item, { x: 0 }, { duration: 0.2 });
        }
      });
      
      dom.sessionList.appendChild(item);
    });

    if (typeof Motion !== 'undefined') {
      const items = dom.sessionList.querySelectorAll('.session-item');
      Motion.animate(items, { opacity: [0, 1], x: [-10, 0] }, { duration: 0.4, delay: Motion.stagger(0.05) });
    }
  }

  function loadPrefs() {
    try {
      const saved = localStorage.getItem('yolo-desktop-prefs');
      if (saved) {
        const p = JSON.parse(saved);
        state.userId = p.userId || 1;
        state.theme = p.theme || 'dark';
        state.sidebarCollapsed = p.sidebarCollapsed || false;
      }
    } catch {}
  }

  function savePrefs() {
    try {
      localStorage.setItem('yolo-desktop-prefs', JSON.stringify({
        userId: state.userId,
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
      }));
    } catch {}
  }

  function applySidebarState() {
    if (!dom.sidebar || !dom.sidebarToggleBtn) return;
    if (state.sidebarCollapsed) {
      dom.sidebar.classList.add('collapsed');
      dom.sidebarToggleBtn.classList.add('active');
    } else {
      dom.sidebar.classList.remove('collapsed');
      dom.sidebarToggleBtn.classList.remove('active');
    }
  }

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    if (dom.themeBtns) {
      dom.themeBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === state.theme);
      });
    }
  }

  // ── Hydrate session from backend (shared with Telegram/CLI) ──
  async function hydrateFromSession() {
    try {
      const data = await window.yoloAPI.getSession({ userId: state.userId });
      if (data && data.messages) {
        state.yoloMode = data.yolo_mode || false;
        state.thinkMode = data.think_mode || false;
        state.messages = data.messages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: null,
        }));

        // Sync mode badge
        const label = dom.modeToggle.querySelector('.mode-label');
        label.textContent = state.yoloMode ? 'YOLO' : 'Safe';
        label.classList.toggle('yolo', state.yoloMode);
        dom.modeToggle.setAttribute('aria-pressed', state.yoloMode ? 'true' : 'false');

        // Update subtitle (Session title removed as per request)
        updateStats(data.history_length || 0, data.total_tokens || 0, data.llm_call_count || 0);
        
        // Refresh sidebar to update active item
        fetchSessions();
      }
    } catch {}
    renderMessages(true);
  }

  // ── Rendering ──
  function renderMessages(shouldAnimate = false, filterQuery = '') {
    dom.messages.innerHTML = '';

    const query = (filterQuery || '').toLowerCase().trim();
    const filteredMessages = query 
      ? state.messages.filter(m => m.content.toLowerCase().includes(query))
      : state.messages;

    if (state.messages.length === 0) {
      dom.messages.appendChild(createWelcomeScreen());
      return;
    }

    if (query && filteredMessages.length === 0) {
      const div = document.createElement('div');
      div.style.padding = '40px';
      div.style.textAlign = 'center';
      div.style.color = 'var(--text-muted)';
      div.textContent = `No messages matching "${filterQuery}"`;
      dom.messages.appendChild(div);
      return;
    }

    filteredMessages.forEach(msg => {
      dom.messages.appendChild(createMessageEl(msg));
    });
    scrollToBottom();

    // Apply stagger animation to message elements ONLY if requested (e.g. on start or initial load)
    const elements = dom.messages.querySelectorAll('.message');
    if (shouldAnimate && elements.length > 0 && typeof Motion !== 'undefined') {
      Motion.animate(
        elements,
        { opacity: [0, 1], y: [20, 0] },
        { delay: Motion.stagger(0.05), duration: 0.4, easing: [0.2, 0.8, 0.2, 1] }
      );
    }
  }

  function createWelcomeScreen() {
    const div = document.createElement('div');
    div.className = 'welcome-screen';
    div.innerHTML = `
      <div class="welcome-logo-wrapper">
        <span style="font-family: 'Playfair Display', serif; font-style: italic; font-size: 32px; font-weight: 700; color: var(--text-primary);">Y</span>
      </div>
      <h1 class="welcome-title">Welcome to <span class="yolo-logo-text">YOL<span class="o-red">O</span></span></h1>
      <p class="welcome-desc">Your autonomous AI agent. Ask anything — code, research, system control, and more.</p>
      
      <div class="welcome-cards">
        <div class="welcome-card" data-prompt="Generate a Next.js landing page with premium glassmorphism CSS styling.">
          <div class="card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/><line x1="14" y1="2" x2="10" y2="22"/></svg>
          </div>
          <h3>Write Code</h3>
          <p>Generate a Next.js landing page with glassmorphism CSS styling.</p>
        </div>
        <div class="welcome-card" data-prompt="Analyze and compare the latest browser automation libraries. What are the trade-offs?">
          <div class="card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </div>
          <h3>Deep Research</h3>
          <p>Analyze and compare the latest browser automation libraries.</p>
        </div>
        <div class="welcome-card" data-prompt="Check the CPU load, running tasks, and active network connections.">
          <div class="card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
          </div>
          <h3>System Control</h3>
          <p>Check the CPU load, running tasks, and active network connections.</p>
        </div>
        <div class="welcome-card" data-prompt="Brainstorm some innovative startup ideas combining AI and developer productivity.">
          <div class="card-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </div>
          <h3>General Chat</h3>
          <p>Brainstorm startup ideas or chat about anything on your mind.</p>
        </div>
      </div>
      
      <p style="font-size: 11px; color: var(--text-muted); margin-top: 24px; margin-bottom: 0 !important; opacity: 0.6; text-align: center;">
        Session is shared with Telegram &amp; CLI. Type <kbd style="background: var(--bg-secondary); border: 1px solid var(--border); padding: 1px 4px; border-radius: 3px;">/</kbd> for commands.
      </p>
    `;
    return div;
  }

  function appendMessageActions(wrapper, msgObj) {
    const actions = document.createElement('div');
    actions.className = 'message-actions';
    const copyBtn = document.createElement('button');
    copyBtn.className = 'msg-action-btn copy-btn';
    copyBtn.title = 'Copy to clipboard';
    copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`;
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(msgObj.content);
      const originalIcon = copyBtn.innerHTML;
      copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
      setTimeout(() => { copyBtn.innerHTML = originalIcon; }, 2000);
    });
    actions.appendChild(copyBtn);
    wrapper.insertBefore(actions, wrapper.querySelector('.msg-timestamp') || null);
  }

  function createMessageEl(msg) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${msg.role}`;

    if (msg.role === 'assistant') {
      wrapper.innerHTML = `<div class="msg-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.28 1.28L3 12l5.8 1.9a2 2 0 0 1 1.28 1.28L12 21l1.9-5.8a2 2 0 0 1 1.28-1.28L21 12l-5.8-1.9a2 2 0 0 1-1.28-1.28Z"/></svg></div>`;
    }

    const content = document.createElement('div');
    content.className = 'msg-content';

    if (msg.role === 'assistant') {
      content.innerHTML = renderMarkdown(msg.content);
      content.querySelectorAll('pre code').forEach(block => {
        try { hljs.highlightElement(block); } catch {}
      });
      // Initialize inline widgets
      initializeInlineWidgets(content);
    } else {
      const voiceMatch = msg.content && msg.content.match(/__VOICE_NOTE__:([^\n]+)/);
      if (voiceMatch) {
        const audioPath = voiceMatch[1].trim();
        // audioPath is something like "artifacts/uploads/2026...webm"
        // The API bridge serves this at /uploads/filename
        const fileName = audioPath.split('/').pop();
        const audioUrl = `http://127.0.0.1:${state.bridgePort}/uploads/${fileName}`;

        content.classList.add('voice-note-bubble');
        content.innerHTML = `
          <div class="voice-note-card">
            <div class="voice-play-icon" onclick="this.closest('.voice-note-bubble').querySelector('audio').play()">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </div>
            <div class="voice-waveform">
              ${Array(12).fill(0).map(() => `<span class="v-bar" style="height: ${Math.floor(Math.random() * 15) + 5}px;"></span>`).join('')}
            </div>
            <span class="voice-duration">Play Voice</span>
            <audio src="${audioUrl}" style="display:none;"></audio>
          </div>
          <div class="voice-transcript">${renderMarkdown(msg.content.split('\n\nTranscript:')[1] || '')}</div>
        `;
      } else if (msg.content && msg.content.includes('🎤 [Voice Message attached]')) {
        // Fallback for old messages
        content.classList.add('voice-note-bubble');
        content.innerHTML = `
          <div class="voice-note-card">
            <div class="voice-play-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </div>
            <div class="voice-waveform">
              <span class="v-bar" style="height: 12px;"></span>
              <span class="v-bar" style="height: 18px;"></span>
              <span class="v-bar" style="height: 14px;"></span>
              <span class="v-bar" style="height: 22px;"></span>
              <span class="v-bar" style="height: 16px;"></span>
              <span class="v-bar" style="height: 10px;"></span>
              <span class="v-bar" style="height: 18px;"></span>
              <span class="v-bar" style="height: 14px;"></span>
              <span class="v-bar" style="height: 10px;"></span>
            </div>
            <span class="voice-duration">Voice Note</span>
          </div>
        `;
      } else {
        content.textContent = msg.content;
      }
    }

    wrapper.appendChild(content);

    if (msg.role === 'assistant') {
      appendMessageActions(wrapper, msg);
    }

    if (msg.timestamp) {
      const ts = document.createElement('div');
      ts.className = 'msg-timestamp';
      ts.textContent = formatTime(msg.timestamp);
      wrapper.appendChild(ts);
    }

    return wrapper;
  }

  function showTypingIndicator() {
    removeTypingIndicator();
    const el = document.createElement('div');
    el.className = 'typing-indicator';
    el.id = 'typing';
    el.innerHTML = `
      <div class="msg-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.28 1.28L3 12l5.8 1.9a2 2 0 0 1 1.28 1.28L12 21l1.9-5.8a2 2 0 0 1 1.28-1.28L21 12l-5.8-1.9a2 2 0 0 1-1.28-1.28Z"/></svg></div>
      <div class="typing-dots"><span></span><span></span><span></span></div>
    `;
    if (typeof Motion !== 'undefined') {
      el.style.opacity = '0';
      el.style.transform = 'translateY(10px)';
    }
    dom.messages.appendChild(el);
    if (typeof Motion !== 'undefined') {
      Motion.animate(el, { opacity: 1, y: 0 }, { duration: 0.3, easing: [0.2, 0.8, 0.2, 1] });
    }
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const el = document.getElementById('typing');
    if (el) el.remove();
  }

  // ── Slash commands registry ──
  const svgIcon = (path) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;

  const SLASH_COMMANDS = [
    { cmd: 'start',       desc: 'Reset the current session',       icon: svgIcon('<polyline points="1 4 1 10 7 10"></polyline><polyline points="23 20 23 14 17 14"></polyline><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>') },
    { cmd: 'status',      desc: 'Show session status report',      icon: svgIcon('<line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line>') },
    { cmd: 'mode',        desc: 'Toggle Safe/YOLO mode',           icon: svgIcon('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>'), hasArgs: true, hint: 'yolo | safe' },
    { cmd: 'think',       desc: 'Toggle think mode',               icon: svgIcon('<path d="M12 2a8 8 0 0 0-8 8c0 5.4 3.6 7.2 3.6 10.8A1.2 1.2 0 0 0 8.8 22h6.4a1.2 1.2 0 0 0 1.2-1.2c0-3.6 3.6-5.4 3.6-10.8a8 8 0 0 0-8-8z"></path><line x1="9" y1="18" x2="15" y2="18"></line>'), hasArgs: true, hint: 'on | off | auto' },
    { cmd: 'compact',     desc: 'Compact conversation history',    icon: svgIcon('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line>') },
    { cmd: 'tools',       desc: 'List all available tools',        icon: svgIcon('<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>') },
    { cmd: 'experiences', desc: 'Show technical lessons learned',  icon: svgIcon('<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>') },
    { cmd: 'schedules',   desc: 'Show scheduled tasks',            icon: svgIcon('<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line>') },
    { cmd: 'memories',    desc: 'Show stored user memories',       icon: svgIcon('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline>') },
    { cmd: 'facts',       desc: 'Show auto-injected basic facts',  icon: svgIcon('<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle>') },
    { cmd: 'forget',      desc: 'Wipe all stored memories',        icon: svgIcon('<polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>') },
    { cmd: 'cancel',      desc: 'Cancel pending confirmations',    icon: svgIcon('<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>') },
  ];

  function parseSlashCommand(text) {
    if (!text.startsWith('/')) return null;
    const parts = text.trim().split(/\s+/);
    const cmd = parts[0].slice(1).toLowerCase();
    const args = parts.slice(1);
    const match = SLASH_COMMANDS.find(c => c.cmd === cmd);
    if (!match) return null;
    return { command: cmd, args };
  }

  // ── Command palette ──
  function createCommandPalette() {
    const palette = document.createElement('div');
    palette.id = 'command-palette';
    palette.className = 'command-palette hidden';
    document.querySelector('.input-wrapper').prepend(palette);
    return palette;
  }

  const commandPalette = createCommandPalette();

  function showCommandPalette(filter) {
    const query = (filter || '').toLowerCase();
    const matches = SLASH_COMMANDS.filter(c =>
      c.cmd.includes(query) || c.desc.toLowerCase().includes(query)
    );
    if (matches.length === 0) { 
      hideCommandPalette();
      return; 
    }
    
    state.activePaletteIndex = 0; // Reset to top when showing/filtering
    
    commandPalette.innerHTML = matches.map((c, i) => `
      <div class="cmd-option ${i === state.activePaletteIndex ? 'active' : ''}" data-cmd="${c.cmd}" data-has-args="${!!c.hasArgs}">
        <span class="cmd-icon">${c.icon}</span>
        <div class="cmd-info">
          <span class="cmd-name">/${c.cmd}${c.hint ? ' <span class="cmd-hint">' + c.hint + '</span>' : ''}</span>
          <span class="cmd-desc">${c.desc}</span>
        </div>
      </div>
    `).join('');
    commandPalette.classList.remove('hidden');

    commandPalette.querySelectorAll('.cmd-option').forEach((opt, index) => {
      opt.addEventListener('click', () => {
        selectPaletteOption(index);
      });
    });
  }

  function updatePaletteSelection() {
    const options = commandPalette.querySelectorAll('.cmd-option');
    options.forEach((opt, i) => {
      opt.classList.toggle('active', i === state.activePaletteIndex);
    });
    // Ensure selected option is visible
    if (options[state.activePaletteIndex]) {
      options[state.activePaletteIndex].scrollIntoView({ block: 'nearest' });
    }
  }

  function selectPaletteOption(index) {
    const options = commandPalette.querySelectorAll('.cmd-option');
    const opt = options[index];
    if (!opt) return;
    
    const cmd = opt.dataset.cmd;
    if (opt.dataset.hasArgs === 'true') {
      dom.input.value = `/${cmd} `;
      dom.input.focus();
    } else {
      dom.input.value = `/${cmd}`;
      sendMessage(`/${cmd}`);
    }
    hideCommandPalette();
  }

  function hideCommandPalette() { 
    commandPalette.classList.add('hidden'); 
    state.activePaletteIndex = -1;
  }

  // ── Send message (with slash-command support + streaming) ──
  async function sendMessage(text) {
    if (!text || !text.trim() || state.isLoading) return;
    text = text.trim();

    const slashCmd = parseSlashCommand(text);

    // Add user message to local state
    const attachedText = state.selectedFiles.length > 0 
      ? `\n\n[Attached: ${state.selectedFiles.map(f => f.name).join(', ')}]`
      : '';
    const fullText = text + attachedText;
    const attachments = state.selectedFiles.map(f => ({ name: f.name, type: f.type, content: f.content }));

    const userMsg = { role: 'user', content: fullText, timestamp: Date.now() };
    state.messages.push(userMsg);

    if (dom.messages.querySelector('.welcome-screen')) {
      dom.messages.innerHTML = '';
    }
    const userEl = createMessageEl(userMsg);
    if (typeof Motion !== 'undefined') {
      userEl.style.opacity = '0';
      userEl.style.transform = 'translateY(10px)';
    }
    dom.messages.appendChild(userEl);
    if (typeof Motion !== 'undefined') {
      Motion.animate(userEl, { opacity: 1, y: 0 }, { duration: 0.3, easing: [0.2, 0.8, 0.2, 1] });
    }
    scrollToBottom();

    dom.input.value = '';
    dom.input.style.height = ''; // Let CSS take over for base height
    dom.sendBtn.disabled = true;
    hideCommandPalette();

    state.selectedFiles = [];
    renderAttachmentChips();

    state.isLoading = true;
    dom.stopBtn.classList.remove('hidden');
    dom.voiceBtn.classList.add('hidden');

    try {
      let result;
      if (slashCmd) {
        // Slash commands use the synchronous path
        showTypingIndicator();
        result = await window.yoloAPI.runCommand({
          command: slashCmd.command,
          args: slashCmd.args,
          userId: state.userId,
          attachments: attachments,
        });

        if (result && result.status === 'needs_confirmation') {
          const confirmedIdx = await window.yoloAPI.showConfirmationDialog(result);
          const confirmed = (confirmedIdx === 0);
          result = await window.yoloAPI.confirmAction({ confirmed, userId: state.userId });
        }

        // Sync UI state for mode/think/start
        if (slashCmd.command === 'mode' && slashCmd.args.length) {
          const m = slashCmd.args[0].toLowerCase();
          if (m === 'yolo') state.yoloMode = true;
          else if (m === 'safe') state.yoloMode = false;
          syncModeBadge();
        }
        if (slashCmd.command === 'start') {
          state.messages = [userMsg];
          removeTypingIndicator();
          renderMessages(true);
          state.isLoading = false;
          dom.stopBtn.classList.add('hidden');
          dom.voiceBtn.classList.remove('hidden');
          return;
        }
        removeTypingIndicator();

        const response = result.response || result.error || 'No response received.';
        const assistantMsg = { role: 'assistant', content: response, timestamp: Date.now() };
        state.messages.push(assistantMsg);
        const el = createMessageEl(assistantMsg);
        if (typeof Motion !== 'undefined') {
          el.style.opacity = '0';
          el.style.transform = 'translateY(10px)';
        }
        dom.messages.appendChild(el);
        if (typeof Motion !== 'undefined') {
          Motion.animate(el, { opacity: 1, y: 0 }, { duration: 0.3, easing: [0.2, 0.8, 0.2, 1] });
        }
      } else {
        // ── Streaming path ──
        // Create the assistant message bubble immediately (empty)
        const streamMsg = { role: 'assistant', content: '', timestamp: Date.now() };
        state.messages.push(streamMsg);

        const streamWrapper = document.createElement('div');
        streamWrapper.className = 'message assistant';
        streamWrapper.innerHTML = `<div class="msg-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.28 1.28L3 12l5.8 1.9a2 2 0 0 1 1.28 1.28L12 21l1.9-5.8a2 2 0 0 1 1.28-1.28L21 12l-5.8-1.9a2 2 0 0 1-1.28-1.28Z"/></svg></div>`;

        const streamContent = document.createElement('div');
        streamContent.className = 'msg-content';
        streamContent.innerHTML = '<span class="stream-cursor"></span>';
        streamWrapper.appendChild(streamContent);

        // Status indicator (shows "Executing tools: ..." etc.)
        const statusEl = document.createElement('div');
        statusEl.className = 'msg-status-indicator';
        statusEl.style.display = 'none';
        streamWrapper.appendChild(statusEl);

        dom.messages.appendChild(streamWrapper);

        if (typeof Motion !== 'undefined') {
          streamWrapper.style.opacity = '0';
          streamWrapper.style.transform = 'translateY(10px)';
          Motion.animate(streamWrapper, { opacity: 1, y: 0 }, { duration: 0.3, easing: [0.2, 0.8, 0.2, 1] });
        }
        scrollToBottom();

        let streamedContent = '';
        let streamDone = false;

        // Listen for streaming events from main process
        const onStreamEvent = (event) => {
          const { type, data } = event;

          if (type === 'stream') {
            // data is the full accumulated content so far
            streamedContent = data;
            streamContent.innerHTML = renderMarkdown(streamedContent) + '<span class="stream-cursor"></span>';
            streamContent.querySelectorAll('pre code').forEach(block => {
              try { hljs.highlightElement(block); } catch {}
            });
            statusEl.style.display = 'none';
            scrollToBottom();
          } else if (type === 'status') {
            statusEl.textContent = data;
            statusEl.style.display = 'block';
            scrollToBottom();
          } else if (type === 'tool_call') {
            const toolGroup = document.createElement('div');
            toolGroup.className = 'msg-tool-group';
            toolGroup.id = `tool-${data.call_id || Math.random().toString(36).substr(2, 9)}`;
            
            const toolDetails = document.createElement('details');
            toolDetails.open = true; // Open by default while running
            toolDetails.className = 'tool-log-details';
            
            const summary = document.createElement('summary');
            summary.innerHTML = `<span class="tool-status-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg></span> Running <code>${escapeHtml(data.name)}</code>...`;
            
            const logContent = document.createElement('div');
            logContent.className = 'tool-log-content';
            logContent.innerHTML = `<div class="tool-call-info"><strong>Arguments:</strong> <code>${escapeHtml(JSON.stringify(data.args || {}))}</code></div><div class="tool-result-placeholder">Waiting for result...</div>`;
            
            toolDetails.appendChild(summary);
            toolDetails.appendChild(logContent);
            toolGroup.appendChild(toolDetails);
            streamWrapper.insertBefore(toolGroup, statusEl);
            scrollToBottom();
          } else if (type === 'tool_result') {
            // Find the matching tool group using call_id if available
            let toolGroup = null;
            if (data.call_id) {
              toolGroup = document.getElementById(`tool-${data.call_id}`);
            }
            // Fallback for missing call_id or old events
            if (!toolGroup) {
              toolGroup = Array.from(streamWrapper.querySelectorAll('.msg-tool-group')).find(
                g => g.querySelector('summary').textContent.includes(data.name) && g.querySelector('.tool-result-placeholder')
              ) || streamWrapper.querySelector('.msg-tool-group:last-of-type');
            }
            if (toolGroup) {
              const details = toolGroup.querySelector('details');
              const summary = details.querySelector('summary');
              const placeholder = details.querySelector('.tool-result-placeholder');
              
              summary.innerHTML = `<span class="tool-status-icon success"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span> Executed <code>${escapeHtml(data.name)}</code>`;
              
              const resultText = typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2);
              placeholder.className = 'tool-result-content';
              
              let highlightedResult;
              if (typeof hljs !== 'undefined') {
                try {
                  highlightedResult = hljs.highlightAuto(resultText).value;
                } catch (e) {
                  highlightedResult = escapeHtml(resultText);
                }
              } else {
                highlightedResult = escapeHtml(resultText);
              }
              
              placeholder.innerHTML = `<strong>Result:</strong><pre><code class="hljs">${highlightedResult}</code></pre>`;
            }
            scrollToBottom();
          } else if (type === 'artifact') {
            const artifactWrapper = document.createElement('div');
            artifactWrapper.className = 'artifact-card';
            
            // For file:// URLs, we might need to handle them differently depending on Electron security
            // If served via /artifacts/ prefix, it works normally.
            if (data.type === 'image') {
              const fullImgUrl = getFullUrl(data.url);
              artifactWrapper.innerHTML = `
                <div class="artifact-title">Generated Image: ${escapeHtml(data.name)}</div>
                <img src="${fullImgUrl}" class="artifact-image" alt="${escapeHtml(data.name)}" style="max-width: 100%; border-radius: 8px; margin-top: 8px; cursor: pointer;" onclick="openLink('${data.url}')" />
                <div class="artifact-actions" style="margin-top: 8px;">
                  <button class="primary-btn sm" onclick="openLink('${data.url}')">View Full Size</button>
                </div>
              `;
            } else {
              artifactWrapper.innerHTML = `
                <div class="artifact-title">Generated File: ${escapeHtml(data.name)}</div>
                <div class="artifact-file-info" style="display: flex; align-items: center; gap: 10px; padding: 12px; background: rgba(0,0,0,0.05); border-radius: 8px; margin-top: 8px;">
                   <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14.5 2 14.5 7.5 20 7.5"></polyline></svg>
                   <span style="font-family: monospace; font-size: 0.9em;">${escapeHtml(data.name)}</span>
                </div>
                <div class="artifact-actions" style="margin-top: 8px;">
                  <button class="primary-btn sm" onclick="openLink('${data.url}')">Open File</button>
                </div>
              `;
            }
            streamWrapper.insertBefore(artifactWrapper, statusEl);
            scrollToBottom();
          } else if (type === 'needs_confirmation') {
            // Phase 2: Native HITL UI
            streamDone = true;
            (async () => {
              const confirmedIdx = await window.yoloAPI.showConfirmationDialog(data);
              const confirmed = (confirmedIdx === 0);
              const finalResult = await window.yoloAPI.confirmAction({ confirmed, userId: state.userId });
              
              const finalResponse = finalResult.response || finalResult.error || 'No response received.';
              streamContent.innerHTML = renderMarkdown(finalResponse);
              streamContent.querySelectorAll('pre code').forEach(block => {
                try { hljs.highlightElement(block); } catch {}
              });
              statusEl.style.display = 'none';
              streamMsg.content = finalResponse;
              appendMessageActions(streamWrapper, streamMsg);
              refreshSessionMeta();
              scrollToBottom();
            })();
          } else if (type === 'done') {
            // Final complete response
            streamedContent = data;
            streamContent.innerHTML = renderMarkdown(streamedContent);
            streamContent.querySelectorAll('pre code').forEach(block => {
              try { hljs.highlightElement(block); } catch {}
            });
            statusEl.style.display = 'none';
            streamMsg.content = streamedContent;
            appendMessageActions(streamWrapper, streamMsg);
            
            // Initialize inline widgets after stream completes
            initializeInlineWidgets(streamContent);

            // Automatically close all tool logs in this message
            streamWrapper.querySelectorAll('.tool-log-details').forEach(d => {
              d.open = false;
            });
            
            streamDone = true;
          } else if (type === 'error') {
            streamContent.innerHTML = renderMarkdown(`⚠️ Error: ${data}`);
            streamMsg.content = `⚠️ Error: ${data}`;
            streamDone = true;
          }
        };

        window.yoloAPI.onChatStreamEvent(onStreamEvent);

        // Fire the streaming request (it runs in background, events come via IPC)
        const streamPromise = window.yoloAPI.streamChat({
          message: text,
          userId: state.userId,
          attachments: attachments,
        });

        // Wait for stream to complete
        await streamPromise;

        // Safety: if we didn't get a 'done' event, wait briefly for remaining events
        if (!streamDone) {
          await new Promise(resolve => setTimeout(resolve, 500));
        }

        // Note: stream listener cleanup is now in the finally block below

        // Add timestamp
        const ts = document.createElement('div');
        ts.className = 'msg-timestamp';
        ts.textContent = formatTime(Date.now());
        streamWrapper.appendChild(ts);
      }

      // Refresh subtitle stats and sidebar
      refreshSessionMeta();
      fetchSessions();
      scrollToBottom();
    } catch (err) {
      removeTypingIndicator();
      const errMsg = { role: 'assistant', content: `⚠️ Connection error: ${err.message}`, timestamp: Date.now() };
      state.messages.push(errMsg);
      dom.messages.appendChild(createMessageEl(errMsg));
      scrollToBottom();
    } finally {
      // Always clean up stream listener (BUG-30 fix)
      window.yoloAPI.removeChatStreamListeners();
      state.isLoading = false;
      dom.stopBtn.classList.add('hidden');
      dom.voiceBtn.classList.remove('hidden');
    }
  }

  function syncModeBadge() {
    const label = dom.modeToggle.querySelector('.mode-label');
    label.textContent = state.yoloMode ? 'YOLO' : 'Safe';
    label.classList.toggle('yolo', state.yoloMode);
    if (dom.modeToggle) dom.modeToggle.setAttribute('aria-pressed', state.yoloMode ? 'true' : 'false');
  }

  function updateStats(historyLen, totalTokens, llmCalls) {
    if (!dom.chatSubtitle) return;
    dom.chatSubtitle.innerHTML = `
      <span class="stat-badge">${historyLen} MSGS</span>
      <span class="stat-badge">${totalTokens} TOKENS</span>
      <span class="stat-badge">${llmCalls} LLM CALLS</span>
    `;
  }

  async function refreshSessionMeta() {
    try {
      const data = await window.yoloAPI.getSession({ userId: state.userId });
      if (data) {
        updateStats(data.history_length || 0, data.total_tokens || 0, data.llm_call_count || 0);
      }
    } catch {}
  }

  // ── Events ──
  function bindEvents() {
    // Event delegation for copying code blocks
    if (dom.messages) {
      dom.messages.addEventListener('click', (e) => {
        const btn = e.target.closest('.code-copy-btn');
        if (btn) {
          const wrapper = btn.closest('.code-block-wrapper');
          if (wrapper) {
            const codeEl = wrapper.querySelector('pre code');
            if (codeEl) {
              const text = codeEl.textContent;
              navigator.clipboard.writeText(text).then(() => {
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(() => {
                  btn.textContent = originalText;
                  btn.classList.remove('copied');
                }, 2000);
              });
            }
          }
        }
      });
    }

    // Welcome cards click handler
    if (dom.messages) {
      dom.messages.addEventListener('click', (e) => {
        const card = e.target.closest('.welcome-card');
        if (card) {
          const prompt = card.getAttribute('data-prompt');
          if (prompt && dom.input) {
            dom.input.value = prompt;
            dom.input.focus();
            dom.input.dispatchEvent(new Event('input', { bubbles: true }));
          }
        }
      });
    }

    // Update the click listener:
    dom.activeWidgetContainer.addEventListener('input', (e) => {
      if (e.target.classList.contains('widget-slider')) {
        const valSpan = document.getElementById(`slider-val-${e.target.dataset.widgetId}`);
        if (valSpan) valSpan.textContent = e.target.value;
      }
    });

    dom.activeWidgetContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.widget-btn');
      const toggleBtn = e.target.closest('.widget-toggle-btn');
      const submitBtn = e.target.closest('.widget-submit-btn');
      const sendBtn = e.target.closest('.widget-custom-send-btn');
      
      const widget = e.target.closest('.dynamic-widget');
      if (!widget || widget.classList.contains('locked')) return;

      if (toggleBtn) {
        toggleBtn.classList.toggle('selected');
        return;
      }

      if (btn) {
        widget.classList.add('locked');
        btn.setAttribute('data-selected', 'true');
        const value = btn.getAttribute('data-value');
        const widgetId = btn.getAttribute('data-widget-id');
        
        state.isLoading = false;
        sendMessage(`[Widget Response: ${widgetId}] Selected: ${value}`);
        setTimeout(() => clearActiveWidget(), 300);
      } else if (submitBtn) {
        widget.classList.add('locked');
        const widgetId = submitBtn.getAttribute('data-widget-id');
        state.isLoading = false;

        if (submitBtn.classList.contains('multi-submit')) {
          const selected = Array.from(widget.querySelectorAll('.widget-toggle-btn.selected')).map(b => b.getAttribute('data-value'));
          sendMessage(`[Widget Response: ${widgetId}] Selected: ${JSON.stringify(selected)}`);
        } else if (submitBtn.classList.contains('slider-submit')) {
          const slider = widget.querySelector('.widget-slider');
          sendMessage(`[Widget Response: ${widgetId}] Value: ${slider.value}`);
        }
        
        setTimeout(() => clearActiveWidget(), 300);
      } else if (sendBtn) {
        const inputEl = widget.querySelector('.widget-custom-input');
        const value = inputEl ? inputEl.value.trim() : '';
        if (!value) return;

        widget.classList.add('locked');
        const widgetId = inputEl.getAttribute('data-widget-id');
        state.isLoading = false;
        sendMessage(`[Widget Response: ${widgetId}] Custom: ${value}`);
        setTimeout(() => clearActiveWidget(), 300);
      }
    });

    // Add keydown listener for Enter key:
    dom.activeWidgetContainer.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const inputEl = e.target.closest('.widget-custom-input');
        if (!inputEl) return;
        
        e.preventDefault();
        const value = inputEl.value.trim();
        if (!value) return;

        const widget = inputEl.closest('.dynamic-widget');
        if (!widget || widget.classList.contains('locked')) return;

        widget.classList.add('locked');
        const widgetId = inputEl.getAttribute('data-widget-id');
        
        // Force isLoading to false so the message isn't dropped if clicked immediately
        state.isLoading = false;
        
        sendMessage(`[Widget Response: ${widgetId}] Custom: ${value}`);
        
        setTimeout(() => clearActiveWidget(), 300);
      }
    });
    dom.sendBtn.addEventListener('click', () => {
      if (!dom.recordingIndicator.classList.contains('hidden')) {
        toggleRecording(false);
      } else {
        sendMessage(dom.input.value);
      }
    });
    dom.input.addEventListener('keydown', (e) => {
      const isPaletteVisible = !commandPalette.classList.contains('hidden');
      const paletteOptions = commandPalette.querySelectorAll('.cmd-option');

      if (isPaletteVisible && paletteOptions.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          state.activePaletteIndex = (state.activePaletteIndex + 1) % paletteOptions.length;
          updatePaletteSelection();
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          state.activePaletteIndex = (state.activePaletteIndex - 1 + paletteOptions.length) % paletteOptions.length;
          updatePaletteSelection();
          return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          selectPaletteOption(state.activePaletteIndex);
          return;
        }
        if (e.key === 'Escape') {
          hideCommandPalette();
          return;
        }
      }

      if (e.key === 'Enter' && !e.shiftKey) { 
        e.preventDefault(); 
        sendMessage(dom.input.value); 
      }
    });

    dom.input.addEventListener('input', () => {
      dom.sendBtn.disabled = !dom.input.value.trim() && state.selectedFiles.length === 0;
      dom.input.style.height = ''; // Reset to base to calculate true scroll height
      const newHeight = Math.min(dom.input.scrollHeight, 150);
      dom.input.style.height = newHeight + 'px';
      const val = dom.input.value;
      if (val.startsWith('/') && !val.includes('\n')) {
        showCommandPalette(val.slice(1).split(/\s/)[0]);
      } else {
        hideCommandPalette();
      }
    });

    dom.input.addEventListener('blur', () => setTimeout(hideCommandPalette, 200));

    if (dom.sidebarToggleBtn) {
      dom.sidebarToggleBtn.addEventListener('click', () => {
        state.sidebarCollapsed = !state.sidebarCollapsed;
        savePrefs();
        applySidebarState();
      });
    }

    dom.modeToggle.addEventListener('click', () => {
      const newMode = state.yoloMode ? 'safe' : 'yolo';
      sendMessage(`/mode ${newMode}`);
    });
    
    dom.refreshBtn.addEventListener('click', () => {
      window.location.reload();
    });

    dom.newChatBtn.addEventListener('click', () => {
      // Find a new unused user ID or just pick a high one
      const maxId = state.sessions.reduce((max, s) => Math.max(max, s.user_id), 0);
      state.userId = maxId + 1;
      state.messages = [];
      savePrefs();
      hydrateFromSession();
      dom.input.focus();
    });

    // File Attach
    dom.attachBtn.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const isHidden = dom.attachMenu.classList.toggle('hidden');
      const isOpen = !isHidden;
      dom.attachBtn.classList.toggle('active', isOpen);
      dom.attachBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      dom.attachMenu.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
      if (isOpen) {
        dom.attachMenu.setAttribute('role', 'menu');
        dom.attachMenu.querySelectorAll('button').forEach(btn => btn.setAttribute('role', 'menuitem'));
      }
    });

    document.querySelectorAll('.attach-menu-item').forEach(item => {
      item.addEventListener('click', () => {
        dom.input.focus(); // This will expand the bar
        dom.attachMenu.classList.add('hidden');
        dom.attachBtn.classList.remove('active');
        dom.attachBtn.setAttribute('aria-expanded', 'false');
        dom.attachMenu.setAttribute('aria-hidden', 'true');
        dom.fileUpload.click();
      });
    });

    // Close attach menu on click outside
    document.addEventListener('mousedown', (e) => {
      if (dom.attachMenu && !dom.attachMenu.classList.contains('hidden')) {
        if (!dom.attachMenu.contains(e.target) && !dom.attachBtn.contains(e.target)) {
          dom.attachMenu.classList.add('hidden');
          dom.attachBtn.classList.remove('active');
          dom.attachBtn.setAttribute('aria-expanded', 'false');
          dom.attachMenu.setAttribute('aria-hidden', 'true');
        }
      }
    });

    async function processFile(file) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (event) => {
          resolve({
            name: file.name,
            size: file.size,
            type: file.type,
            content: event.target.result
          });
        };
        
        const textExtensions = ['.txt', '.md', '.py', '.js', '.ts', '.html', '.css', '.json', '.yaml', '.yml', '.csv', '.xml'];
        const isTextFile = textExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
        
        if (isTextFile) {
          reader.readAsText(file);
        } else {
          reader.readAsDataURL(file);
        }
      });
    }

    dom.input.addEventListener('paste', async (e) => {
      const items = (e.clipboardData || e.originalEvent.clipboardData).items;
      const filesToProcess = [];
      
      for (const item of items) {
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) filesToProcess.push(file);
        }
      }
      
      if (filesToProcess.length > 0) {
        const newFiles = await Promise.all(filesToProcess.map(processFile));
        state.selectedFiles = [...state.selectedFiles, ...newFiles];
        renderAttachmentChips();
        dom.sendBtn.disabled = false;
        
        if (typeof Motion !== 'undefined') {
          Motion.animate(dom.attachmentChips, { scale: [0.95, 1], opacity: [0.8, 1] }, { duration: 0.2 });
        }
      }
    });

    // ── Drag & Drop Support ──
    window.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dom.inputWrapper.classList.add('drag-over');
    });

    window.addEventListener('dragleave', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dom.inputWrapper.classList.remove('drag-over');
    });

    window.addEventListener('drop', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      dom.inputWrapper.classList.remove('drag-over');
      
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const files = Array.from(e.dataTransfer.files);
        const newFiles = await Promise.all(files.map(processFile));
        state.selectedFiles = [...state.selectedFiles, ...newFiles];
        renderAttachmentChips();
        dom.input.focus();
        dom.sendBtn.disabled = false;
        
        if (typeof Motion !== 'undefined') {
          Motion.animate(dom.attachmentChips, { scale: [0.95, 1], opacity: [0.8, 1] }, { duration: 0.2 });
        }
      }
    });

    dom.fileUpload.addEventListener('change', async (e) => {
      if (e.target.files && e.target.files.length > 0) {
        const files = Array.from(e.target.files);
        const newFiles = await Promise.all(files.map(processFile));
        state.selectedFiles = [...state.selectedFiles, ...newFiles];
        renderAttachmentChips();
        dom.input.focus();
        dom.sendBtn.disabled = false;
      }
      e.target.value = ''; // Reset for consecutive uploads
    });
    // Voice Recording State
    let recordingTimer;
    let recordingSeconds = 0;
    let mediaRecorder = null;
    let audioChunks = [];

    function startRecordingTimer() {
      recordingSeconds = 0;
      dom.recordingTime.textContent = '0:00';
      recordingTimer = setInterval(() => {
        recordingSeconds++;
        const mins = Math.floor(recordingSeconds / 60);
        const secs = (recordingSeconds % 60).toString().padStart(2, '0');
        dom.recordingTime.textContent = `${mins}:${secs}`;
      }, 1000);
    }

    function stopRecordingTimer() {
      clearInterval(recordingTimer);
    }

    async function toggleRecording(start) {
      if (start) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          mediaRecorder = new MediaRecorder(stream);
          audioChunks = [];

          mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
              audioChunks.push(event.data);
            }
          };

          mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            
            // Convert blob to Base64
            const reader = new FileReader();
            reader.readAsDataURL(audioBlob);
            reader.onloadend = async () => {
              const base64data = reader.result.split(',')[1];
              
              // Instead of just transcribing and sending text, we send as a voice attachment
              state.selectedFiles = [{
                name: `voice_note_${Date.now()}.webm`,
                type: 'audio/webm',
                content: base64data
              }];
              sendMessage('Voice Message');
            };
            
            // Stop all tracks to release microphone
            stream.getTracks().forEach(track => track.stop());
          };

          mediaRecorder.start();
          dom.input.parentElement.classList.add('expanded');
          dom.voiceBtn.classList.add('recording');
          dom.voiceBtn.classList.add('hidden'); // Hide voice button while recording
          dom.recordingIndicator.classList.remove('hidden');
          dom.input.classList.add('hidden');
          dom.sendBtn.disabled = false; // Ensure send is clickable
          startRecordingTimer();
        } catch (err) {
          console.error("Error accessing microphone:", err);
          alert("Could not access microphone. Please check permissions.");
        }
      } else {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
          mediaRecorder.stop();
        }
        dom.input.parentElement.classList.remove('expanded');
        dom.voiceBtn.classList.remove('recording');
        dom.voiceBtn.classList.remove('hidden');
        dom.recordingIndicator.classList.add('hidden');
        dom.input.classList.remove('hidden');
        dom.sendBtn.disabled = !dom.input.value.trim(); // Revert to text logic
        stopRecordingTimer();
      }
    }

    dom.stopBtn.addEventListener('click', () => {
      window.yoloAPI.abortChatStream();
    });

    dom.voiceBtn.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const isRecording = !dom.voiceBtn.classList.contains('recording');
      toggleRecording(isRecording);
    });

    dom.cancelVoiceBtn.addEventListener('click', () => {
      toggleRecording(false);
    });

    // Settings Category Switching
    dom.settingsNavItems.forEach(item => {
      item.addEventListener('click', () => {
        const cat = item.dataset.category;
        dom.settingsNavItems.forEach(i => i.classList.toggle('active', i === item));
        dom.settingsPanels.forEach(p => p.classList.toggle('active', p.dataset.category === cat));
        dom.settingsCategoryTitle.textContent = item.querySelector('span').textContent + ' Settings';
        
        if (cat === 'memory') updateMemoryStats();
      });
    });

    // Theme Switcher Buttons
    dom.themeBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        state.theme = btn.dataset.theme;
        applyTheme();
        savePrefs();
      });
    });

    // Font Size Control
    if (dom.settingFontSize) {
      dom.settingFontSize.addEventListener('change', () => {
        const size = dom.settingFontSize.value;
        document.documentElement.style.setProperty('--font-size-chat', size + 'px');
        // Re-render messages to apply font size if needed, or just use CSS variable
      });
    }

    // Memory Actions
    async function updateMemoryStats() {
      try {
        const stats = await window.yoloAPI.runCommand({
          command: 'memories',
          args: ['--stats'],
          userId: state.userId
        });
        if (stats && stats.response) {
          // Expecting JSON-like response from the tool
          const data = JSON.parse(stats.response);
          dom.statL1.textContent = data.L1_working_memory || 0;
          dom.statL2.textContent = data.L2_episodic_memory || 0;
          dom.statL3.textContent = data.L3_semantic_memory || 0;
          dom.statL4.textContent = data.L4_pattern_memory || 0;
        }
      } catch (e) { console.error("Stats fail", e); }
    }

    if (dom.btnConsolidate) {
      dom.btnConsolidate.addEventListener('click', async () => {
        dom.btnConsolidate.disabled = true;
        dom.btnConsolidate.textContent = 'Consolidating...';
        await window.yoloAPI.runCommand({ command: 'compact_memories', args: [], userId: state.userId });
        await updateMemoryStats();
        dom.btnConsolidate.disabled = false;
        dom.btnConsolidate.textContent = 'Consolidate Now';
      });
    }

    if (dom.btnWipeMemory) {
      dom.btnWipeMemory.addEventListener('click', async () => {
        if (confirm("Are you absolutely sure? This will wipe ALL long-term memories for this user.")) {
          await window.yoloAPI.runCommand({ command: 'forget', args: [], userId: state.userId });
          await updateMemoryStats();
        }
      });
    }

    let lastFocusedEl = null;
    dom.settingsBtn.addEventListener('click', () => {
      lastFocusedEl = document.activeElement;
      dom.settingUserId.value = state.userId;
      dom.settingMode.value = state.yoloMode ? 'yolo' : 'safe';
      dom.settingsModal.classList.remove('hidden');
      dom.settingsModal.setAttribute('aria-hidden', 'false');
      updateMemoryStats();
      // Focus the dialog header for screen readers
      setTimeout(() => {
        const closeBtn = dom.closeSettings;
        if (closeBtn) closeBtn.focus();
      }, 0);
    });
    const closeSettingsModal = () => {
      dom.settingsModal.classList.add('hidden');
      dom.settingsModal.setAttribute('aria-hidden', 'true');
      if (lastFocusedEl && lastFocusedEl.focus) lastFocusedEl.focus();
    };
    dom.closeSettings.addEventListener('click', closeSettingsModal);
    
    // Workers
    dom.workersToggleBtn.addEventListener('click', () => {
      const willOpen = dom.workersPanel.classList.contains('collapsed');
      dom.workersPanel.classList.toggle('collapsed');
      dom.workersToggleBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      if (willOpen) {
        // focus first interactive element in panel
        setTimeout(() => {
          const first = dom.workersPanel.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
          if (first) first.focus();
        }, 0);
      }
    });
    dom.closeWorkers.addEventListener('click', () => {
      dom.workersPanel.classList.add('collapsed');
      dom.workersToggleBtn.setAttribute('aria-expanded', 'false');
      dom.workersToggleBtn.focus();
    });


    if (dom.toggleSettingsSidebar) {
      dom.toggleSettingsSidebar.addEventListener('click', (e) => {
        e.stopPropagation();
        dom.settingsSidebar.classList.toggle('collapsed');
      });
    }

    dom.backToWorkers.addEventListener('click', () => {
      dom.workerChatView.classList.add('hidden');
      dom.workersListView.classList.remove('hidden');
      state.activeWorkerId = null;
    });
    // Close on overlay click
    dom.settingsModal.addEventListener('click', (e) => {
      if (e.target === dom.settingsModal) closeSettingsModal();
    });

    // Escape to close + basic focus trap
    document.addEventListener('keydown', (e) => {
      if (dom.settingsModal.classList.contains('hidden')) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        closeSettingsModal();
        return;
      }
      if (e.key !== 'Tab') return;

      const focusable = dom.settingsModal.querySelectorAll('button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])');
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
    dom.settingUserId.addEventListener('change', () => {
      state.userId = parseInt(dom.settingUserId.value) || 1;
      localStorage.setItem('yolo-manual-user-id', String(state.userId));
      savePrefs();
      hydrateFromSession(); // Reload for new user
    });
    dom.settingMode.addEventListener('change', () => {
      sendMessage(`/mode ${dom.settingMode.value}`);
    });

    // LLM Provider Settings
    const btnSaveLlm = document.getElementById('save-llm-settings');
    if (btnSaveLlm) {
      btnSaveLlm.addEventListener('click', async () => {
        btnSaveLlm.textContent = 'Saving...';
        btnSaveLlm.disabled = true;
        
        const provider = document.getElementById('setting-llm-provider').value;
        const model = document.getElementById('setting-model-name').value.trim();
        const apiKey = document.getElementById('setting-api-key').value.trim();
        const baseUrl = document.getElementById('setting-base-url').value.trim();
        
        const payload = {
          "LLM_PROVIDER": provider !== 'auto' ? provider : ''
        };
        
        if (model) {
          payload["MODEL_NAME"] = model;
          if (provider === 'openai') payload["OPENAI_MODEL"] = model;
          if (provider === 'anthropic') payload["ANTHROPIC_MODEL"] = model;
          if (provider === 'openrouter') payload["OPENROUTER_MODEL"] = model;
          if (provider === 'compatible') payload["LLM_MODEL"] = model;
        }
        
        if (apiKey) {
          if (provider === 'openai') payload["OPENAI_API_KEY"] = apiKey;
          else if (provider === 'anthropic') payload["ANTHROPIC_API_KEY"] = apiKey;
          else if (provider === 'openrouter') payload["OPENROUTER_API_KEY"] = apiKey;
          else if (provider === 'compatible') payload["LLM_API_KEY"] = apiKey;
          else payload["OPENAI_API_KEY"] = apiKey; // fallback
        }
        
        if (baseUrl) {
          if (provider === 'openai') payload["OPENAI_BASE_URL"] = baseUrl;
          else if (provider === 'anthropic') payload["ANTHROPIC_BASE_URL"] = baseUrl;
          else if (provider === 'openrouter') payload["OPENROUTER_BASE_URL"] = baseUrl;
          else if (provider === 'compatible') payload["LLM_BASE_URL"] = baseUrl;
        }

        try {
          const res = await window.yoloAPI.updateEnv(payload);
          if (res.error) {
            window.yoloAPI.showNotification('Settings Error', res.error);
          } else {
            window.yoloAPI.showNotification('Settings Saved', res.message || 'LLM Provider updated successfully');
            document.getElementById('setting-api-key').value = ''; // clear key for security
          }
        } catch (e) {
          window.yoloAPI.showNotification('Settings Error', e.message);
        } finally {
          btnSaveLlm.textContent = 'Save Provider Settings';
          btnSaveLlm.disabled = false;
        }
      });
    }

    // MCP Servers Settings
    const mcpServersList = document.getElementById('mcp-servers-list');
    const btnSaveMcp = document.getElementById('save-mcp-server');
    let currentMcpServers = {};

    async function loadMcpServers() {
      if (!window.yoloAPI?.getMcpServers) return;
      try {
        const data = await window.yoloAPI.getMcpServers();
        currentMcpServers = data.mcpServers || {};
        renderMcpServers();
      } catch (e) {
        console.error("Failed to load MCP servers", e);
      }
    }

    function renderMcpServers() {
      if (!mcpServersList) return;
      mcpServersList.innerHTML = '';
      const serverNames = Object.keys(currentMcpServers);
      if (serverNames.length === 0) {
        mcpServersList.innerHTML = '<span style="color: var(--text-secondary); font-style: italic; font-size: 13px;">No MCP servers configured.</span>';
        return;
      }
      
      for (const name of serverNames) {
        const server = currentMcpServers[name];
        const el = document.createElement('div');
        el.style.display = 'flex';
        el.style.justifyContent = 'space-between';
        el.style.alignItems = 'center';
        el.style.padding = '8px 12px';
        el.style.background = 'var(--bg-tertiary)';
        el.style.borderRadius = '6px';
        
        const envStr = server.env && Object.keys(server.env).length > 0 
          ? `<br><span style="font-size: 11px; color: var(--accent-color);">Env: ${Object.keys(server.env).length} vars</span>` 
          : '';
          
        el.innerHTML = `
          <div style="display: flex; flex-direction: column; overflow: hidden; margin-right: 10px;">
            <strong style="font-size: 14px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">${name}</strong>
            <span style="font-size: 12px; color: var(--text-secondary); white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">${server.command} ${server.args ? server.args.join(' ') : ''}${envStr}</span>
          </div>
          <button class="danger-btn" data-name="${name}" style="padding: 4px 8px; font-size: 12px; flex-shrink: 0;">Remove</button>
        `;
        
        el.querySelector('button').addEventListener('click', async (e) => {
          const sName = e.target.dataset.name;
          delete currentMcpServers[sName];
          await saveMcpServers();
        });
        
        mcpServersList.appendChild(el);
      }
    }

    async function saveMcpServers() {
      if (!window.yoloAPI?.updateMcpServers) return;
      try {
        const res = await window.yoloAPI.updateMcpServers({ mcpServers: currentMcpServers });
        if (res.error) {
          window.yoloAPI.showNotification('MCP Error', res.error);
        } else {
          renderMcpServers();
          window.yoloAPI.showNotification('MCP Servers Saved', res.message || 'Updated successfully');
        }
      } catch (e) {
        window.yoloAPI.showNotification('MCP Error', e.message);
      }
    }

    if (btnSaveMcp) {
      btnSaveMcp.addEventListener('click', async () => {
        const nameInput = document.getElementById('setting-mcp-name');
        const cmdInput = document.getElementById('setting-mcp-cmd');
        const argsInput = document.getElementById('setting-mcp-args');
        const envInput = document.getElementById('setting-mcp-env');
        
        const name = nameInput.value.trim();
        const cmd = cmdInput.value.trim();
        let args = argsInput.value.trim();
        let envRaw = envInput.value.trim();
        
        if (!name || !cmd) {
          window.yoloAPI.showNotification('Validation Error', 'Server name and command are required');
          return;
        }
        
        // Parse ENV
        let envObj = {};
        if (envRaw) {
          const parts = envRaw.split(',');
          for (const p of parts) {
            const [k, v] = p.split('=');
            if (k && v) envObj[k.trim()] = v.trim();
          }
        }
        
        btnSaveMcp.textContent = 'Adding...';
        btnSaveMcp.disabled = true;
        
        currentMcpServers[name] = {
          command: cmd,
          args: args ? args.split(',').map(s => s.trim().replace(/^["'](.*)["']$/, '$1')) : [],
          env: envObj
        };
        
        await saveMcpServers();
        
        nameInput.value = '';
        cmdInput.value = '';
        argsInput.value = '';
        if (envInput) envInput.value = '';
        btnSaveMcp.textContent = 'Add Server';
        btnSaveMcp.disabled = false;
      });
    }

    // Call loadMcpServers to populate initially
    loadMcpServers();

    // Bridge status
    if (window.yoloAPI?.onBridgeStatus) {
      window.yoloAPI.onBridgeStatus((status) => {
        updateStatus(status === 'connected' ? 'connected' : 'disconnected');
        if (status === 'connected') hydrateFromSession();
      });
    }
  }

  // ── Health polling + auto-detect user ID ──
  async function pollHealth() {
    const check = async () => {
      try {
        const res = await window.yoloAPI.healthCheck();
        if (res.status === 'ok') {
          updateStatus('connected');
          // Auto-detect user ID from backend on first connect
          if (res.default_user_id && !localStorage.getItem('yolo-manual-user-id')) {
            state.userId = res.default_user_id;
          }
        } else {
          updateStatus('disconnected');
        }
      } catch { updateStatus('disconnected'); }
    };
    await check();
    // Hydrate AFTER we know the correct user_id
    await hydrateFromSession();
    setInterval(check, 10000);
  }

  function updateStatus(status) {
    dom.statusBar.className = `status-bar status-${status}`;
    const labels = {
      connected: 'Connected — session shared with Telegram & CLI',
      connecting: 'Connecting to Yolo agent...',
      disconnected: 'Starting engine...',
    };
    dom.statusText.textContent = labels[status] || labels.connecting;
    if (status === 'connected') setTimeout(() => dom.statusBar.classList.add('hidden'), 3000);
    else dom.statusBar.classList.remove('hidden');
  }

  // ── Utilities ──
  function renderMarkdown(text) {
    if (!text) return '';
    try {
      if (typeof marked !== 'undefined') {
        const mathBlocks = [];
        const mathInline = [];

        // 1. Protect block math $$...$$ and \[...\]
        let processedText = text.replace(/\$\$([\s\S]+?)\$\$/g, (match, formula) => {
          mathBlocks.push(formula);
          return `@@MATH_BLOCK_${mathBlocks.length - 1}@@`;
        });
        processedText = processedText.replace(/\\\[([\s\S]+?)\\\]/g, (match, formula) => {
          mathBlocks.push(formula);
          return `@@MATH_BLOCK_${mathBlocks.length - 1}@@`;
        });

        // 2. Protect inline math $...$ and \(...\)
        processedText = processedText.replace(/\\\(([\s\S]+?)\\\)/g, (match, formula) => {
          mathInline.push(formula);
          return `@@MATH_INLINE_${mathInline.length - 1}@@`;
        });
        // Regex ensures it doesn't match single $ used for currency or within words
        processedText = processedText.replace(/(^|[^\\])\$([^\$\n]+?)\$/g, (match, prefix, formula) => {
          mathInline.push(formula);
          return `${prefix}@@MATH_INLINE_${mathInline.length - 1}@@`;
        });

        // 3. Handle <think> or <thought> tags (Thinking Space)
        processedText = processedText.replace(/<(think|thought)>([\s\S]*?)<\/\1>/gi, (match, tag, content) => {
          return `<details class="thinking-space"><summary>Thought Process</summary><div class="thinking-content">${content}</div></details>`;
        });
        // Handle unclosed tags during streaming
        const openThink = processedText.lastIndexOf('<think>');
        const closeThink = processedText.lastIndexOf('</think>');
        const openThought = processedText.lastIndexOf('<thought>');
        const closeThought = processedText.lastIndexOf('</thought>');

        if ((openThink > closeThink) || (openThought > closeThought)) {
          const isThink = openThink > openThought;
          const tag = isThink ? 'think' : 'thought';
          const openIdx = isThink ? openThink : openThought;
          const content = processedText.substring(openIdx + tag.length + 2);
          processedText = processedText.substring(0, openIdx) + `<details class="thinking-space" open><summary>Thinking...</summary><div class="thinking-content">${content}</div></details>`;
        }

        // 4. Intercept raw unformatted JSON widgets (if agent forgot backticks)
        const widgetRegex = /\{\s*"type"\s*:\s*"(choice|confirm|multi-select|slider)"/g;
        let match;
        while ((match = widgetRegex.exec(processedText)) !== null) {
          let openBraces = 0;
          let endIndex = -1;
          // Look backwards slightly to check if it's already inside backticks
          const beforeStr = processedText.substring(Math.max(0, match.index - 10), match.index);
          if (beforeStr.includes('`')) {
             // Likely already in a code block, let renderer.code handle it
             continue;
          }

          for (let i = match.index; i < processedText.length; i++) {
            if (processedText[i] === '{') openBraces++;
            else if (processedText[i] === '}') {
              openBraces--;
              if (openBraces === 0) {
                endIndex = i;
                break;
              }
            }
          }
          if (endIndex !== -1) {
            const jsonStr = processedText.substring(match.index, endIndex + 1);
            try {
              const data = JSON.parse(jsonStr);
              if (data && data.type) {
                const wrapped = '\n```widget\n' + jsonStr + '\n```\n';
                processedText = processedText.substring(0, match.index) + wrapped + processedText.substring(endIndex + 1);
                widgetRegex.lastIndex = match.index + wrapped.length;
              }
            } catch (e) {}
          }
        }

        const renderer = new marked.Renderer();
        const originalCodeRenderer = renderer.code.bind(renderer);

        renderer.code = function(tokenOrCode, language, isEscaped) {
          let codeText = '';
          let lang = '';
          
          // Handle marked v18+ token signature vs legacy signature
          if (typeof tokenOrCode === 'object' && tokenOrCode !== null) {
            codeText = tokenOrCode.text;
            lang = tokenOrCode.lang;
          } else {
            codeText = tokenOrCode;
            lang = language;
          }

          if (lang === 'widget' || lang === 'json' || !lang) {
            try {
              const data = JSON.parse(codeText);
              if (data && data.type) {
                if (data.type === 'timer') {
                  const widgetId = 'timer-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
                  const rawDuration = data.duration || data.time || data.seconds || 60;
                  const duration = parseInt(rawDuration, 10) || 60;
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
              }
            } catch (e) {
              if (lang === 'widget') {
                console.error("Failed to parse widget JSON:", e);
              }
              // If it's json or empty, just ignore the parse error and fall through to standard code block rendering
            }
          }

          if (lang === 'mermaid') {
            return `<div class="inline-widget inline-mermaid" data-raw="${escapeHtml(codeText)}"><div style="color:var(--text-muted); font-size:12px; padding:10px;">Rendering Diagram...</div></div>`;
          }

          if (lang === 'chart') {
            return `<div class="inline-widget inline-chart-wrapper"><canvas class="inline-chart" data-chart="${escapeHtml(codeText)}"></canvas></div>`;
          }

          if (lang === 'stack') {
            try {
              const data = JSON.parse(codeText);
              if (data && data.items && Array.isArray(data.items)) {
                const direction = data.direction === 'horizontal' ? 'row' : 'column';
                const itemsHtml = data.items.map(item => `
                  <div class="stack-item">
                    <span class="stack-label">${escapeHtml(item.label || '')}</span>
                    <span class="stack-value">${escapeHtml(item.value || '')}</span>
                  </div>
                `).join('');
                return `
                  <div class="inline-widget inline-stack direction-${direction}">
                    ${data.title ? `<div class="stack-title">${escapeHtml(data.title)}</div>` : ''}
                    <div class="stack-items">${itemsHtml}</div>
                  </div>
                `;
              }
            } catch (e) {
              console.error("Stack render error:", e);
            }
          }

          if (lang === 'carousel') {
            const slides = codeText.split('<!-- slide -->');
            const slidesHtml = slides.map((slide, index) => {
              // Parse the inner markdown for each slide
              // Using a fresh, simple marked configuration to avoid infinite recursive loops 
              // with our custom renderer hook if it had another carousel inside
              const innerHtml = marked.parse(slide.trim(), { breaks: true, gfm: true });
              return `<div class="carousel-slide" data-index="${index}" style="display: ${index === 0 ? 'block' : 'none'};">${innerHtml}</div>`;
            }).join('');
            
            const controlsHtml = slides.length > 1 ? `
              <div class="carousel-controls">
                <button class="carousel-btn prev" title="Previous Slide">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
                </button>
                <span class="carousel-dots">
                  ${slides.map((_, i) => `<span class="carousel-dot ${i === 0 ? 'active' : ''}"></span>`).join('')}
                </span>
                <button class="carousel-btn next" title="Next Slide">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                </button>
              </div>
            ` : '';

            return `
              <div class="inline-widget inline-carousel">
                <div class="carousel-slides-container">
                  ${slidesHtml}
                </div>
                ${controlsHtml}
              </div>
            `;
          }

          const displayLang = lang || 'code';
          if (typeof hljs !== 'undefined') {
            try {
              const validLang = (lang && hljs.getLanguage(lang)) ? lang : null;
              const highlighted = validLang 
                ? hljs.highlight(codeText, { language: validLang }).value 
                : hljs.highlightAuto(codeText).value;
              return `
                <div class="code-block-wrapper">
                  <div class="code-block-header">
                    <span class="code-lang">${escapeHtml(displayLang)}</span>
                    <button class="code-copy-btn" type="button">Copy</button>
                  </div>
                  <pre><code class="hljs ${validLang ? 'language-' + validLang : ''}">${highlighted}</code></pre>
                </div>
              `;
            } catch (e) {
              console.error("Highlight.js failed:", e);
            }
          }

          return `
            <div class="code-block-wrapper">
              <div class="code-block-header">
                <span class="code-lang">${escapeHtml(displayLang)}</span>
                <button class="code-copy-btn" type="button">Copy</button>
              </div>
              <pre><code class="${lang ? 'language-' + lang : ''}">${escapeHtml(codeText)}</code></pre>
            </div>
          `;
        };

        marked.setOptions({ breaks: true, gfm: true, renderer: renderer });
        let html = marked.parse(processedText);

        // 3. Restore and render math with KaTeX
        if (typeof katex !== 'undefined') {
          html = html.replace(/@@MATH_BLOCK_(\d+)@@/g, (match, index) => {
            try {
              return '<div class="math-block">' + katex.renderToString(mathBlocks[index], { displayMode: true, throwOnError: false }) + '</div>';
            } catch (e) {
              return '$$' + mathBlocks[index] + '$$';
            }
          });

          html = html.replace(/@@MATH_INLINE_(\d+)@@/g, (match, index) => {
            try {
              return katex.renderToString(mathInline[index], { displayMode: false, throwOnError: false });
            } catch (e) {
              return '$' + mathInline[index] + '$';
            }
          });
        }

        return html;
      }
    } catch (err) {
      console.error('Markdown error:', err);
    }
    return escapeHtml(text).replace(/\n/g, '<br>');
  }

  async function initializeInlineWidgets(container) {
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
        if (running) return;
        if (duration <= 0) duration = 60;
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
    });
    if (!container) return;

    // Initialize Mermaid
    if (typeof mermaid !== 'undefined') {
      try {
        mermaid.initialize({ startOnLoad: false, theme: document.documentElement.getAttribute('data-theme') === 'light' ? 'default' : 'dark' });
        const mermaidNodes = container.querySelectorAll('.inline-mermaid:not([data-rendered="true"])');
        for (let i = 0; i < mermaidNodes.length; i++) {
          const el = mermaidNodes[i];
          el.setAttribute('data-rendered', 'true');
          const id = 'mermaid-' + Date.now() + '-' + i + '-' + Math.floor(Math.random()*1000);
          try {
            const rawText = el.getAttribute('data-raw') || el.textContent;
            const { svg } = await mermaid.render(id, rawText);
            el.innerHTML = svg;
          } catch (err) {
            console.error('Mermaid render error:', err);
            el.innerHTML = `<pre style="color:var(--text-muted); font-size:12px;">Mermaid Error: ${escapeHtml(err.message)}</pre>`;
          }
        }
      } catch (e) {
        console.error('Mermaid init error:', e);
      }
    }

    // Initialize Chart.js
    if (typeof Chart !== 'undefined') {
      container.querySelectorAll('.inline-chart:not([data-rendered="true"])').forEach(canvas => {
        canvas.setAttribute('data-rendered', 'true');
        try {
          const dataStr = canvas.getAttribute('data-chart');
          const data = JSON.parse(dataStr);
          
          Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
          Chart.defaults.font.family = getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim();

          new Chart(canvas, data);
        } catch (e) {
          console.error("Chart.js render error:", e);
          const wrapper = canvas.parentElement;
          wrapper.innerHTML = `<pre style="color:var(--text-muted); font-size:12px;">Chart Error: ${escapeHtml(e.message)}</pre>`;
        }
      });
    }

    // Initialize Carousels
    container.querySelectorAll('.inline-carousel:not([data-rendered="true"])').forEach(carousel => {
      carousel.setAttribute('data-rendered', 'true');
      let currentSlide = 0;
      const slides = carousel.querySelectorAll('.carousel-slide');
      const dots = carousel.querySelectorAll('.carousel-dot');
      const prevBtn = carousel.querySelector('.carousel-btn.prev');
      const nextBtn = carousel.querySelector('.carousel-btn.next');

      const updateSlide = () => {
        slides.forEach((s, i) => s.style.display = i === currentSlide ? 'block' : 'none');
        dots.forEach((d, i) => d.classList.toggle('active', i === currentSlide));
      };

      if (prevBtn) prevBtn.addEventListener('click', () => {
        currentSlide = (currentSlide - 1 + slides.length) % slides.length;
        updateSlide();
      });

      if (nextBtn) nextBtn.addEventListener('click', () => {
        currentSlide = (currentSlide + 1) % slides.length;
        updateSlide();
      });
      
      dots.forEach((dot, i) => {
        dot.addEventListener('click', () => {
          currentSlide = i;
          updateSlide();
        });
      });
    });
  }

  function escapeHtml(str) { const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }
  function formatTime(ts) { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function scrollToBottom() { requestAnimationFrame(() => { dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight; }); }

  init();

  // ── Workers & Swarms Logic ──
  function pollWorkers() {
    // Poll Background Workers
    window.yoloAPI.fetchWorkers(state.userId)
      .then(res => {
        if (res.workers) {
          // Detect status changes for notifications
          res.workers.forEach(w => {
            const prevStatus = state.workerStates[w.task_id];
            if (prevStatus && prevStatus !== w.status) {
              if (w.status === 'completed' || w.status === 'failed') {
                window.yoloAPI.showNotification(
                  `Worker ${w.status === 'completed' ? 'Finished' : 'Failed'}`,
                  `Task ${w.task_id}: ${w.objective}`
                );
              }
            }
            state.workerStates[w.task_id] = w.status;
          });

          if (!dom.workersPanel.classList.contains('collapsed') && dom.tabWorkers.classList.contains('active')) {
            if (state.activeWorkerId) {
              fetchWorkerSession(state.activeWorkerId).catch(e => console.error(e));
            } else {
              renderWorkersList(res.workers);
            }
          }
        }
      })
      .catch(e => console.error("Worker poll failed", e));

    // Poll Swarms
    window.yoloAPI.fetchSwarms(state.userId)
      .then(res => {
        if (res.swarms) {
          if (!dom.workersPanel.classList.contains('collapsed') && dom.tabSwarms.classList.contains('active')) {
            if (state.activeSwarmId) {
              fetchSwarmMessages(state.activeSwarmId).catch(e => console.error(e));
            } else {
              renderSwarmsList(res.swarms);
            }
          }
        }
      })
      .catch(e => console.error("Swarm poll failed", e));

    setTimeout(pollWorkers, 3000);
  }

  function renderSwarmsList(swarms) {
    if (!swarms || swarms.length === 0) {
      dom.swarmsList.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;">No active swarms</div>';
      return;
    }
    dom.swarmsList.innerHTML = swarms.map(s => {
      // Calculate overall status based on workers
      let status = 'Running';
      if (s.workers && s.workers.length > 0) {
        if (s.workers.every(w => w.status === 'completed')) status = 'Completed';
        else if (s.workers.some(w => w.status === 'failed')) status = 'Failed';
        else if (s.workers.some(w => w.status === 'cancelled')) status = 'Cancelled';
      }

      return `
        <div class="swarm-item" data-id="${escapeHtml(s.swarm_id)}">
          <div class="worker-item-header">
            <span class="swarm-id-badge">${escapeHtml(s.swarm_id)}</span>
            <span class="worker-status ${escapeHtml(status.toLowerCase())}">${escapeHtml(status)}</span>
          </div>
          <div class="swarm-meta">
            ${s.workers.length} active workers<br>
            Last message: ${s.last_active ? formatTime(s.last_active) : 'N/A'}
          </div>
        </div>
      `;
    }).join('');

    dom.swarmsList.querySelectorAll('.swarm-item').forEach(item => {
      item.addEventListener('click', () => {
        state.activeSwarmId = item.dataset.id;
        dom.swarmChatTitle.textContent = state.activeSwarmId;
        dom.swarmsListView.classList.add('hidden');
        dom.swarmChatView.classList.remove('hidden');
        dom.swarmChatMessages.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted);">Loading swarm messages...</div>';
        fetchSwarmMessages(state.activeSwarmId);
      });
    });
  }

  async function fetchSwarmMessages(swarmId) {
    try {
      const res = await window.yoloAPI.fetchSwarmMessages(swarmId);
      if (res.messages) {
        renderSwarmChat(res.messages);
      }
    } catch (e) {
      console.error("Failed to fetch swarm messages", e);
    }
  }

  function renderSwarmChat(messages) {
    if (!messages || messages.length === 0) {
      dom.swarmChatMessages.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;">No messages in this swarm yet.</div>';
      return;
    }
    
    // Sort oldest first
    const sorted = [...messages].reverse();

    dom.swarmChatMessages.innerHTML = sorted.map(m => {
      // Create colored role badge
      const roleColor = `hsl(${Array.from(m.sender_role).reduce((acc, char) => acc + char.charCodeAt(0), 0) % 360}, 70%, 60%)`;
      
      return `
        <div class="msg user-msg" style="margin-bottom: 12px;">
          <div class="msg-header">
            <span style="font-weight: 600; color: ${roleColor}; font-size: 11px; text-transform: uppercase;">${escapeHtml(m.sender_role)}</span>
            <span style="opacity: 0.6; font-size: 10px;">${formatTime(m.created_at)}</span>
          </div>
          <div class="msg-content" style="font-size: 13px; line-height: 1.5; padding-top: 4px;">
            ${marked.parse(m.message)}
          </div>
        </div>
      `;
    }).join('');
    
    // Auto-scroll to bottom of swarm chat
    requestAnimationFrame(() => {
      dom.swarmChatMessages.scrollTop = dom.swarmChatMessages.scrollHeight;
    });
  }

  function renderWorkersList(workers) {
    if (!workers || workers.length === 0) {
      dom.workersList.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;">No active workers</div>';
      return;
    }
    dom.workersList.innerHTML = workers.map(w => `
      <div class="worker-item" data-id="${escapeHtml(w.task_id)}">
        <div class="worker-item-header">
          <span class="worker-task-id">${escapeHtml(w.task_id)}</span>
          <span class="worker-status ${escapeHtml(w.status.toLowerCase())}">${escapeHtml(w.status)}</span>
        </div>
        <div class="worker-objective">${escapeHtml(w.objective)}</div>
      </div>
    `).join('');

    dom.workersList.querySelectorAll('.worker-item').forEach(item => {
      item.addEventListener('click', () => {
        state.activeWorkerId = item.dataset.id;
        dom.workerChatTitle.textContent = state.activeWorkerId;
        dom.workersListView.classList.add('hidden');
        dom.workerChatView.classList.remove('hidden');
        dom.workerChatMessages.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted);">Loading session...</div>';
        fetchWorkerSession(state.activeWorkerId);
      });
    });
  }

  async function fetchWorkerSession(taskId) {
    try {
      const res = await window.yoloAPI.fetchWorkerSession(taskId);
      if (res.messages) {
        renderWorkerChat(res.messages);
      }
    } catch (e) {
      console.error("Failed to fetch worker session", e);
    }
  }

  function renderWorkerChat(messages) {
    dom.workerChatMessages.innerHTML = '';
    if (messages.length === 0) {
      dom.workerChatMessages.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;">No messages yet</div>';
      return;
    }
    messages.forEach(msg => {
      const el = createMessageEl(msg);
      dom.workerChatMessages.appendChild(el);
    });
    dom.workerChatMessages.scrollTop = dom.workerChatMessages.scrollHeight;
  }

  // Add mouse tracking effect for subtle lighting/depth
  document.addEventListener('mousemove', (e) => {
    const x = e.clientX;
    const y = e.clientY;
    document.documentElement.style.setProperty('--mouse-x', `${x}px`);
    document.documentElement.style.setProperty('--mouse-y', `${y}px`);
  });

})();
