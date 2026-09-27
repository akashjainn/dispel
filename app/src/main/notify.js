// Texts the trusted contact or manager through the Mac's Messages app
// (iMessage, falling back to SMS when an iPhone relays texts). Nothing goes
// through our server. Sent only when the user presses the button.
//
// The first send makes macOS ask "Dispel wants to control Messages".

const { execFile } = require('node:child_process');
const { validHandle } = require('./settings');

// The handle and text are passed as arguments, never pasted into the script.
const SCRIPT = `
on run argv
  set theHandle to item 1 of argv
  set theText to item 2 of argv
  tell application "Messages"
    try
      set svc to 1st account whose service type = iMessage
      send theText to participant theHandle of svc
    on error
      set svc to 1st account whose service type = SMS
      send theText to participant theHandle of svc
    end try
  end tell
end run`;

function sendText(handle, text) {
  return new Promise((resolve) => {
    if (process.platform !== 'darwin') return resolve({ ok: false, error: 'Texting needs macOS Messages.' });
    if (!validHandle(handle)) return resolve({ ok: false, error: 'No valid phone number or email in Settings.' });
    execFile('osascript', ['-e', SCRIPT, handle.trim(), text], { timeout: 15000 }, (err, _out, stderr) => {
      if (!err) return resolve({ ok: true });
      const msg = String(stderr || err.message);
      console.error('[notify] send failed:', msg.trim());
      if (/-1743|not authori[sz]ed/i.test(msg)) {
        return resolve({
          ok: false,
          error: 'Allow Dispel to control Messages: System Settings → Privacy & Security → Automation.',
        });
      }
      resolve({ ok: false, error: 'Messages couldn’t send it. Is Messages signed in?' });
    });
  });
}

// The alert text. Honest: "likely", the score, and a note when it's a mock.
function alertText({ mode, app, result }) {
  const pct = Math.round(result.overall.probability * 100);
  const where = app ? `a call (${app})` : 'a call';
  const mock = result.mock ? ' [Test: no detection model is connected yet.]' : '';
  if (mode === 'business') {
    return (
      `Security alert from Dispel: I’m on ${where} where the caller’s voice was flagged as likely ` +
      `AI-generated (${pct}% chance). Please don’t act on any payment or access request tied to this call ` +
      `until it’s verified. Can you call me?${mock}`
    );
  }
  return (
    `Heads up from Dispel: I’m on ${where} and the caller’s voice was flagged as likely AI-generated ` +
    `(${pct}% chance). If anyone contacts you about this or asks for money, check with me directly first. ` +
    `Can you call me?${mock}`
  );
}

function testText(mode) {
  const role = mode === 'business' ? 'manager' : 'trusted contact';
  return `Test from Dispel: you’re set as my ${role} for deepfake call alerts. No action needed.`;
}

module.exports = { sendText, alertText, testText };
