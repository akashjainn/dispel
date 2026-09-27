const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('callsim', {
  list: () => ipcRenderer.invoke('clips:list'),
  // Dropped File objects → their paths on disk; main copies them into clips/<label>/.
  add: (files, label) => ipcRenderer.invoke('clips:add', Array.from(files, (f) => webUtils.getPathForFile(f)), label),
  openFolder: () => ipcRenderer.invoke('clips:open'),
  askMic: () => ipcRenderer.invoke('mic:ask'),
  onChanged: (fn) => ipcRenderer.on('clips-changed', () => fn()),
});
