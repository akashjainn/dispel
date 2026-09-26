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

// Window sizes (px). The wizard stage is 160x240 (the 80x120 canvas at 2x);
// the speech bubble sits to its left.
const SIZE = {
  plain: { width: 160, height: 240 },
  bubble: { width: 400, height: 290 }, // taller: the call alert has yes/no buttons
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
let callSession = null; // { id, app, bounds, canEnd, alerted, result, prompt, ending, wasVisible }
let guardEnabled = true;

// ---------- windows ----------

function createWizard() {
  wizard = new BrowserWindow({
    ...SIZE.plain,
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
  setWizardLevel('floating');
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
  const size = bubble ? SIZE.bubble : SIZE.plain;
  const a = currentAnchor();
  wizard.setBounds({
    x: Math.round(a.right - size.width),
    y: Math.round(a.bottom - size.height),
    width: size.width,
    height: size.height,
  });
}

// On the desktop the wizard floats above normal windows, like a tool palette,
// so files dragged from Finder can land on it. During a call it goes to the
// top level so it shows over a full-screen call and above the purple ring.
let wizardLevel = null;
function setWizardLevel(level) {
  if (level === wizardLevel) return;
  wizardLevel = level;
  wizard.setAlwaysOnTop(true, level);
}

function setMode(next, payload = {}) {
  mode = next;
  bubble = ['analyzing', 'result', 'call-alert'].includes(next);
  if (next === 'hidden') {
    wizard.webContents.send('wizard:state', { mode: 'hidden' });
    return;
  }
  setWizardLevel(callSession ? 'screen-saver' : 'floating');
  placeWizard();
  wizard.webContents.send('wizard:state', { mode: next, ...payload });
  if (!wizard.isVisible()) wizard.showInactive();
}

const OVERLAY_PAD = 24; // must match the ring's inset + border in overlay.html

// Purple ring drawn just outside the call window, never over its content.
function showOverlay(bounds) {
  if (!bounds) {
    overlay.hide(); // minimized or on another Space
    return;
  }
  overlay.setBounds({
    x: bounds.x - OVERLAY_PAD,
    y: bounds.y - OVERLAY_PAD,
    width: bounds.width + OVERLAY_PAD * 2,
    height: bounds.height + OVERLAY_PAD * 2,
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
  if (busy) return;
  busy = true;
  const name = path.basename(filePath);
  wizardVisible = true;
  setMode('analyzing', { name });
  try {
    const result = await analyzer.analyze('file');
    logResult({ source: 'file', name, result });
    if (callAlertShowing()) return; // don't cover a deepfake warning; it's in the log
    setMode('result', { name, result });
  } catch (err) {
    console.error('[analyze]', err);
    if (!callAlertShowing()) setMode('result', { name, error: 'I couldn’t read that file.' });
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

function callAlertShowing() {
  return Boolean(callSession?.alerted) && mode === 'call-alert' && bubble;
}

// Put the wizard back in the call's state (after a file check or a message).
function showCallMode() {
  const s = callSession;
  if (s.alerted) setMode('call-alert', { app: s.app, result: s.result, prompt: s.prompt });
  else setMode('call-watch', { app: s.app });
}

// prompt: ask | ending | failed | manual (see the call-alert state in wizard.js)
function setCallPrompt(prompt) {
  const s = callSession;
  s.prompt = prompt;
  setMode('call-alert', { app: s.app, result: s.result, prompt });
}

async function onCallStarted({ app: callApp, bounds, canEnd }) {
  if (!guardEnabled) return;
  const session = {
    id: Date.now(),
    app: callApp,
    bounds,
    canEnd,
    alerted: false,
    result: null,
    prompt: null,
    ending: false,
    wasVisible: wizardVisible,
  };
  callSession = session;
  console.log('[call] started:', callApp, bounds);
  const fileBubbleUp = mode === 'analyzing' || mode === 'result';
  if (fileBubbleUp) {
    setWizardLevel('screen-saver');
    placeWizard(); // move to the call's corner; the gray state shows once it's dismissed
  } else setMode('call-watch', { app: callApp, appear: !wizard.isVisible() });

  // MOCK: no audio is captured yet. We wait out the mock latency and use the
  // mock score, which always lands above the alert threshold.
  const result = await analyzer.analyze('call');
  if (callSession !== session) return; // call ended or restarted meanwhile
  logResult({ source: 'call', name: callApp, result });
  if (result.overall.probability >= analyzer.SYNTHETIC_AT) {
    session.alerted = true;
    session.result = result;
    showOverlay(session.bounds);
    setCallPrompt(session.canEnd ? 'ask' : 'manual'); // takes over any file bubble: it's urgent
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
  const s = callSession;
  console.log('[call] ended:', s.app);
  clearTimeout(s.endTimer);
  callSession = null;
  overlay.hide();
  setWizardLevel('floating');
  if (s.ending) {
    wizardVisible = true;
    setMode('result', { message: 'I hung up the call.' });
  } else if (mode === 'analyzing' || mode === 'result') {
    wizardVisible = true;
    placeWizard(); // keep the file bubble, back at the desktop spot
  } else if (s.wasVisible || wizardVisible) setMode('idle');
  else {
    wizard.hide();
    mode = 'hidden';
  }
}

// "Yes, hang up": quit the call app. If the call is still going after a few
// seconds (the app asked to confirm, or refused), say so.
function endCall() {
  const s = callSession;
  if (!s?.alerted || s.ending || !s.canEnd) return;
  s.ending = true;
  setCallPrompt('ending');
  calls.endCall();
  s.endTimer = setTimeout(() => {
    if (callSession !== s) return;
    s.ending = false;
    setCallPrompt('failed');
  }, 8000);
}

function onEndResult(ok) {
  const s = callSession;
  if (!s?.ending || ok) return;
  clearTimeout(s.endTimer);
  s.ending = false;
  setCallPrompt('failed');
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
    { label: 'Check an audio file…', click: pickFile, enabled: !busy },
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
  // Audio files can also be dropped on the menu-bar icon (macOS).
  tray.on('drop-files', (_e, files) => {
    const file = files.find(validAudioPath);
    if (file) analyzeFile(file);
    else setMode('result', { error: 'That doesn’t look like an audio file I can read.' });
  });
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

  ipcMain.on('wizard:end-call', () => endCall());

  ipcMain.on('wizard:dismiss-bubble', () => {
    if (mode === 'result') {
      if (callSession) showCallMode();
      else setMode('idle');
    } else if (mode === 'call-alert') {
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
  calls.on('end-result', onEndResult);
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
