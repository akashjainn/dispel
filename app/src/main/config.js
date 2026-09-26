// Server settings and the anonymous install id. Main process only: the API
// key never reaches the renderer (docs/INTERFACES.md).
//
// Settings come from app/config.local.json (gitignored; copy
// config.example.json), overridden by DISPEL_SERVER_URL / DISPEL_API_KEY.
// With no server URL the app keeps using the local mock.

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { app } = require('electron');

const LOCAL_CONFIG = path.join(__dirname, '..', '..', 'config.local.json');

function loadConfig() {
  let file = {};
  try {
    file = JSON.parse(fs.readFileSync(LOCAL_CONFIG, 'utf8'));
  } catch (err) {
    if (err.code !== 'ENOENT') console.error('[config] ignoring config.local.json:', err.message);
  }
  const serverUrl = (process.env.DISPEL_SERVER_URL ?? file.serverUrl ?? '').trim().replace(/\/+$/, '');
  const apiKey = (process.env.DISPEL_API_KEY ?? file.apiKey ?? '').trim();
  return { serverUrl: serverUrl || null, apiKey: apiKey || null };
}

// A random UUID made on first launch and kept in <userData>/client-id. No
// account and nothing personal: it only groups this install's checks on the
// server (GET /history). Deleting the file starts a fresh history.
let cachedId = null;
function clientId() {
  if (cachedId) return cachedId;
  const file = path.join(app.getPath('userData'), 'client-id');
  try {
    const saved = fs.readFileSync(file, 'utf8').trim();
    if (/^[0-9a-f-]{36}$/i.test(saved)) return (cachedId = saved);
  } catch {
    // first launch
  }
  cachedId = crypto.randomUUID();
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, cachedId + '\n');
  } catch (err) {
    console.error('[config] could not save client id:', err.message); // still works for this session
  }
  return cachedId;
}

module.exports = { loadConfig, clientId };
