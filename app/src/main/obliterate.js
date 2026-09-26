// The hang-up spell's window: transparent, click-through, over the whole
// display of the call, where the bolt lands and the call window shatters
// (renderer/obliterate.html). main.js decides when; this only shows it.

const path = require('node:path');
const { BrowserWindow, ipcMain, screen } = require('electron');

const ROOT = path.join(__dirname, '..', '..');

// ms from cast() until the call window is completely covered in crystal. Must
// match COVERED in renderer/obliterate.js; main hangs up then, behind it.
const COVERED_MS = 810;
const MAX_MS = 6000; // hide the window by then even if the page never says it's done

class Obliterator {
  constructor() {
    this.win = null;
    this.active = false;
    this.onDone = [];
    this.timer = null;
  }

  create() {
    this.win = new BrowserWindow({
      show: false,
      frame: false,
      transparent: true,
      resizable: false,
      movable: false,
      focusable: false,
      hasShadow: false,
      skipTaskbar: true,
      enableLargerThanScreen: true,
      backgroundColor: '#00000000',
      webPreferences: {
        preload: path.join(ROOT, 'src', 'preload', 'obliterate.js'),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
      },
    });
    this.win.setIgnoreMouseEvents(true);
    this.win.setAlwaysOnTop(true, 'screen-saver');
    this.win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    this.win.loadFile(path.join(ROOT, 'src', 'renderer', 'obliterate.html'));
    this.win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    this.win.webContents.on('will-navigate', (e) => e.preventDefault());
    ipcMain.on('spell:done', (e) => {
      if (e.sender === this.win.webContents) this.finish();
    });
  }

  // from: screen point where the spell left the wand. target: the call
  // window's screen bounds. snapshot: a data URL of the call window, or null.
  cast({ from, target, style, snapshot }) {
    const { bounds } = screen.getDisplayMatching(target);
    this.active = true;
    this.win.setBounds(bounds);
    this.win.showInactive();
    this.win.webContents.send('spell:cast', {
      from: { x: from.x - bounds.x, y: from.y - bounds.y },
      rect: { x: target.x - bounds.x, y: target.y - bounds.y, width: target.width, height: target.height },
      view: { width: bounds.width, height: bounds.height },
      style,
      snapshot: snapshot || null,
    });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.finish(), MAX_MS);
  }

  // The call is over (or won't end): break the crystal now.
  shatter() {
    if (this.active) this.win.webContents.send('spell:shatter');
  }

  // Runs fn once the spell has finished (right away if none is running).
  whenDone(fn) {
    if (this.active) this.onDone.push(fn);
    else fn();
  }

  finish() {
    if (!this.active) return;
    clearTimeout(this.timer);
    this.active = false;
    this.win.hide();
    const fns = this.onDone.splice(0);
    for (const fn of fns) fn();
  }
}

module.exports = { Obliterator, COVERED_MS };
