const $ = (id) => document.getElementById(id);
let clips = [];        // { name, src, label, file }
let current = null;    // the clip on the phone
let state = 'idle';    // idle | ringing | connected
let mic = null, player = null, ringer = null, timer = null, startedAt = 0;

let showKey = false;
try { showKey = localStorage.getItem('callsim.showKey') === '1'; } catch {}

function prettyName(file) {
  const base = file.split('/').pop().replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').trim();
  return base ? base[0].toUpperCase() + base.slice(1) : 'Unknown';
}

function tagHtml(label) {
  if (!label) return '<span class="tag">no key</span>';
  return `<span class="tag ${label}">${label}</span>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function setClips(list) {
  clips = list.map((c) => ({ ...c, name: prettyName(c.file) }));
  render();
}

async function loadClips() {
  setClips(await window.callsim.list());
}

function render() {
  const list = $('list');
  list.innerHTML = '';
  if (!clips.length) {
    list.innerHTML = '<div class="empty">No callers yet. Drag audio files onto the phone, or put them in clips/real and clips/synthetic (Folder).</div>';
  }
  clips.forEach((c, i) => {
    const b = document.createElement('button');
    b.className = 'row';
    b.innerHTML = `<span class="av">${escapeHtml(c.name[0].toUpperCase())}</span>` +
                  `<span class="name"><div>${escapeHtml(c.name)}</div><div class="file">${escapeHtml(c.file.split('/').pop())}</div></span>` +
                  (showKey ? tagHtml(c.label) : '');
    b.onclick = () => ring(i);
    list.appendChild(b);
  });
  $('showKey').classList.toggle('on', showKey);
  showAnswerKey();
}

function showAnswerKey() {
  const html = current && showKey ? tagHtml(current.label) : '';
  $('keyIn').innerHTML = html;
  $('keyOn').innerHTML = html;
}

// ---------- ringtone (synthesized, two-tone like a phone) ----------
function startRinger() {
  const ctx = new AudioContext();
  const gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(ctx.destination);
  for (const f of [440, 480]) {
    const o = ctx.createOscillator();
    o.frequency.value = f;
    o.connect(gain);
    o.start();
  }
  const t0 = ctx.currentTime;
  for (let k = 0; k < 20; k++) { // 2 s on, 4 s off, for up to 2 minutes
    gain.gain.setValueAtTime(0.08, t0 + k * 6);
    gain.gain.setValueAtTime(0, t0 + k * 6 + 2);
  }
  ringer = ctx;
}
function stopRinger() { if (ringer) { ringer.close(); ringer = null; } }

// ---------- call flow ----------
function setPhone(title, status) {
  $('callerIn').textContent = title;
  $('callerOn').textContent = title;
  $('status').textContent = status;
  $('avatarIn').textContent = current ? current.name[0].toUpperCase() : '?';
  $('recents').classList.toggle('hidden', state !== 'idle');
  $('incoming').classList.toggle('hidden', state !== 'ringing');
  $('inCall').classList.toggle('hidden', state !== 'connected');
  showAnswerKey();
}

function ring(i) {
  if (state !== 'idle') endCall();
  current = clips[i];
  state = 'ringing';
  $('err').textContent = '';
  setPhone(current.name, 'incoming call…');
  startRinger();
}

async function answer() {
  stopRinger();
  $('err').textContent = '';
  // Holding the mic is what makes the wizard see a call. Nothing is recorded:
  // the stream is never read, and it's released on hang-up.
  try {
    if (!(await window.callsim.askMic())) throw new Error('denied');
    mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    $('err').textContent = 'No microphone access, so the wizard won\'t see this as a call. Allow Call Simulator under System Settings → Privacy & Security → Microphone.';
  }
  if (state !== 'ringing') { endCall(); return; } // hung up while the mic prompt was open
  state = 'connected';
  player = new Audio(current.src);
  player.onerror = () => { $('err').textContent = 'Can\'t play that file. Try WAV or MP3.'; };
  startedAt = Date.now();
  setPhone(current.name, '0:00');
  try { await player.play(); } catch (e) { $('err').textContent = 'Could not play the clip: ' + e.message; }
  timer = setInterval(() => {
    if (state === 'connected') $('status').textContent = elapsed();
  }, 250);
}

function elapsed() {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function endCall() {
  stopRinger();
  clearInterval(timer);
  if (player) { player.pause(); player = null; }
  if (mic) { mic.getTracks().forEach((t) => t.stop()); mic = null; }
  state = 'idle';
  current = null;
  setPhone('No call', '');
}

$('accept').onclick = answer;
$('decline').onclick = endCall;
$('hangup').onclick = endCall;
$('openFolder').onclick = () => window.callsim.openFolder();
$('surprise').onclick = () => { if (clips.length) ring(Math.floor(Math.random() * clips.length)); };
$('showKey').onclick = () => {
  showKey = !showKey;
  try { localStorage.setItem('callsim.showKey', showKey ? '1' : '0'); } catch {}
  render();
};
window.addEventListener('beforeunload', endCall);
window.callsim.onChanged(loadClips);

// ---------- drop files in (copied into clips/real or clips/synthetic) ----------
// Dragging files over the phone shows two targets; drop on one to pick the label.
let dragDepth = 0;
const showDrops = (on) => $('drops').classList.toggle('hidden', !on);
window.addEventListener('dragenter', (e) => {
  e.preventDefault();
  if (e.dataTransfer.types.includes('Files') && dragDepth++ === 0) showDrops(true);
});
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; showDrops(false); } });
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => { e.preventDefault(); dragDepth = 0; showDrops(false); });
for (const zone of document.querySelectorAll('.drop')) {
  zone.addEventListener('dragover', () => zone.classList.add('over'));
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', async (e) => {
    zone.classList.remove('over');
    setClips(await window.callsim.add(e.dataTransfer.files, zone.dataset.label));
  });
}

// Status-bar clock.
const tick = () => { $('clock').textContent = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).replace(/\s?[AP]M/i, ''); };
tick();
setInterval(tick, 10_000);

setPhone('No call', '');
loadClips();
