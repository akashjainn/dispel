// Menu-bar wizard. Owns the tray, the wizard window, the call-highlight
// overlay, and the flow between them. The renderer only draws what it's told.

const path = require('node:path');
const fs = require('node:fs');
const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, dialog, screen, shell } = require('electron');

const analyzer = require('./analyzer');
const { logResult, logPath } = require('./results-log');
const { CallWatch } = require('./callwatch');
const { CHARACTERS, STYLES, loadPrefs, savePrefs } = require('./prefs');
const { Obliterator, COVERED_MS } = require('./obliterate');

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
let simWindow = null; // the demo's pretend call window (tray -> "Simulate a call")
const calls = new CallWatch();
const obliterator = new Obliterator(); // the hang-up spell's window

// Where the wizard's bottom-right corner sits on the desktop. Dragging moves it.
let desktopAnchor = null;
let wizardVisible = false; // desktop visibility, independent of call mode
let mode = 'hidden'; // hidden | idle | analyzing | result | call-watch | call-alert
let bubble = false;
let busy = false; // a file analysis is running
let callSession = null; // { id, app, bounds, canEnd, alerted, result, prompt, ending, wasVisible }
let guardEnabled = true;
let character = 'wizard'; // wizard | witch, loaded from prefs.json once the app is ready
let style = '2d'; // 2d (pixel art) | 3d (pre-rendered 3D sprites)

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
  wizard.loadFile(path.join(RENDERER, 'wizard.html'), { query: { character, style } }); // first frame is right
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
  bubble = ['analyzing', 'result', 'call-alert', 'learn', 'greet'].includes(next);
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

// Said on the way out of the hat; folded away after a few seconds.
const GREETINGS = [
  'Hi! Drop a voice clip on me and I’ll listen for signs it’s synthetic.',
  'I’m here. Drop an audio file on me, or click me to choose one.',
  'Got a voice message that feels off? Drop it on me.',
];
let greetTimer = null;

function summon() {
  wizardVisible = true;
  if (callSession) return; // call mode owns the wizard until the call ends
  setMode('greet', { appear: true, text: GREETINGS[Math.floor(Math.random() * GREETINGS.length)] });
  clearTimeout(greetTimer);
  greetTimer = setTimeout(() => {
    if (mode === 'greet' && wizardVisible && !callSession) setMode('idle');
  }, 5500);
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
    title: `Choose an audio file for the ${character}`,
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

  // MOCK: no audio is captured yet. The server (or the local mock) answers with
  // demo data: about 70% of calls land above the alert threshold.
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
  clearTimeout(s.fireTimer);
  clearTimeout(s.hangTimer);
  callSession = null;
  overlay.hide();
  closeSimWindow();
  if (s.ending && obliterator.active) {
    // Let the crystal shatter before the wizard heads back to the desktop.
    obliterator.shatter();
    obliterator.whenDone(() => {
      if (callSession) return; // a new call took over meanwhile
      setWizardLevel('floating');
      if (mode === 'call-alert') {
        wizardVisible = true;
        setMode('result', { message: 'I hung up the call.' });
      } else placeWizard();
    });
    return;
  }
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

// "Yes, hang up": the wizard pulls out its wand and casts (wizard.js). When
// the spell leaves the wand, a bolt hits the call window and turns it to
// crystal (obliterate.js); once it's covered, quit the call app behind it.
// If the call is still going after a few seconds (the app asked to confirm,
// or refused), say so.
function endCall() {
  const s = callSession;
  if (!s?.alerted || s.ending || !s.canEnd) return;
  s.ending = true;
  setCallPrompt('ending');
  // The demo's call window is ours, so the pieces can be made of it.
  simWindow?.webContents.capturePage().then(
    (img) => {
      s.snapshot = img.toDataURL();
    },
    () => {},
  );
  s.fireTimer = setTimeout(() => castSpell(s, null), 3000); // the spell never left the wand: hang up anyway
}

// from: the screen point where the spell left the wand, or null to skip the show.
function castSpell(s, from) {
  if (callSession !== s || !s.ending || s.cast) return;
  s.cast = true;
  clearTimeout(s.fireTimer);
  if (!from || !s.bounds) {
    hangUp(s);
    return;
  }
  obliterator.cast({ from, target: s.bounds, style, snapshot: s.snapshot });
  wizard.moveTop(); // the wizard stays in front of its spell
  s.hangTimer = setTimeout(() => hangUp(s), COVERED_MS);
}

function hangUp(s) {
  if (callSession !== s) return;
  s.endTimer = setTimeout(() => {
    if (callSession !== s) return;
    s.ending = false;
    obliterator.shatter();
    setCallPrompt('failed');
  }, 8000);
  calls.endCall();
}

function onEndResult(ok) {
  const s = callSession;
  if (!s?.ending || ok) return;
  clearTimeout(s.endTimer);
  s.ending = false;
  obliterator.shatter();
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
  const bounds = {
    x: workArea.x + Math.round((workArea.width - width) / 2),
    y: workArea.y + Math.round((workArea.height - height) / 2),
    width,
    height,
  };
  openSimWindow(bounds);
  calls.simulate(bounds);
}

// A pretend call window for the demo, so there's something on screen to
// watch, flag and hang up. Moving it moves the call; closing it hangs up.
function openSimWindow(bounds) {
  closeSimWindow();
  const win = new BrowserWindow({
    ...bounds,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    title: 'Demo call',
    backgroundColor: '#00000000',
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  simWindow = win;
  win.loadFile(path.join(RENDERER, 'call-sim.html'));
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e) => e.preventDefault());
  win.once('ready-to-show', () => win.show());
  win.on('move', () => calls.moveSimulated(win.getBounds()));
  win.on('closed', () => {
    if (simWindow !== win) return; // closed by closeSimWindow: the call is already over
    simWindow = null;
    if (calls.simulated) calls.endSimulated();
  });
}

function closeSimWindow() {
  const win = simWindow;
  simWindow = null;
  if (win && !win.isDestroyed()) win.close();
}

// ---------- tray ----------

// Wizard or witch, 2D or 3D. The renderer plays the transition; the choice is
// saved for the next launch.
function setLook(next) {
  const c = CHARACTERS.includes(next.character) ? next.character : character;
  const s = STYLES.includes(next.style) ? next.style : style;
  if (c === character && s === style) return;
  character = c;
  style = s;
  savePrefs({ ...loadPrefs(), character, style });
  wizard.webContents.send('wizard:look', { character, style });
  tray.setImage(trayIcon());
  tray.setToolTip(`Dispel ${character}`);
}

const otherCharacter = () => (character === 'wizard' ? 'witch' : 'wizard');

// Menu items for the look, shared by the right-click and menu-bar menus.
function lookMenuItems() {
  return [
    { label: `Turn into a ${otherCharacter()}`, click: () => setLook({ character: otherCharacter() }) },
    {
      label: '3D look',
      type: 'checkbox',
      checked: style === '3d',
      click: (item) => setLook({ style: item.checked ? '3d' : '2d' }),
    },
  ];
}

function trayIcon() {
  // The character's face from the first idle frame, sized for the menu bar.
  const k = style === '3d' ? 4 : 1; // the 3D sheets are 4x
  const sheetPath = style === '3d' ? path.join(ASSETS, '3d', `${character}-sprites.png`) : path.join(ASSETS, `${character}-sprites.png`);
  const sheet = nativeImage.createFromPath(sheetPath);
  const face = sheet.crop({ x: 20 * k, y: 16 * k, width: 48 * k, height: 48 * k });
  const icon = nativeImage.createEmpty();
  icon.addRepresentation({ scaleFactor: 1, buffer: face.resize({ width: 18, height: 18, quality: 'best' }).toPNG() });
  icon.addRepresentation({ scaleFactor: 2, buffer: face.resize({ width: 36, height: 36, quality: 'best' }).toPNG() });
  return icon;
}

function trayMenu() {
  return Menu.buildFromTemplate([
    { label: wizardVisible ? `Send ${character} away` : `Summon ${character}`, click: toggleWizard },
    { label: 'Check an audio file…', click: pickFile, enabled: !busy },
    { label: 'Learn about deepfakes', click: () => learn() },
    { type: 'separator' },
    ...lookMenuItems(),
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
  tray.setToolTip(`Dispel ${character}`);
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

  // The hang-up spell left the wand at (x, y) in the wizard window.
  ipcMain.on('wizard:blast-fire', (_e, x, y) => {
    const s = callSession;
    if (!s || !Number.isFinite(x) || !Number.isFinite(y)) return;
    const b = wizard.getBounds();
    if (x < 0 || y < 0 || x > b.width || y > b.height) return;
    castSpell(s, { x: b.x + x, y: b.y + y });
  });

  ipcMain.on('wizard:learn', (_e, topic) => learn(typeof topic === 'string' ? topic : undefined));

  // Right-click on the wizard (or witch).
  ipcMain.on('wizard:context-menu', () => {
    Menu.buildFromTemplate([
      { label: 'Check an audio file…', click: pickFile, enabled: !busy },
      { label: 'Learn about deepfakes', click: () => learn() },
      { type: 'separator' },
      ...lookMenuItems(),
      { type: 'separator' },
      { label: `Send ${character} away`, click: dismiss, enabled: !callSession },
    ]).popup({ window: wizard });
  });

  ipcMain.on('wizard:dismiss-bubble', () => {
    if (mode === 'result' || mode === 'learn' || mode === 'greet') {
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
  ({ character, style } = loadPrefs());
  createWizard();
  createOverlay();
  obliterator.create();
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
