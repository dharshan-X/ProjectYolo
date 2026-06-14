const { app, BrowserWindow, ipcMain, dialog, Tray, Menu, Notification, globalShortcut, shell } = require('electron');
// Application menu will be configured per-window or hidden by default

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn } = require('child_process');

let mainWindow;
let tray;
let pyBridge;

function getBridgeToken() {
  // 1. Environment variable
  if (process.env.DESKTOP_BRIDGE_TOKEN) {
    return process.env.DESKTOP_BRIDGE_TOKEN;
  }

  // 2. Persistent file (~/.yolo/.bridge_token)
  const yoloHome = process.env.YOLO_HOME 
    ? path.resolve(process.env.YOLO_HOME)
    : path.join(require('os').homedir(), '.yolo');
  const tokenFile = path.join(yoloHome, '.bridge_token');

  if (fs.existsSync(tokenFile)) {
    try {
      return fs.readFileSync(tokenFile, 'utf8').trim();
    } catch (err) {
      console.error('[main] Failed to read bridge token file:', err);
    }
  }

  // 3. Generate new and persist
  const newToken = crypto.randomBytes(32).toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, ''); // Roughly match Python's urlsafe_token
  
  try {
    if (!fs.existsSync(yoloHome)) {
      fs.mkdirSync(yoloHome, { recursive: true });
    }
    fs.writeFileSync(tokenFile, newToken, { encoding: 'utf8', mode: 0o600 });
  } catch (err) {
    console.warn('[main] Could not persist bridge token:', err);
  }

  return newToken;
}

const BRIDGE_PORT = parseInt(process.env.DESKTOP_BRIDGE_PORT || '8790', 10);
const BRIDGE_TOKEN = getBridgeToken();
process.env.DESKTOP_BRIDGE_TOKEN = BRIDGE_TOKEN;

function bridgeUrl(pathname) {
  return `http://127.0.0.1:${BRIDGE_PORT}${pathname}`;
}

function bridgeOptions(options = {}) {
  return {
    ...options,
    headers: {
      ...(options.headers || {}),
      'X-Yolo-Bridge-Token': BRIDGE_TOKEN,
    },
  };
}

function bridgeFetch(pathname, options = {}) {
  return fetch(bridgeUrl(pathname), bridgeOptions(options));
}

function toggleWindow() {
  if (!mainWindow) {
    createWindow();
  } else if (mainWindow.isVisible() && mainWindow.isFocused()) {
    mainWindow.hide();
  } else {
    mainWindow.show();
    mainWindow.focus();
  }
}

function createTray() {
  const iconPath = path.join(__dirname, 'renderer', 'icon.png');
  // Note: if icon.png is missing, Tray may show a placeholder or empty space.
  tray = new Tray(iconPath);
  
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show/Hide Window',
      click: () => toggleWindow()
    },
    {
      label: 'Toggle YOLO Mode',
      click: async () => {
        try {
          // Fetch current session to determine current mode
          const resp = await bridgeFetch('/session?user_id=1');
          const session = await resp.json();
          const newMode = session.yolo_mode ? 'safe' : 'yolo';
          
          // Toggle via /command endpoint
          await bridgeFetch('/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: 'mode', args: [newMode], user_id: 1 }),
          });
          
          // Notify renderer if window exists
          mainWindow?.webContents?.send('mode-toggled', { mode: newMode });
          
          console.log(`[tray] YOLO Mode toggled to: ${newMode}`);
        } catch (err) {
          console.error('[tray] Failed to toggle YOLO mode:', err);
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Exit',
      click: () => {
        app.quit();
      }
    }
  ]);

  tray.setToolTip('Yolo AI Agent');
  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
    } else {
      createWindow();
    }
  });
}

const CONFIG_PATH = path.join(app.getPath('userData'), 'window-state.json');

function loadWindowState() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    }
  } catch (err) {
    console.error('[main] Failed to load window state:', err);
  }
  return { width: 1280, height: 820 }; // Default size
}

function saveWindowState() {
  if (!mainWindow) return;
  try {
    const bounds = mainWindow.getBounds();
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(bounds));
  } catch (err) {
    console.error('[main] Failed to save window state:', err);
  }
}

function createWindow() {
  const state = loadWindowState();

  mainWindow = new BrowserWindow({
    width: state.width,
    height: state.height,
    x: state.x,
    y: state.y,
    minWidth: 900,
    minHeight: 600,
    title: 'Yolo',
    icon: path.join(__dirname, 'renderer', 'icon.png'),
    backgroundColor: '#121212',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    frame: process.platform === 'darwin' ? false : true,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });
  
  // Enable shortcuts since menu is hidden
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.control && input.key.toLowerCase() === 'r') {
      mainWindow.reload();
      event.preventDefault();
    }
    if (input.control && input.shift && input.key.toLowerCase() === 'i') {
      mainWindow.webContents.openDevTools();
      event.preventDefault();
    }
    if (input.control && input.key.toLowerCase() === 'z') {
      mainWindow.webContents.undo();
      event.preventDefault();
    }
    if (input.control && (input.key.toLowerCase() === 'y' || (input.shift && input.key.toLowerCase() === 'z'))) {
      mainWindow.webContents.redo();
      event.preventDefault();
    }
    if (input.control && input.key.toLowerCase() === 'c') {
      mainWindow.webContents.copy();
    }
    if (input.control && input.key.toLowerCase() === 'v') {
      mainWindow.webContents.paste();
    }
    if (input.control && input.key.toLowerCase() === 'x') {
      mainWindow.webContents.cut();
    }
    if (input.control && input.key.toLowerCase() === 'a') {
      mainWindow.webContents.selectAll();
    }
  });

  // Save state on move or resize
  mainWindow.on('resize', saveWindowState);
  mainWindow.on('move', saveWindowState);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── IPC Handlers (all relay to the bridge started by server.py / bot.py) ──

ipcMain.handle('send-message', async (_event, { message, userId, attachments }) => {
  try {
    const resp = await bridgeFetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, user_id: userId || 1, attachments: attachments || [] }),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('get-session', async (_event, { userId }) => {
  try {
    const resp = await bridgeFetch(`/session?user_id=${userId || 1}`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { messages: [], history_length: 0 };
  }
});

ipcMain.handle('get-sessions', async () => {
  try {
    const resp = await bridgeFetch('/sessions', { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { sessions: [] };
  }
});

ipcMain.handle('health-check', async () => {
  try {
    const resp = await bridgeFetch('/health', { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { status: 'offline' };
  }
});

ipcMain.handle('fetch-workers', async (_event, userId) => {
  try {
    const resp = await bridgeFetch(`/workers?user_id=${userId || 1}`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { workers: [] };
  }
});

ipcMain.handle('fetch-swarms', async (_event, userId) => {
  try {
    const resp = await bridgeFetch(`/swarms?user_id=${userId || 1}`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { swarms: [] };
  }
});

ipcMain.handle('fetch-swarm-messages', async (_event, swarmId) => {
  try {
    const resp = await bridgeFetch(`/swarms/${swarmId}/messages`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { messages: [] };
  }
});

ipcMain.handle('fetch-worker-session', async (_event, taskId) => {
  try {
    const resp = await bridgeFetch(`/workers/${taskId}/session`, { cache: 'no-store' });
    return await resp.json();
  } catch {
    return { messages: [] };
  }
});

ipcMain.handle('run-command', async (_event, { command, args, userId, attachments }) => {
  try {
    const resp = await bridgeFetch('/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, args: args || [], user_id: userId || 1, attachments: attachments || [] }),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('show-confirmation-dialog', async (_event, details) => {
  const { action, tool_args } = details;
  const result = dialog.showMessageBoxSync(mainWindow, {
    type: 'question',
    buttons: ['Confirm', 'Deny'],
    defaultId: 0,
    cancelId: 1,
    title: 'Action Confirmation',
    message: `The agent wants to execute: ${action}`,
    detail: `Arguments: ${JSON.stringify(tool_args, null, 2)}\n\nDo you want to allow this?`,
  });
  return result; // 0 for Confirm, 1 for Deny
});

ipcMain.handle('confirm-action', async (_event, { confirmed, userId }) => {
  try {
    const resp = await bridgeFetch('/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed, user_id: userId || 1 }),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('show-notification', (_event, { title, body }) => {
  if (Notification.isSupported()) {
    new Notification({
      title,
      body,
      icon: path.join(__dirname, 'renderer', 'icon.png'),
    }).show();
  }
});

let currentAbortController = null;

// Streaming chat: opens SSE connection to /chat/stream and relays events to renderer
ipcMain.handle('stream-chat', async (_event, { message, userId, attachments }) => {
  if (currentAbortController) {
    currentAbortController.abort();
  }
  currentAbortController = new AbortController();

  try {
    const resp = await bridgeFetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, user_id: userId || 1, attachments: attachments || [] }),
      signal: currentAbortController.signal,
    });

    if (!resp.ok) {
      const errBody = await resp.text();
      mainWindow?.webContents?.send('chat-stream-event', { type: 'error', data: errBody });
      return { error: errBody };
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const parts = buffer.split('\n\n');
      buffer = parts.pop(); // keep incomplete chunk

      for (const part of parts) {
        const lines = part.split('\n');
        let eventType = 'message';
        let data = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          else if (line.startsWith('data: ')) data = line.slice(6);
        }
        if (data) {
          try {
            const parsed = JSON.parse(data);
            mainWindow?.webContents?.send('chat-stream-event', { type: eventType, data: parsed });
          } catch {
            mainWindow?.webContents?.send('chat-stream-event', { type: eventType, data });
          }
        }
      }
    }
    return { ok: true };
  } catch (err) {
    if (err.name === 'AbortError') {
      console.log('[main] Chat stream aborted');
      mainWindow?.webContents?.send('chat-stream-event', { type: 'error', data: 'Stream aborted' });
      return { error: 'Stream aborted' };
    }
    mainWindow?.webContents?.send('chat-stream-event', { type: 'error', data: err.message });
    return { error: err.message };
  } finally {
    currentAbortController = null;
  }
});

ipcMain.handle('abort-chat-stream', () => {
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
    return { ok: true };
  }
  return { ok: false };
});

ipcMain.handle('transcribe', async (_event, { audio }) => {
  try {
    const resp = await bridgeFetch('/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio }),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('update-env', async (_event, payload) => {
  try {
    const resp = await bridgeFetch('/config/env', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('get-bridge-port', () => {
  return BRIDGE_PORT;
});

ipcMain.handle('get-mcp-servers', async () => {
  try {
    const resp = await bridgeFetch('/mcp/servers');
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('update-mcp-servers', async (_event, payload) => {
  try {
    const resp = await bridgeFetch('/mcp/servers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await resp.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('open-external', async (_event, url) => {
  // Only allow http and https URLs
  try {
    const parsed = new URL(url);
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return { error: `Blocked: unsafe URL scheme '${parsed.protocol}'` };
    }
    await shell.openExternal(url);
    return { ok: true };
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('open-path', async (_event, filePath) => {
  // Basic validation: must be absolute and not contain traversal
  const resolved = path.resolve(filePath);
  if (resolved !== filePath && !resolved.startsWith(path.resolve(filePath))) {
    return { error: 'Path validation failed' };
  }
  const err = await shell.openPath(resolved);
  if (err) return { error: err };
  return { ok: true };
});

// ── App lifecycle ──

app.whenReady().then(() => {
  // Start Python Bridge automatically
  const projectRoot = path.join(__dirname, '..');
  const venvPython = process.platform === 'win32' 
    ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(projectRoot, '.venv', 'bin', 'python3');
  
  const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
  console.log(`[main] Starting Python Bridge using: ${pythonCmd}`);

  const yoloCwd = process.env.YOLO_CWD || process.cwd();
  pyBridge = spawn(pythonCmd, [path.join(__dirname, 'api_bridge.py')], { 
    stdio: 'inherit',
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    cwd: yoloCwd,
    detached: false
  });

  pyBridge.on('exit', (code, signal) => {
    console.error(`[main] Python bridge exited (code=${code}, signal=${signal})`);
    // Notify renderer
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('bridge-status', { status: 'offline', code, signal });
    }
  });

  pyBridge.on('error', (err) => {
    console.error('[main] Python bridge error:', err);
  });

  createWindow();
  createTray();

  // Register global shortcut
  const shortcut = process.platform === 'darwin' ? 'Command+Shift+Y' : 'Control+Shift+Y';
  const ret = globalShortcut.register(shortcut, () => {
    console.log(`[main] Global shortcut ${shortcut} pressed`);
    toggleWindow();
  });

  if (!ret) {
    console.error('[main] Registration failed for shortcut:', shortcut);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', () => {
  // Unregister all shortcuts
  globalShortcut.unregisterAll();
});

app.on('quit', () => {
  if (pyBridge && !pyBridge.killed) {
    try {
      // Kill the entire process group
      process.kill(-pyBridge.pid, 'SIGTERM');
    } catch (e) {
      try { pyBridge.kill('SIGTERM'); } catch (_) {}
    }
  }
});
