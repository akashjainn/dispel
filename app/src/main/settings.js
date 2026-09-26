// User settings, kept in <userData>/settings.json. Main process only; the
// settings window reads and writes them through validated IPC.
//
// mode: "personal" (alerts go to a trusted contact) or "business" (to a manager).
// contact: who "Notify" texts. handle is a phone number or an iMessage email.

const fs = require('node:fs');
const path = require('node:path');
const { app } = require('electron');

const DEFAULTS = { mode: 'personal', contact: { name: '', handle: '' } };

const file = () => path.join(app.getPath('userData'), 'settings.json');

// A phone number (digits, spaces, dashes, dots, parens, optional leading +) or an email.
const PHONE = /^\+?[0-9][0-9 ().-]{6,20}$/;
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,255}\.[a-z]{2,}$/i;

function validHandle(h) {
  return typeof h === 'string' && (PHONE.test(h.trim()) || EMAIL.test(h.trim()));
}

function clean(input) {
  const mode = input?.mode === 'business' ? 'business' : 'personal';
  const name = typeof input?.contact?.name === 'string' ? input.contact.name.trim().slice(0, 60) : '';
  const handle = typeof input?.contact?.handle === 'string' ? input.contact.handle.trim().slice(0, 120) : '';
  return { mode, contact: { name, handle } };
}

function loadSettings() {
  try {
    return clean(JSON.parse(fs.readFileSync(file(), 'utf8')));
  } catch (err) {
    if (err.code !== 'ENOENT') console.error('[settings] ignoring settings.json:', err.message);
    return clean(DEFAULTS);
  }
}

// Returns { ok: true, settings } or { ok: false, error } (shown in the settings window).
function saveSettings(input) {
  const s = clean(input);
  if (s.contact.handle && !validHandle(s.contact.handle)) {
    return { ok: false, error: 'Enter a phone number (like +1 404 555 0123) or an iMessage email.' };
  }
  try {
    fs.mkdirSync(path.dirname(file()), { recursive: true });
    fs.writeFileSync(file(), JSON.stringify(s, null, 2) + '\n');
  } catch (err) {
    return { ok: false, error: `Couldn’t save settings: ${err.message}` };
  }
  return { ok: true, settings: s };
}

// What the wizard's notify button says and whether it can send yet.
function notifyInfo(s = loadSettings()) {
  const business = s.mode === 'business';
  const configured = validHandle(s.contact.handle);
  const who = s.contact.name || (business ? 'my manager' : 'my trusted contact');
  return {
    configured,
    label: configured ? `Notify ${who}` : business ? 'Set up “Notify my manager”' : 'Set up “Notify trusted contact”',
    who,
  };
}

module.exports = { loadSettings, saveSettings, notifyInfo, validHandle };
