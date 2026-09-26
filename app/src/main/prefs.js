// Per-install preferences in <userData>/prefs.json. A missing or broken file
// means the defaults; a failed save is logged and the app keeps going.

const fs = require('node:fs');
const path = require('node:path');
const { app } = require('electron');

// Both characters share one frame layout (see Assets/ and sprites.js). Each
// has a pixel-art look (2d) and a ray-traced voxel look (3d, Assets/3d/).
const CHARACTERS = ['wizard', 'witch'];
const STYLES = ['2d', '3d'];
const DEFAULTS = { character: 'wizard', style: '2d' };

const prefsPath = () => path.join(app.getPath('userData'), 'prefs.json');

function loadPrefs() {
  let saved = {};
  try {
    saved = JSON.parse(fs.readFileSync(prefsPath(), 'utf8'));
  } catch (err) {
    if (err.code !== 'ENOENT') console.error('[prefs] ignoring prefs.json:', err.message);
  }
  return {
    character: CHARACTERS.includes(saved?.character) ? saved.character : DEFAULTS.character,
    style: STYLES.includes(saved?.style) ? saved.style : DEFAULTS.style,
  };
}

function savePrefs(prefs) {
  const file = prefsPath();
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(`${file}.tmp`, JSON.stringify(prefs, null, 2) + '\n');
    fs.renameSync(`${file}.tmp`, file); // never leave a half-written file behind
  } catch (err) {
    console.error('[prefs] could not save:', err.message);
  }
}

module.exports = { CHARACTERS, STYLES, loadPrefs, savePrefs };
