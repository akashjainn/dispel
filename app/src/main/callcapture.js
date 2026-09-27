// Records a few seconds of a call with bin/callcapture (macOS 14.2+), hands
// the WAV to `use`, then deletes it. Runs only when the user asks the wizard
// to listen (AGENTS.md: never record continuously, never keep audio).
//
// Errors thrown here carry `userMessage`, which the wizard shows as-is.

const { execFile } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const HELPER = path.join(__dirname, '..', '..', 'bin', 'callcapture');
const LISTEN_SECONDS = 12; // the neural detector scores up to 3 x 4 s windows

function userError(userMessage, detail) {
  const err = new Error(detail || userMessage);
  err.userMessage = userMessage;
  return err;
}

const available = () => process.platform === 'darwin' && fs.existsSync(HELPER);

function record(outPath, seconds, prefixes) {
  const args = ['--seconds', String(seconds), '--out', outPath];
  for (const p of prefixes) args.push('--prefix', p);
  return new Promise((resolve, reject) => {
    execFile(HELPER, args, { timeout: (seconds + 15) * 1000 }, (err, stdout) => {
      let msg = null;
      try {
        msg = JSON.parse(stdout.trim().split('\n').pop());
      } catch {}
      if (msg?.ok) resolve(msg);
      else reject(userError('I couldn’t listen to the call.', msg?.error || err?.message || 'callcapture failed'));
    });
  });
}

// prefixes: bundle-ID prefixes of the call app (from callwatch). With none, or
// if that app isn't playing sound, the helper taps all system audio instead.
async function withCallClip({ app, prefixes = [], seconds = LISTEN_SECONDS }, use) {
  if (!available()) throw userError('I can’t listen to calls on this Mac. It needs macOS 14.2 or later.');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dispel-'));
  const clip = path.join(dir, `call-${crypto.randomUUID()}.wav`);
  try {
    const rec = await record(clip, seconds, prefixes);
    console.log(`[listen] ${rec.seconds.toFixed(1)} s from ${rec.scope === 'app' ? app : 'system audio'}, peak ${rec.peak.toFixed(3)}`);
    if (rec.silent) {
      throw userError(
        `I couldn’t hear anything from ${app}. If the caller was talking, allow Dispel under System Settings → Privacy & Security → Screen & System Audio Recording.`,
        'silent capture',
      );
    }
    return await use(clip, rec);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

module.exports = { withCallClip, LISTEN_SECONDS };
