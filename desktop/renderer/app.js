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
    selectedFiles: [], // Added for visual chips
    activePaletteIndex: -1, // Added for keyboard navigation
    workerStates: {}, // Track task_id -> status
    bridgePort: 8790, // Default fallback
  };

  // ── History (Undo/Redo) ──
  const fileHistory = [];
  function saveFileState() {
    const last = fileHistory[fileHistory.length - 1];
    if (last && last.length === state.selectedFiles.length) {
      const match = last.every((f, i) => f.name === state.selectedFiles[i].name);
      if (match) return;
    }
    fileHistory.push([...state.selectedFiles]);
    if (fileHistory.length > 50) fileHistory.shift();
  }

  function undoFile() {
    if (fileHistory.length > 0) {
      state.selectedFiles = fileHistory.pop();
      renderAttachmentChips();
      if (state.selectedFiles.length === 0 && !dom.input.value.trim()) {
        dom.sendBtn.disabled = true;
      }
    }
  }

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
    
    if (data.type === 'choice') {
      const optionsHtml = (data.options || []).map(opt => {
        const label = opt.label.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const val = opt.value.replace(/"/g, '&quot;');
        return `<button class="widget-btn" data-widget-id="${data.id}" data-value="${val}">${label}</button>`;
      }).join('');
      
      const title = (data.text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      
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
      
      dom.activeWidgetContainer.innerHTML = `
        <div class="dynamic-widget textbar-widget" id="widget-${data.id}">
          <div class="widget-title">${title}</div>
          <div class="widget-options">
            ${optionsHtml}
          </div>
          ${customInputHtml}
          <div class="widget-cancel" onclick="window.clearActiveWidget()">Cancel</div>
        </div>
      `;
      
      dom.inputWrapper.classList.add('hidden');
      dom.activeWidgetContainer.classList.remove('hidden');
      
      if (data.allow_custom) {
        const inputEl = dom.activeWidgetContainer.querySelector('.widget-custom-input');
        if (inputEl) inputEl.focus();
      }
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
    workersListView: $('#workers-list-view'),
    workersList: $('#workers-list'),
    workerChatView: $('#worker-chat-view'),
    backToWorkers: $('#back-to-workers'),
    workerChatTitle: $('#worker-chat-title'),
    workerChatMessages: $('#worker-chat-messages'),
    voiceBtn: $('#voice-btn'),
    recordingIndicator: $('#recording-indicator'),
    fileUpload: $('#file-upload'),
    cancelVoiceBtn: $('#cancel-voice-btn'),
    recordingTime: $('.recording-time'),
    attachMenu: $('#attach-menu'),
    stopBtn: $('#stop-btn'),
    toggleSettingsSidebar: $('#toggle-settings-sidebar'),
    settingsSidebar: $('.settings-sidebar'),
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
        saveFileState();
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
      }
    } catch {}
  }

  function savePrefs() {
    try {
      localStorage.setItem('yolo-desktop-prefs', JSON.stringify({
        userId: state.userId,
        theme: state.theme,
      }));
    } catch {}
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

        // Update subtitle (Session title removed as per request)
        const historyLen = data.history_length || 0;
        const totalTokens = data.total_tokens || 0;
        const llmCalls = data.llm_call_count || 0;
        dom.chatSubtitle.textContent = `${historyLen} MSGS · ${totalTokens} TOKENS · ${llmCalls} LLM CALLS`;
        
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
      <div class="welcome-icon">
        <div class="welcome-glow"></div>
        <span style="font-family: 'Playfair Display', serif; font-style: italic;">Y</span>
      </div>
      <h1 style="font-family: 'Playfair Display', serif; font-style: italic; letter-spacing: -0.02em;">Welcome to Yolo</h1>
      <p style="font-family: 'DM Sans', sans-serif;">Your autonomous AI agent. Ask anything — code, research, system control, and more.</p>
      <p style="font-size:12px; color:var(--text-muted); margin-top:8px;">Session is shared with Telegram &amp; CLI. Type <kbd>/</kbd> for commands.</p>
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

    saveFileState();
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
            summary.innerHTML = `<span class="tool-status-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/></svg></span> Running <code>${data.name}</code>...`;
            
            const logContent = document.createElement('div');
            logContent.className = 'tool-log-content';
            logContent.innerHTML = `<div class="tool-call-info"><strong>Arguments:</strong> <code>${JSON.stringify(data.args || {})}</code></div><div class="tool-result-placeholder">Waiting for result...</div>`;
            
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
              
              summary.innerHTML = `<span class="tool-status-icon success"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span> Executed <code>${data.name}</code>`;
              
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
                <div class="artifact-title">Generated Image: ${data.name}</div>
                <img src="${fullImgUrl}" class="artifact-image" alt="${data.name}" style="max-width: 100%; border-radius: 8px; margin-top: 8px; cursor: pointer;" onclick="openLink('${data.url}')" />
                <div class="artifact-actions" style="margin-top: 8px;">
                  <button class="primary-btn sm" onclick="openLink('${data.url}')">View Full Size</button>
                </div>
              `;
            } else {
              artifactWrapper.innerHTML = `
                <div class="artifact-title">Generated File: ${data.name}</div>
                <div class="artifact-file-info" style="display: flex; align-items: center; gap: 10px; padding: 12px; background: rgba(0,0,0,0.05); border-radius: 8px; margin-top: 8px;">
                   <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14.5 2 14.5 7.5 20 7.5"></polyline></svg>
                   <span style="font-family: monospace; font-size: 0.9em;">${data.name}</span>
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

        // Cleanup: remove the stream listener
        window.yoloAPI.removeChatStreamListeners();

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
      state.isLoading = false;
      dom.stopBtn.classList.add('hidden');
      dom.voiceBtn.classList.remove('hidden');
    }
  }

  function syncModeBadge() {
    const label = dom.modeToggle.querySelector('.mode-label');
    label.textContent = state.yoloMode ? 'YOLO' : 'Safe';
    label.classList.toggle('yolo', state.yoloMode);
  }

  async function refreshSessionMeta() {
    try {
      const data = await window.yoloAPI.getSession({ userId: state.userId });
      if (data) {
        const historyLen = data.history_length || 0;
        const totalTokens = data.total_tokens || 0;
        const llmCalls = data.llm_call_count || 0;
        dom.chatSubtitle.textContent = `${historyLen} MSGS · ${totalTokens} TOKENS · ${llmCalls} LLM CALLS`;
      }
    } catch {}
  }

  // ── Events ──
  function bindEvents() {
    // Update the click listener:
    dom.activeWidgetContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.widget-btn');
      const sendBtn = e.target.closest('.widget-custom-send-btn');
      
      const widget = e.target.closest('.dynamic-widget');
      if (!widget || widget.classList.contains('locked')) return;

      if (btn) {
        // Lock the widget visually
        widget.classList.add('locked');
        btn.setAttribute('data-selected', 'true');

        // Extract value
        const value = btn.getAttribute('data-value');
        const widgetId = btn.getAttribute('data-widget-id');
        
        // Force isLoading to false so the message isn't dropped if clicked immediately
        state.isLoading = false;
        
        // Send the response
        sendMessage(`[Widget Response: ${widgetId}] Selected: ${value}`);
        
        setTimeout(() => clearActiveWidget(), 300);
      } else if (sendBtn) {
        const inputEl = widget.querySelector('.widget-custom-input');
        const value = inputEl ? inputEl.value.trim() : '';
        if (!value) return;

        widget.classList.add('locked');
        const widgetId = inputEl.getAttribute('data-widget-id');
        
        // Force isLoading to false so the message isn't dropped if clicked immediately
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
      const newHeight = Math.min(dom.input.scrollHeight, 80); // Stricter cap for 3 rows
      dom.input.style.height = newHeight + 'px';
      const val = dom.input.value;
      if (val.startsWith('/') && !val.includes('\n')) {
        showCommandPalette(val.slice(1).split(/\s/)[0]);
      } else {
        hideCommandPalette();
      }
    });

    dom.input.addEventListener('blur', () => setTimeout(hideCommandPalette, 200));

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
      dom.attachBtn.classList.toggle('active', !isHidden);
    });

    document.querySelectorAll('.attach-menu-item').forEach(item => {
      item.addEventListener('click', () => {
        dom.input.focus(); // This will expand the bar
        dom.attachMenu.classList.add('hidden');
        dom.attachBtn.classList.remove('active');
        dom.fileUpload.click();
      });
    });

    // Close attach menu on click outside
    document.addEventListener('mousedown', (e) => {
      if (dom.attachMenu && !dom.attachMenu.classList.contains('hidden')) {
        if (!dom.attachMenu.contains(e.target) && !dom.attachBtn.contains(e.target)) {
          dom.attachMenu.classList.add('hidden');
          dom.attachBtn.classList.remove('active');
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
        
        if (file.type.startsWith('image/')) {
          reader.readAsDataURL(file);
        } else {
          reader.readAsText(file);
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
        saveFileState();
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
        saveFileState();
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
        saveFileState();
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
          saveFileState();
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

    dom.settingsBtn.addEventListener('click', () => {
      dom.settingUserId.value = state.userId;
      dom.settingMode.value = state.yoloMode ? 'yolo' : 'safe';
      dom.settingsModal.classList.remove('hidden');
      updateMemoryStats();
    });
    dom.closeSettings.addEventListener('click', () => dom.settingsModal.classList.add('hidden'));
    
    // Workers
    dom.workersToggleBtn.addEventListener('click', () => {
      dom.workersPanel.classList.toggle('hidden');
    });
    dom.closeWorkers.addEventListener('click', () => {
      dom.workersPanel.classList.add('hidden');
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
    dom.settingsModal.addEventListener('click', (e) => {
      if (e.target === dom.settingsModal) dom.settingsModal.classList.add('hidden');
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

    // Global Undo for Files
    window.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key.toLowerCase() === 'z') {
        // Simple heuristic: if we are not typing anything in the textarea, allow file undo
        if (document.activeElement !== dom.input || dom.input.value === '') {
          undoFile();
        }
      }
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

          if (lang === 'widget') {
            try {
              const data = JSON.parse(codeText);
              if (typeof renderActiveWidget === 'function') {
                renderActiveWidget(data);
              }
              return `<div class="widget-placeholder"><em>[Interactive Widget Expanded]</em></div>`;
            } catch (e) {
              console.error("Failed to parse widget JSON:", e);
            }
          }

          if (typeof hljs !== 'undefined') {
            try {
              const validLang = (lang && hljs.getLanguage(lang)) ? lang : null;
              const highlighted = validLang 
                ? hljs.highlight(codeText, { language: validLang }).value 
                : hljs.highlightAuto(codeText).value;
              return `<pre><code class="hljs ${validLang ? 'language-' + validLang : ''}">${highlighted}</code></pre>`;
            } catch (e) {
              console.error("Highlight.js failed:", e);
            }
          }

          return `<pre><code class="${lang ? 'language-' + lang : ''}">${escapeHtml(codeText)}</code></pre>`;
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

  function escapeHtml(str) { const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }
  function formatTime(ts) { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function scrollToBottom() { requestAnimationFrame(() => { dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight; }); }

  init();

  // ── Workers Logic ──
  function pollWorkers() {
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

          if (!dom.workersPanel.classList.contains('hidden')) {
            if (state.activeWorkerId) {
              fetchWorkerSession(state.activeWorkerId).catch(e => console.error(e));
            } else {
              renderWorkersList(res.workers);
            }
          }
        }
      })
      .catch(e => console.error("Worker poll failed", e));

    setTimeout(pollWorkers, 3000);
  }

  function renderWorkersList(workers) {
    if (!workers || workers.length === 0) {
      dom.workersList.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;">No active workers</div>';
      return;
    }
    dom.workersList.innerHTML = workers.map(w => `
      <div class="worker-item" data-id="${w.task_id}">
        <div class="worker-item-header">
          <span class="worker-task-id">${w.task_id}</span>
          <span class="worker-status ${w.status.toLowerCase()}">${w.status}</span>
        </div>
        <div class="worker-objective">${w.objective}</div>
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
