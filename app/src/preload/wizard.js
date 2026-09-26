// The only bridge between the wizard page and the main process.
const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('wizard', {
  onState: (cb) => ipcRenderer.on('wizard:state', (_e, state) => cb(state)),
  pickFile: () => ipcRenderer.send('wizard:pick-file'),
  dismissBubble: () => ipcRenderer.send('wizard:dismiss-bubble'),
  vanished: () => ipcRenderer.send('wizard:vanished'),
  drag: (phase, x, y) => ipcRenderer.send('wizard:drag', phase, x, y),
});

// Dropped files are handled here, not in the page: a File passed through
// contextBridge is copied and loses its path on disk, so getPathForFile must
// see the original event. The page only draws the hover glow.
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  ipcRenderer.send('wizard:analyze-path', webUtils.getPathForFile(file));
});
