const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('yoloAPI', {
  sendMessage: (payload) => ipcRenderer.invoke('send-message', payload),
  streamChat: (payload) => ipcRenderer.invoke('stream-chat', payload),
  onChatStreamEvent: (callback) => {
    ipcRenderer.on('chat-stream-event', (_event, data) => callback(data));
  },
  removeChatStreamListeners: () => {
    ipcRenderer.removeAllListeners('chat-stream-event');
  },
  runCommand: (payload) => ipcRenderer.invoke('run-command', payload),
  getSession: (payload) => ipcRenderer.invoke('get-session', payload),
  getSessions: () => ipcRenderer.invoke('get-sessions'),
  healthCheck: () => ipcRenderer.invoke('health-check'),
  fetchWorkers: (userId) => ipcRenderer.invoke('fetch-workers', userId),
  fetchWorkerSession: (taskId) => ipcRenderer.invoke('fetch-worker-session', taskId),
  fetchSwarms: (userId) => ipcRenderer.invoke('fetch-swarms', userId),
  fetchSwarmMessages: (swarmId) => ipcRenderer.invoke('fetch-swarm-messages', swarmId),
  showConfirmationDialog: (details) => ipcRenderer.invoke('show-confirmation-dialog', details),
  confirmAction: (payload) => ipcRenderer.invoke('confirm-action', payload),
  abortChatStream: () => ipcRenderer.invoke('abort-chat-stream'),
  showNotification: (title, body) => ipcRenderer.invoke('show-notification', { title, body }),
  onBridgeStatus: (callback) => {
    ipcRenderer.on('bridge-status', (_event, status) => callback(status));
  },
  transcribe: (payload) => ipcRenderer.invoke('transcribe', payload),
  updateEnv: (payload) => ipcRenderer.invoke('update-env', payload),
  getBridgePort: () => ipcRenderer.invoke('get-bridge-port'),
  getMcpServers: () => ipcRenderer.invoke('get-mcp-servers'),
  updateMcpServers: (payload) => ipcRenderer.invoke('update-mcp-servers', payload),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  openPath: (path) => ipcRenderer.invoke('open-path', path),
});
