// Minimal obs-websocket v5 client (OBS 28+: Tools → WebSocket Server Settings).
// Opens a connection per request batch; enough for switching scenes on a tap.

const crypto = require('node:crypto');

const sha256b64 = (s) => crypto.createHash('sha256').update(s).digest('base64');

// requests: [[requestType, requestData], ...], run in order.
function obsRequests({ url = 'ws://127.0.0.1:4455', password = '' }, requests) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const pending = new Map();
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error('OBS did not answer (is its WebSocket server on?)'));
    }, 4000);
    const finish = (err) => {
      clearTimeout(timer);
      ws.close();
      err ? reject(err) : resolve();
    };
    ws.onerror = () => finish(new Error(`can't reach OBS at ${url}`));
    ws.onmessage = ({ data }) => {
      const { op, d } = JSON.parse(data);
      if (op === 0) {
        // Hello: identify, with auth if OBS asks for it.
        const identify = { rpcVersion: 1 };
        if (d.authentication) {
          const secret = sha256b64(password + d.authentication.salt);
          identify.authentication = sha256b64(secret + d.authentication.challenge);
        }
        ws.send(JSON.stringify({ op: 1, d: identify }));
      } else if (op === 2) {
        requests.forEach(([requestType, requestData], i) => {
          const requestId = String(i);
          pending.set(requestId, requestType);
          ws.send(JSON.stringify({ op: 6, d: { requestType, requestId, requestData } }));
        });
      } else if (op === 7) {
        if (!d.requestStatus.result) {
          return finish(new Error(`OBS ${pending.get(d.requestId)}: ${d.requestStatus.comment || d.requestStatus.code}`));
        }
        pending.delete(d.requestId);
        if (pending.size === 0) finish();
      }
    };
  });
}

module.exports = { obsRequests };
