// Bridge for the settings window. Main validates everything it receives.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('settings', {
  get: () => ipcRenderer.invoke('settings:get'),
  save: (s) => ipcRenderer.invoke('settings:save', s),
  sendTest: () => ipcRenderer.invoke('settings:test'),
});
