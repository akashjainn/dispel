// Minimal obs-websocket v5 client (OBS 28+: Tools → WebSocket Server Settings).
// Opens a connection per request batch; enough for switching scenes on a tap.

const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const sha256b64 = (s) => crypto.createHash('sha256').update(s).digest('base64');
const ALREADY_EXISTS = 601; // obs-websocket RequestStatus.ResourceAlreadyExists

// With no password in our config, use the one OBS generated for itself (this
// Mac's OBS settings), so it never has to be copied into the repo folder.
function obsPassword(configured) {
  if (configured) return configured;
  const p = path.join(os.homedir(), 'Library/Application Support/obs-studio/plugin_config/obs-websocket/config.json');
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8')).server_password || '';
  } catch {
    return '';
  }
}

// requests: [[requestType, requestData, { allowExisting }], ...], sent in order.
// Resolves with each request's responseData (null for an allowed "already exists").
function obsRequests({ url = 'ws://127.0.0.1:4455', password = '' }, requests) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const results = new Array(requests.length).fill(null);
    let left = requests.length;
    const timer = setTimeout(() => finish(new Error('OBS did not answer (is its WebSocket server on?)')), 8000);
    let done = false;
    function finish(err) {
      if (done) return; // ws.close() can fire onerror again
      done = true;
      clearTimeout(timer);
      ws.close();
      err ? reject(err) : resolve(results);
    }
    ws.onerror = () => finish(new Error(`can't reach OBS at ${url} (open OBS; Tools → WebSocket Server Settings → Enable)`));
    ws.onmessage = ({ data }) => {
      const { op, d } = JSON.parse(data);
      if (op === 0) {
        // Hello: identify, with auth if OBS asks for it.
        const identify = { rpcVersion: 1 };
        if (d.authentication) {
          const secret = sha256b64(obsPassword(password) + d.authentication.salt);
          identify.authentication = sha256b64(secret + d.authentication.challenge);
        }
        ws.send(JSON.stringify({ op: 1, d: identify }));
      } else if (op === 2) {
        if (!requests.length) return finish();
        requests.forEach(([requestType, requestData], i) => {
          ws.send(JSON.stringify({ op: 6, d: { requestType, requestId: String(i), requestData } }));
        });
      } else if (op === 7) {
        const i = Number(d.requestId);
        const { result, code, comment } = d.requestStatus;
        if (!result && !(code === ALREADY_EXISTS && requests[i][2]?.allowExisting)) {
          return finish(new Error(`OBS ${requests[i][0]}: ${comment || code}`));
        }
        results[i] = d.responseData ?? null;
        if (--left === 0) finish();
      }
    };
  });
}

module.exports = { obsRequests };
