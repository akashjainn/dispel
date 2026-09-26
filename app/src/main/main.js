// Menu-bar wizard. Owns the tray, the wizard window, the call-highlight
// overlay, and the flow between them. The renderer only draws what it's told.

const path = require('node:path');
const fs = require('node:fs');
const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, dialog, screen, shell, globalShortcut } = require('electron');

const analyzer = require('./analyzer');
const { logResult, logPath } = require('./results-log');
const { CallWatch } = require('./callwatch');
const { withCallClip, LISTEN_SECONDS } = require('./callcapture');
const { loadConfig } = require('./config');
const { loadSettings, saveSettings, notifyInfo } = require('./settings');
const { sendText, alertText, testText } = require('./notify');

const ROOT = path.join(__dirname, '..', '..');
const ASSETS = path.join(ROOT, 'Assets');
const RENDERER = path.join(ROOT, 'src', 'renderer');

const AUDIO_EXTS = new Set(['.wav', '.mp3', '.m4a', '.mp4', '.aac', '.ogg', '.oga', '.opus', '.flac', '.webm', '.mov']);
const MAX_FILE_BYTES = 500 * 1024 * 1024;

// Window sizes (px). The wizard stage is 160x240 (the 80x120 canvas at 2x);
// the speech bubble sits to its left.
const SIZE = {
  plain: { width: 160, height: 240 },
  small: { width: 80, height: 120 }, // gray "watching" wizard in a call's corner (0.5 scale in wizard.css)
  bubble: { width: 400, height: 380 }, // tall enough for the call alert's buttons
};
const CALL_INSET = 12; // gap between the wizard and the call window's corner
const EDGE = 40; // gap from the screen edge for the default desktop spot
const LISTEN_KEY = 'CommandOrControl+Shift+L'; // "listen to this call", only while a call is on

let tray = null;
let wizard = null;
let overlay = null;
const calls = new CallWatch();

// Where the wizard's bottom-right corner sits on the desktop. Dragging moves it.
let desktopAnchor = null;
let wizardVisible = false; // desktop visibility, independent of call mode
let mode = 'hidden'; // hidden | idle | analyzing | result | call-watch | call-listen | call-alert
let bubble = false;
let busy = false; // a file analysis is running
let callSession = null; // { id, app, prefixes, bounds, canEnd, listening, alerted, result, prompt, ending, wasVisible }
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

// Where the wizard goes during a call, inside the call window. The small gray
// watching wizard sits in the bottom-right corner; it's click-through (see
// placeWizard), so the call's own buttons under it still work. Anything
// clickable (the warning bubble with its buttons) goes in the top-right corner
// instead, away from the End button that Zoom and FaceTime put at the bottom.
const TITLE_BAR = 32;
function callPlacement(bounds, size) {
  if (!bounds) return defaultAnchor();
  const wa = screen.getDisplayMatching(bounds).workArea;
  const right = Math.min(bounds.x + bounds.width, wa.x + wa.width) - CALL_INSET;
  if (mode === 'call-watch') {
    return { right, bottom: Math.min(bounds.y + bounds.height, wa.y + wa.height) - CALL_INSET };
  }
  const top = Math.max(bounds.y, wa.y) + TITLE_BAR;
  return { right, bottom: top + size.height };
}

function placeWizard() {
  const size = bubble ? SIZE.bubble : mode === 'call-watch' ? SIZE.small : SIZE.plain;
  const a = callSession ? callPlacement(callSession.bounds, size) : desktopAnchor;
  // The small gray wizard watching a call is passive: clicks go straight
  // through it to whatever is underneath (the call's buttons, other windows).
  wizard.setIgnoreMouseEvents(mode === 'call-watch');
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
  bubble = ['analyzing', 'result', 'call-listen', 'call-alert', 'learn'].includes(next);
  if (next === 'hidden') {
    wizard.webContents.send('wizard:state', { mode: 'hidden' });
    return;
  }
  setWizardLevel(callSession ? 'screen-saver' : 'floating');
  placeWizard();
  wizard.webContents.send('wizard:state', { mode: next, ...payload });
  if (!wizard.isVisible() && !hiddenForFocus()) wizard.showInactive();
}

// During a call, the wizard and the ring only show while the call app is in
// front. Switch to another app and they get out of the way.
function hiddenForFocus() {
  return Boolean(callSession) && !callSession.front;
}

function applyCallFocus() {
  if (hiddenForFocus()) {
    wizard.hide();
    overlay.hide();
    return;
  }
  if (mode !== 'hidden' && !wizard.isVisible()) wizard.showInactive();
  if (callSession && (callSession.alerted || callSession.verified)) showOverlay(callSession.bounds);
}

const OVERLAY_PAD = 24; // must match the ring's inset + border in overlay.html

// Ring drawn just outside the call window, never over its content.
// tone: "alert" (purple, pulsing) or "real" (green, steady). The green look is
// injected CSS, so the overlay page itself never runs scripts.
const REAL_RING_CSS = `.glow {
  border-color: #22c55e !important;
  box-shadow: 0 0 14px 3px rgba(34, 197, 94, 0.75) !important;
  animation: none !important;
  opacity: 0.85;
}`;
let overlayTone = 'alert';
let overlayCssKey = null;
async function setOverlayTone(tone) {
  if (tone === overlayTone) return;
  overlayTone = tone;
  const wc = overlay.webContents;
  if (overlayCssKey) await wc.removeInsertedCSS(overlayCssKey).catch(() => {});
  overlayCssKey = tone === 'real' ? await wc.insertCSS(REAL_RING_CSS).catch(() => null) : null;
}

function showOverlay(bounds, tone) {
  if (tone) setOverlayTone(tone);
  if (!bounds || hiddenForFocus()) {
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
    const result = await analyzer.analyze('file', filePath);
    logResult({ source: 'file', name, result });
    if (callAlertShowing()) return; // don't cover a deepfake warning; it's in the log
    setMode('result', { name, result });
  } catch (err) {
    console.error('[analyze]', err);
    if (!callAlertShowing()) setMode('result', { name, error: err.userMessage || 'I couldn’t read that file.' });
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

// ---------- learn mode ----------

const LESSON_TOPICS = new Set(['deepfake', 'scams', 'protect']); // keys of LESSONS in lessons.js

// The wizard explains deepfakes, scams and how to stay safe (renderer pages
// through the lesson). Doesn't interrupt a file check or a call warning.
function learn(topic) {
  if (mode === 'analyzing' || callAlertShowing()) return;
  wizardVisible = true;
  setMode('learn', { topic: LESSON_TOPICS.has(topic) ? topic : null });
}

// ---------- call mode ----------

function callAlertShowing() {
  return Boolean(callSession?.alerted) && mode === 'call-alert' && bubble;
}

// Put the wizard back in the call's state (after a file check or a message).
// Everything the warning bubble shows, including the notify button.
function alertPayload(s) {
  return { app: s.app, result: s.result, prompt: s.prompt, notify: { ...notifyInfo(), status: s.notifyStatus } };
}

function showCallMode() {
  const s = callSession;
  if (s.alerted) setMode('call-alert', alertPayload(s));
  else setMode('call-watch', { app: s.app });
}

// prompt: ask | ending | failed | manual (see the call-alert state in wizard.js)
function setCallPrompt(prompt) {
  const s = callSession;
  s.prompt = prompt;
  setMode('call-alert', alertPayload(s));
}

// "Notify trusted contact" / "Notify my manager": text them from Messages.
// Opens Settings instead if nobody is set up yet.
async function notifyContact() {
  const s = callSession;
  if (!s?.alerted || s.notifyStatus?.state === 'sending') return;
  const settings = loadSettings();
  const info = notifyInfo(settings);
  if (!info.configured) {
    openSettings();
    return;
  }
  const refresh = () => callSession === s && mode === 'call-alert' && setMode('call-alert', alertPayload(s));
  s.notifyStatus = { state: 'sending', text: `Texting ${info.who}…` };
  refresh();
  const res = await sendText(settings.contact.handle, alertText({ mode: settings.mode, app: s.app, result: s.result }));
  console.log('[notify]', res.ok ? 'sent' : `failed: ${res.error}`);
  s.notifyStatus = res.ok ? { state: 'sent', text: `Texted ${info.who}.` } : { state: 'failed', text: res.error };
  refresh();
}

// ---------- settings window ----------

let settingsWin = null;
function openSettings() {
  if (settingsWin && !settingsWin.isDestroyed()) {
    settingsWin.show();
    settingsWin.focus();
    return;
  }
  settingsWin = new BrowserWindow({
    width: 420,
    height: 480,
    resizable: false,
    minimizable: false,
    fullscreenable: false,
    title: 'Dispel Settings',
    backgroundColor: '#fffaf0',
    webPreferences: {
      preload: path.join(ROOT, 'src', 'preload', 'settings.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  settingsWin.setAlwaysOnTop(true, 'screen-saver'); // above the wizard and full-screen calls
  settingsWin.loadFile(path.join(RENDERER, 'settings.html'));
  settingsWin.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  settingsWin.webContents.on('will-navigate', (e) => e.preventDefault());
  app.focus({ steal: true });
  settingsWin.on('closed', () => {
    settingsWin = null;
    // The notify button's label depends on the settings.
    if (callSession?.alerted && mode === 'call-alert') setMode('call-alert', alertPayload(callSession));
  });
}

function onCallStarted({ app: callApp, bounds, canEnd, front, prefixes }) {
  if (!guardEnabled) return;
  callSession = {
    id: Date.now(),
    app: callApp,
    prefixes,
    bounds,
    canEnd,
    front,
    listening: false,
    alerted: false,
    verified: false, // voice scored likely real: green ring, wizard stays small and gray
    result: null,
    prompt: null,
    ending: false,
    wasVisible: wizardVisible,
  };
  console.log('[call] started:', callApp, bounds);
  globalShortcut.register(LISTEN_KEY, listenToCall);
  const fileBubbleUp = mode === 'analyzing' || mode === 'result';
  if (fileBubbleUp) {
    setWizardLevel('screen-saver');
    placeWizard(); // move to the call's corner; the gray state shows once it's dismissed
  } else setMode('call-listen', { ...listenPayload(callSession, 'offer'), appear: !wizard.isVisible() });
}

function listenPayload(s, step, extra = {}) {
  return { app: s.app, step, seconds: LISTEN_SECONDS, ...extra };
}

// The user asked the wizard to listen (bubble button, tray, or the shortcut).
// Records a few seconds of the call, sends it to our server, and shows the
// verdict. Nothing is recorded unless the user asks (AGENTS.md).
async function listenToCall() {
  const s = callSession;
  if (!s || s.listening || s.ending) return;
  s.listening = true;
  try {
    let result;
    if (!analyzer.usesServer()) {
      // Local mock ("Results from" in the tray): no recording at all.
      setMode('call-listen', listenPayload(s, 'listening'));
      result = await analyzer.analyze('call');
    } else {
      if (!loadConfig().serverUrl) await analyzer.analyze('call'); // throws "not connected" before recording
      setMode('call-listen', listenPayload(s, 'listening'));
      result = await withCallClip({ app: s.app, prefixes: s.prefixes }, (clip) => {
        if (callSession === s) setMode('call-listen', listenPayload(s, 'checking'));
        return analyzer.analyze('call', clip);
      });
    }
    if (callSession !== s) return; // call ended meanwhile
    logResult({ source: 'call', name: s.app, result });
    applyCallResult(s, result);
  } catch (err) {
    console.error('[listen]', err.message);
    if (callSession === s) setMode('call-listen', listenPayload(s, 'error', { error: err.userMessage || 'I couldn’t check the call.' }));
  } finally {
    s.listening = false;
  }
}

function applyCallResult(s, result) {
  s.result = result;
  s.alerted = result.overall.probability >= analyzer.SYNTHETIC_AT;
  s.verified = result.overall.verdict === 'likely_real';
  if (s.alerted) {
    s.prompt = null;
    showOverlay(s.bounds, 'alert');
    setCallPrompt(s.canEnd ? 'ask' : 'manual'); // takes over any file bubble: it's urgent
    return;
  }
  if (s.verified) showOverlay(s.bounds, 'real');
  else overlay.hide(); // inconclusive: no ring
  setMode('call-listen', listenPayload(s, 'result', { result }));
}

function onCallMoved({ bounds, front }) {
  if (!callSession) return;
  callSession.bounds = bounds;
  callSession.front = front;
  placeWizard();
  applyCallFocus();
}

function onCallEnded() {
  if (!callSession) return;
  const s = callSession;
  console.log('[call] ended:', s.app);
  clearTimeout(s.endTimer);
  callSession = null;
  globalShortcut.unregister(LISTEN_KEY);
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
    { label: 'Learn about deepfakes', click: () => learn() },
    { label: 'Settings…', click: openSettings },
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
    {
      label: `Listen to this call (${LISTEN_SECONDS} s)`,
      accelerator: LISTEN_KEY,
      enabled: Boolean(callSession) && !callSession.listening,
      click: listenToCall,
    },
    { label: callSession ? 'End simulated call' : 'Simulate a call (demo)', click: simulateCall },
    {
      label: 'Results from',
      submenu: [
        ['server', 'Server'],
        ['real', 'Mock: likely real'],
        ['synthetic', 'Mock: likely synthetic'],
      ].map(([v, label]) => ({
        label,
        type: 'radio',
        checked: analyzer.getResultSource() === v,
        click: () => analyzer.setResultSource(v),
      })),
    },
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
  ipcMain.on('wizard:listen', () => listenToCall());
  ipcMain.on('wizard:notify', () => notifyContact());

  // Settings IPC answers only the settings window.
  const fromSettings = (e) => settingsWin && !settingsWin.isDestroyed() && e.sender === settingsWin.webContents;
  ipcMain.handle('settings:get', (e) => (fromSettings(e) ? loadSettings() : null));
  ipcMain.handle('settings:save', (e, s) => (fromSettings(e) ? saveSettings(s) : { ok: false, error: 'denied' }));
  ipcMain.handle('settings:test', (e) => {
    if (!fromSettings(e)) return { ok: false, error: 'denied' };
    const s = loadSettings();
    return sendText(s.contact.handle, testText(s.mode));
  });

  ipcMain.on('wizard:learn', (_e, topic) => learn(typeof topic === 'string' ? topic : undefined));

  // Right-click on the wizard.
  ipcMain.on('wizard:context-menu', () => {
    Menu.buildFromTemplate([
      { label: 'Check an audio file…', click: pickFile, enabled: !busy },
      { label: 'Learn about deepfakes', click: () => learn() },
    { label: 'Settings…', click: openSettings },
      { type: 'separator' },
      { label: 'Send wizard away', click: dismiss, enabled: !callSession },
    ]).popup({ window: wizard });
  });

  ipcMain.on('wizard:dismiss-bubble', () => {
    if (mode === 'result' || mode === 'learn' || mode === 'call-listen') {
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

  // `npm start -- --simulate-call` runs the call flow with a fake call and
  // ignores real ones, so a demo can't be hijacked by an actual call.
  const simulate = process.argv.includes('--simulate-call');

  // Start with the wizard out so people see it on first launch. Call watching
  // starts only once the page can draw, so a call that's already running when
  // the app opens still gets the call-mode wizard.
  wizard.webContents.once('did-finish-load', () => {
    summon();
    if (simulate) setTimeout(simulateCall, 1500);
    else calls.start();
  });
});

app.on('window-all-closed', (e) => e.preventDefault()); // lives in the menu bar
app.on('before-quit', () => calls.stop());
app.on('will-quit', () => globalShortcut.unregisterAll());
