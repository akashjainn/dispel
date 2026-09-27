// Bridge for the hang-up spell's window (renderer/obliterate.html). Main
// sends the spell; the page says when it has finished.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('spell', {
  onCast: (cb) => ipcRenderer.on('spell:cast', (_e, cast) => cb(cast)),
  onShatter: (cb) => ipcRenderer.on('spell:shatter', () => cb()),
  done: () => ipcRenderer.send('spell:done'),
});
