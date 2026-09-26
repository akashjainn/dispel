// Menu-bar wizard. Owns the tray, the wizard window, the call-highlight
// overlay, and the flow between them. The renderer only draws what it's told.

const path = require('node:path');
const fs = require('node:fs');
const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, dialog, screen, shell } = require('electron');

const analyzer = require('./analyzer');
const { logResult, logPath } = require('./results-log');
const { CallWatch } = require('./callwatch');

const ROOT = path.join(__dirname, '..', '..');
const ASSETS = path.join(ROOT, 'Assets');
const RENDERER = path.join(ROOT, 'src', 'renderer');

const AUDIO_EXTS = new Set(['.wav', '.mp3', '.m4a', '.mp4', '.aac', '.ogg', '.oga', '.opus', '.flac', '.webm', '.mov']);
const MAX_FILE_BYTES = 500 * 1024 * 1024;

// Window sizes (px). The wizard is drawn at 2x; the bubble sits to its left.
const SIZE = {
  desktop: { width: 180, height: 300 }, // wizard + cauldron
  desktopBubble: { width: 440, height: 300 },
  call: { width: 180, height: 170 }, // wizard only
  callBubble: { width: 440, height: 300 },
};
const CALL_INSET = 12; // gap between the wizard and the call window's corner
const EDGE = 40; // gap from the screen edge for the default desktop spot

let tray = null;
let wizard = null;
let overlay = null;
const calls = new CallWatch();

// Where the wizard's bottom-right corner sits on the desktop. Dragging moves it.
let desktopAnchor = null;
let wizardVisible = false; // desktop visibility, independent of call mode
let mode = 'hidden'; // hidden | idle | analyzing | result | call-watch | call-alert
let bubble = false;
let busy = false; // a file analysis is running
let callSession = null; // { id, app, bounds, alerted, wasVisible }
let guardEnabled = true;

// ---------- windows ----------

function createWizard() {
  wizard = new BrowserWindow({
    ...SIZE.desktop,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    hasShadow: false,
    skipTaskbar: true,
    fullscreenable: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(ROOT, 'src', 'preload', 'wizard.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  wizard.setAlwaysOnTop(true, 'screen-saver');
  wizard.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  wizard.loadFile(path.join(RENDERER, 'wizard.html'));
  wizard.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  wizard.webContents.on('will-navigate', (e) => e.preventDefault());
}

function createOverlay() {
  overlay = new BrowserWindow({
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    focusable: false,
    hasShadow: false,
    skipTaskbar: true,
    backgroundColor: '#00000000',
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  overlay.setIgnoreMouseEvents(true);
  overlay.setAlwaysOnTop(true, 'floating');
  overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  overlay.loadFile(path.join(RENDERER, 'overlay.html'));
}

function defaultAnchor() {
  const { workArea } = screen.getPrimaryDisplay();
  return { right: workArea.x + workArea.width - EDGE, bottom: workArea.y + workArea.height - EDGE };
}

function callAnchor(bounds) {
  if (!bounds) return defaultAnchor();
  return { right: bounds.x + bounds.width - CALL_INSET, bottom: bounds.y + bounds.height - CALL_INSET };
}

function currentAnchor() {
  return callSession ? callAnchor(callSession.bounds) : desktopAnchor;
}

// Resize the wizard window around its bottom-right anchor.
function placeWizard() {
  const inCall = mode.startsWith('call');
  const size = inCall ? (bubble ? SIZE.callBubble : SIZE.call) : bubble ? SIZE.desktopBubble : SIZE.desktop;
  const a = currentAnchor();
  wizard.setBounds({
    x: Math.round(a.right - size.width),
    y: Math.round(a.bottom - size.height),
    width: size.width,
    height: size.height,
  });
}

function setMode(next, payload = {}) {
  mode = next;
  bubble = ['analyzing', 'result', 'call-alert'].includes(next);
  if (next === 'hidden') {
    wizard.webContents.send('wizard:state', { mode: 'hidden' });
    return;
  }
  placeWizard();
  wizard.webContents.send('wizard:state', { mode: next, ...payload });
  if (!wizard.isVisible()) wizard.showInactive();
}

function showOverlay(bounds) {
  if (!bounds) return;
  const pad = 8;
  overlay.setBounds({
    x: bounds.x - pad,
    y: bounds.y - pad,
    width: bounds.width + pad * 2,
    height: bounds.height + pad * 2,
  });
  if (!overlay.isVisible()) overlay.showInactive();
  wizard.moveTop();
}

// ---------- desktop wizard ----------

function summon() {
  wizardVisible = true;
  if (callSession) return; // call mode owns the wizard until the call ends
  setMode('idle', { appear: true });
}

function dismiss() {
  wizardVisible = false;
  if (callSession) return;
  wizard.webContents.send('wizard:state', { mode: 'vanish' });
  // The renderer plays the sink-into-hat animation, then asks to be hidden.
}

function toggleWizard() {
  if (wizardVisible) dismiss();
  else summon();
}

async function analyzeFile(filePath) {
  if (busy || callSession) return;
  busy = true;
  const name = path.basename(filePath);
  wizardVisible = true;
  setMode('analyzing', { name });
  try {
    const result = await analyzer.analyze('file');
    logResult({ source: 'file', name, result });
    if (callSession) return; // a call took over the wizard meanwhile
    setMode('result', { name, result });
  } catch (err) {
    console.error('[analyze]', err);
    if (!callSession) setMode('result', { name, error: 'I couldn’t read that file.' });
  } finally {
    busy = false;
  }
}

async function pickFile() {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: 'Choose an audio file for the wizard',
    properties: ['openFile'],
    filters: [{ name: 'Audio', extensions: [...AUDIO_EXTS].map((e) => e.slice(1)) }],
  });
  if (!canceled && filePaths[0]) analyzeFile(filePaths[0]);
}

function validAudioPath(p) {
  if (typeof p !== 'string' || !path.isAbsolute(p)) return false;
  if (!AUDIO_EXTS.has(path.extname(p).toLowerCase())) return false;
  try {
    const st = fs.statSync(p);
    return st.isFile() && st.size > 0 && st.size <= MAX_FILE_BYTES;
  } catch {
    return false;
  }
}

// ---------- call mode ----------

async function onCallStarted({ app: callApp, bounds }) {
  if (!guardEnabled) return;
  const session = { id: Date.now(), app: callApp, bounds, alerted: false, wasVisible: wizardVisible };
  callSession = session;
  console.log('[call] started:', callApp, bounds);
  setMode('call-watch', { app: callApp, appear: !wizard.isVisible() });

  // MOCK: no audio is captured yet. We wait out the mock latency and use the
  // mock score, which always lands above the alert threshold.
  const result = await analyzer.analyze('call');
  if (callSession !== session) return; // call ended or restarted meanwhile
  logResult({ source: 'call', name: callApp, result });
  if (result.overall.probability >= analyzer.SYNTHETIC_AT) {
    session.alerted = true;
    showOverlay(session.bounds);
    setMode('call-alert', { app: callApp, result });
  }
}

function onCallMoved({ bounds }) {
  if (!callSession) return;
  callSession.bounds = bounds;
  placeWizard();
  if (callSession.alerted) showOverlay(bounds);
}

function onCallEnded() {
  if (!callSession) return;
  console.log('[call] ended:', callSession.app);
  const { wasVisible } = callSession;
  callSession = null;
  overlay.hide();
  if (wasVisible || wizardVisible) setMode('idle');
  else {
    wizard.hide();
    mode = 'hidden';
  }
}

function simulateCall() {
  if (callSession) {
    calls.endSimulated();
    return;
  }
  const { workArea } = screen.getPrimaryDisplay();
  const width = Math.round(workArea.width * 0.6);
  const height = Math.round(workArea.height * 0.6);
  calls.simulate({
    x: workArea.x + Math.round((workArea.width - width) / 2),
    y: workArea.y + Math.round((workArea.height - height) / 2),
    width,
    height,
  });
}

// ---------- tray ----------

function trayIcon() {
  // Wizard's face from the first idle frame, sized for the menu bar.
  const sheet = nativeImage.createFromPath(path.join(ASSETS, 'wizard-sprites.png'));
  const face = sheet.crop({ x: 20, y: 16, width: 48, height: 48 });
  const icon = nativeImage.createEmpty();
  icon.addRepresentation({ scaleFactor: 1, buffer: face.resize({ width: 18, height: 18, quality: 'best' }).toPNG() });
  icon.addRepresentation({ scaleFactor: 2, buffer: face.resize({ width: 36, height: 36, quality: 'best' }).toPNG() });
  return icon;
}

function trayMenu() {
  return Menu.buildFromTemplate([
    { label: wizardVisible ? 'Send wizard away' : 'Summon wizard', click: toggleWizard },
    { label: 'Check an audio file…', click: pickFile, enabled: !busy && !callSession },
    { type: 'separator' },
    {
      label: 'Watch calls',
      type: 'checkbox',
      checked: guardEnabled,
      click: (item) => {
        guardEnabled = item.checked;
        if (!guardEnabled && callSession) onCallEnded();
      },
    },
    { label: callSession ? 'End simulated call' : 'Simulate a call (demo)', click: simulateCall },
    { type: 'separator' },
    { label: 'Open results log', click: () => shell.showItemInFolder(logPath()) },
    { label: 'Quit', role: 'quit' },
  ]);
}

function createTray() {
  tray = new Tray(trayIcon());
  tray.setToolTip('Dispel wizard');
  tray.on('click', toggleWizard);
  tray.on('right-click', () => tray.popUpContextMenu(trayMenu()));
}

// ---------- IPC (every handler validates its arguments) ----------

let drag = null;

function registerIpc() {
  ipcMain.on('wizard:pick-file', () => pickFile());

  ipcMain.on('wizard:analyze-path', (_e, p) => {
    if (validAudioPath(p)) analyzeFile(p);
    else setMode('result', { error: 'That doesn’t look like an audio file I can read.' });
  });

  ipcMain.on('wizard:dismiss-bubble', () => {
    if (mode === 'result') setMode('idle');
    else if (mode === 'call-alert') {
      // Keep the purple highlight; just fold the speech bubble away.
      bubble = false;
      placeWizard();
      wizard.webContents.send('wizard:state', { mode: 'call-alert', bubble: false });
    }
  });

  ipcMain.on('wizard:vanished', () => {
    if (!wizardVisible && !callSession) {
      wizard.hide();
      mode = 'hidden';
    }
  });

  ipcMain.on('wizard:drag', (_e, phase, x, y) => {
    if (callSession || !['start', 'move', 'end'].includes(phase)) return;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    if (phase === 'start') drag = { x, y, anchor: { ...desktopAnchor } };
    else if (phase === 'move' && drag) {
      desktopAnchor = { right: drag.anchor.right + (x - drag.x), bottom: drag.anchor.bottom + (y - drag.y) };
      placeWizard();
    } else drag = null;
  });
}

// ---------- app lifecycle ----------

if (!app.requestSingleInstanceLock()) app.quit();

app.whenReady().then(() => {
  if (process.platform === 'darwin') app.dock.hide();
  desktopAnchor = defaultAnchor();
  createWizard();
  createOverlay();
  createTray();
  registerIpc();

  calls.on('call', onCallStarted);
  calls.on('move', onCallMoved);
  calls.on('ended', onCallEnded);
  calls.start();

  // Start with the wizard out so people see it on first launch.
  wizard.webContents.once('did-finish-load', () => {
    summon();
    // `npm start -- --simulate-call` runs the call flow without a real call.
    if (process.argv.includes('--simulate-call')) setTimeout(simulateCall, 1500);
  });
});

app.on('window-all-closed', (e) => e.preventDefault()); // lives in the menu bar
app.on('before-quit', () => calls.stop());
