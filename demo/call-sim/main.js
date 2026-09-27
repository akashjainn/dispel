// Fake phone-call simulator for demos, on the same laptop as the Dispel wizard.
// A window "rings"; on Accept the page holds the mic (so the wizard's callwatch
// sees a call from this app's bundle ID) and plays a clip from clips/. The
// wizard taps this app's audio and gives its verdict; "Show answers" reveals the key.
//
// Clips: clips/real/*, clips/synthetic/* (the answer key), or clips/* (unlabeled).
// Nothing is recorded or sent anywhere.
//
// Usage: npm start (packages and opens "Call Simulator.app"; see README.md)

const { app, BrowserWindow, ipcMain, shell, systemPreferences, session } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const AUDIO = /\.(wav|mp3|m4a|aac|flac|ogg|webm|aiff?)$/i;
const LABELS = ['real', 'synthetic'];

// Dev: next to this file. Packaged: the .app sits in demo/call-sim/out/<name>-darwin-<arch>/,
// so walk up from it to the source folder's clips/.
function findClipsDir() {
  if (process.env.CALLSIM_CLIPS) return path.resolve(process.env.CALLSIM_CLIPS);
  let dir = app.isPackaged ? process.resourcesPath : __dirname;
  for (let i = 0; i < 8; i++) {
    if (fs.existsSync(path.join(dir, 'clips', 'README.md'))) return path.join(dir, 'clips');
    dir = path.dirname(dir);
  }
  return path.join(app.getPath('userData'), 'clips');
}
const CLIPS = findClipsDir();

function audioIn(dir) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true })
      .filter((e) => e.isFile() && AUDIO.test(e.name))
      .map((e) => e.name)
      .sort();
  } catch {
    return [];
  }
}

function listClips() {
  const out = audioIn(CLIPS).map((f) => ({ file: f, label: null }));
  for (const label of LABELS) {
    for (const f of audioIn(path.join(CLIPS, label))) out.push({ file: `${label}/${f}`, label });
  }
  return out.map((c) => ({ ...c, src: pathToFileURL(path.join(CLIPS, c.file)).href }));
}

// Copies dropped files into clips/<label>/, never overwriting one that's there.
function addClips(paths, label) {
  const dest = path.join(CLIPS, LABELS.includes(label) ? label : '');
  for (const p of paths) {
    if (!AUDIO.test(p) || !fs.statSync(p).isFile()) continue;
    const { name, ext } = path.parse(p);
    let target = path.join(dest, name + ext);
    for (let n = 2; fs.existsSync(target); n++) target = path.join(dest, `${name} ${n}${ext}`);
    fs.copyFileSync(p, target);
  }
  return listClips();
}

let win = null;

function createWindow() {
  // The window is the phone: frameless and transparent outside its rounded corners.
  // Drag it by the bezel or status bar; ⌘W / ⌘Q close it.
  win = new BrowserWindow({
    width: 330,
    height: 690,
    title: 'Call Simulator',
    frame: false,
    transparent: true,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    hasShadow: true,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'src', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, 'src', 'index.html'));
}

// Tell the page when clips/ changes, so adding a file in Finder shows up without a reload.
function watchClips() {
  let pending = null;
  const changed = () => {
    clearTimeout(pending);
    pending = setTimeout(() => win?.webContents.send('clips-changed'), 200);
  };
  for (const dir of [CLIPS, ...LABELS.map((l) => path.join(CLIPS, l))]) {
    try { fs.watch(dir, changed); } catch {}
  }
}

ipcMain.handle('clips:list', () => listClips());
ipcMain.handle('clips:add', (_e, paths, label) => addClips(paths, label));
ipcMain.handle('clips:open', () => shell.openPath(CLIPS));
ipcMain.handle('mic:ask', async () =>
  process.platform !== 'darwin' || systemPreferences.getMediaAccessStatus('microphone') === 'granted'
    || systemPreferences.askForMediaAccess('microphone'),
);

app.setName('Call Simulator');
app.whenReady().then(() => {
  for (const label of LABELS) fs.mkdirSync(path.join(CLIPS, label), { recursive: true });
  // Only the mic (for the call) and nothing else.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === 'media'));
  createWindow();
  watchClips();

  // `--smoke`: load the page, check the bridge and clip list, then quit.
  if (process.argv.includes('--smoke')) {
    win.webContents.once('did-finish-load', async () => {
      const n = await win.webContents.executeJavaScript('window.callsim.list().then((c) => c.length)');
      console.log(`smoke ok: ${n} clip(s) in ${CLIPS}`);
      if (process.env.CALLSIM_SHOT) {
        if (process.env.CALLSIM_SHOT_JS) await win.webContents.executeJavaScript(process.env.CALLSIM_SHOT_JS);
        await new Promise((r) => setTimeout(r, 400));
        fs.writeFileSync(process.env.CALLSIM_SHOT, (await win.webContents.capturePage()).toPNG());
      }
      app.exit(0);
    });
  }
});
app.on('window-all-closed', () => app.quit());
