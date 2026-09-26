// Fake-caller rig for demos. Runs on the "caller" laptop; an iPhone opens the
// control page on the same network and taps a button to:
//   1. dial the judge's laptop on Teams / FaceTime (Discord is dialed by hand)
//   2. play a caller's clip into the call (through BlackHole, the call app's mic)
//   3. optionally switch OBS to that caller's video scene (OBS Virtual Camera)
//
// Only what's in scenarios.local.json can be dialed or played; the phone sends
// ids, never URLs or paths. Every request needs the token printed at startup.
//
// Usage: npm start   (see README.md)

const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, execFile } = require('node:child_process');
const { obsRequests } = require('./obs');

const ROOT = __dirname;
const PORT = Number(process.env.PORT) || 8790;
const PLAYER = path.join(ROOT, 'bin', 'playto');
const CONFIG_FILE = fs.existsSync(path.join(ROOT, 'scenarios.local.json'))
  ? path.join(ROOT, 'scenarios.local.json')
  : path.join(ROOT, 'scenarios.example.json');

const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
const platforms = config.platforms || {};
const callers = new Map((config.callers || []).map((c) => [c.id, c]));

// Kept across restarts so the phone's home-screen app keeps working.
const TOKEN_FILE = path.join(ROOT, '.token');
if (!fs.existsSync(TOKEN_FILE)) fs.writeFileSync(TOKEN_FILE, crypto.randomBytes(6).toString('hex'), { mode: 0o600 });
const TOKEN = fs.readFileSync(TOKEN_FILE, 'utf8').trim();

// ---------- actions ----------

let playing = null; // { id, proc, startedAt, duration }
let lastError = null;

function run(cmd, args) {
  return new Promise((resolve, reject) =>
    execFile(cmd, args, { timeout: 10_000 }, (err, _out, stderr) => (err ? reject(new Error(stderr || err.message)) : resolve())),
  );
}

function dial(platformId, video) {
  const p = platforms[platformId];
  if (!p) throw new Error('unknown platform');
  const url = video ? p.dialVideo || p.dial : p.dial;
  if (!url) return { dialed: false, note: p.note || `Start the ${p.label} call by hand.` };
  return run('open', [url]).then(() => ({ dialed: true, note: p.note || null }));
}

function hangUp(platformId) {
  const p = platforms[platformId];
  if (!p?.app) throw new Error('no app to quit for that platform');
  stop();
  return run('osascript', ['-e', `tell application "${p.app.replace(/"/g, '')}" to quit`]);
}

async function setScene(scene, input) {
  if (!config.obs || !scene) return;
  const reqs = [['SetCurrentProgramScene', { sceneName: scene }]];
  if (input) reqs.push(['TriggerMediaInputAction', { inputName: input, mediaAction: 'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART' }]);
  await obsRequests(config.obs, reqs);
}

function idleScene() {
  setScene(config.obs?.idleScene).catch((err) => console.warn('[obs]', err.message));
}

function stop() {
  if (!playing) return;
  playing.proc.kill();
  playing = null;
  idleScene();
}

async function play(callerId, video) {
  const c = callers.get(callerId);
  if (!c) throw new Error('unknown caller');
  const file = path.resolve(ROOT, c.audio);
  if (!fs.existsSync(file)) throw new Error(`missing clip: ${c.audio}`);
  stop();
  if (video && c.video) await setScene(c.video.scene, c.video.input); // video first, so lips and voice start together

  const args = ['--device', config.audioDevice || 'BlackHole 2ch'];
  if (config.monitor) args.push('--monitor');
  const proc = spawn(PLAYER, [...args, file], { stdio: ['ignore', 'pipe', 'inherit'] });
  const entry = { id: c.id, proc, startedAt: Date.now(), duration: null };
  playing = entry;

  const started = await new Promise((resolve) => {
    let buf = '';
    proc.stdout.on('data', (chunk) => {
      buf += chunk;
      for (const line of buf.split('\n').slice(0, -1)) {
        let msg;
        try {
          msg = JSON.parse(line);
        } catch {
          continue;
        }
        if ('ok' in msg) resolve(msg);
        if (msg.done && playing === entry) {
          playing = null;
          idleScene();
        }
      }
      buf = buf.slice(buf.lastIndexOf('\n') + 1);
    });
    proc.on('exit', () => {
      resolve({ ok: false, error: 'player exited' });
      if (playing === entry) playing = null;
    });
  });
  if (!started.ok) {
    if (playing === entry) playing = null;
    const devices = started.devices?.length ? ` Output devices: ${started.devices.join(', ')}.` : '';
    throw new Error(`${started.error}.${devices}`);
  }
  entry.duration = started.duration;
  return { duration: started.duration };
}

function status() {
  return {
    playing: playing && { id: playing.id, elapsed: (Date.now() - playing.startedAt) / 1000, duration: playing.duration },
    lastError,
  };
}

function publicConfig() {
  return {
    platforms: Object.entries(platforms).map(([id, p]) => ({
      id,
      label: p.label,
      canDial: Boolean(p.dial),
      canHangUp: Boolean(p.app),
      note: p.note || null,
    })),
    callers: [...callers.values()].map((c) => ({
      id: c.id,
      label: c.label,
      subtitle: c.subtitle || '',
      hasVideo: Boolean(c.video),
      ready: fs.existsSync(path.resolve(ROOT, c.audio)),
    })),
    video: Boolean(config.obs),
  };
}

// ---------- HTTP ----------

const STATIC = {
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript'],
  '/style.css': ['style.css', 'text/css'],
  '/manifest.webmanifest': ['manifest.webmanifest', 'application/manifest+json'],
  '/icon.png': ['icon.png', 'image/png'],
};

function send(res, code, body) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

function readJson(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (c) => {
      raw += c;
      if (raw.length > 10_000) req.destroy();
    });
    req.on('end', () => {
      try {
        resolve(JSON.parse(raw || '{}'));
      } catch {
        resolve({});
      }
    });
  });
}

const ACTIONS = {
  'POST /api/dial': (b) => dial(String(b.platform), Boolean(b.video)),
  'POST /api/play': (b) => play(String(b.caller), Boolean(b.video)),
  'POST /api/stop': () => stop(),
  'POST /api/hangup': (b) => hangUp(String(b.platform)),
  'GET /api/config': () => publicConfig(),
  'GET /api/status': () => status(),
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const file = req.method === 'GET' && STATIC[url.pathname];
  if (file) {
    const p = path.join(ROOT, 'public', file[0]);
    if (!fs.existsSync(p)) return send(res, 404, { error: 'not found' });
    res.writeHead(200, { 'Content-Type': file[1] });
    return fs.createReadStream(p).pipe(res);
  }
  const action = ACTIONS[`${req.method} ${url.pathname}`];
  if (!action) return send(res, 404, { error: 'not found' });
  const given = Buffer.from(String(req.headers['x-token'] || ''));
  if (given.length !== TOKEN.length || !crypto.timingSafeEqual(given, Buffer.from(TOKEN))) {
    return send(res, 401, { error: 'bad token' });
  }
  try {
    const body = req.method === 'POST' ? await readJson(req) : {};
    const out = await action(body);
    if (req.method === 'POST') lastError = null;
    send(res, 200, out ?? { ok: true });
  } catch (err) {
    lastError = err.message;
    console.warn(`[${url.pathname}]`, err.message);
    send(res, 400, { error: err.message });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Caller rig using ${path.basename(CONFIG_FILE)}. Open on the phone:`);
  for (const addrs of Object.values(os.networkInterfaces())) {
    for (const a of addrs || []) {
      if (a.family === 'IPv4' && !a.internal) console.log(`  http://${a.address}:${PORT}/?t=${TOKEN}`);
    }
  }
  if (!fs.existsSync(PLAYER)) console.warn('bin/playto is missing: run `npm start` (it builds it) on macOS.');
});
