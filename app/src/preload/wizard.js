// The only bridge between the wizard page and the main process.
const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('wizard', {
  onState: (cb) => ipcRenderer.on('wizard:state', (_e, state) => cb(state)),
  pickFile: () => ipcRenderer.send('wizard:pick-file'),
  analyzeFile: (file) => ipcRenderer.send('wizard:analyze-path', webUtils.getPathForFile(file)),
  dismissBubble: () => ipcRenderer.send('wizard:dismiss-bubble'),
  vanished: () => ipcRenderer.send('wizard:vanished'),
  drag: (phase, x, y) => ipcRenderer.send('wizard:drag', phase, x, y),
});
