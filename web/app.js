// Hocus Pocus website: the desktop wizard's file check, in a browser. The sprite stage, the wizard's
// idle life, its voice lines and the lessons are the app's own scripts (app/src/renderer/, served at
// /shared/); this file draws the page's states and the evidence report. Contract: docs/INTERFACES.md
// (POST /web/analyze returns the same AnalyzeResponse as /analyze).

const $ = (id) => document.getElementById(id);

const EXTENSIONS = ['.wav', '.mp3', '.m4a', '.webm', '.ogg', '.oga', '.opus', '.flac', '.aac', '.mp4', '.mov'];
const MAX_BYTES = 25 * 1024 * 1024;
const TIMEOUT_MS = 120000;

// ---------- the stage: pot, character, wand, poof (as in app/src/renderer/wizard.js) ----------

const px = (name) => `/Assets/${name}`;
const render3d = (name) => ({ src: `/Assets/3d/${name}`, scale: 4 });
const stage = new Stage($('stage'));
const potLayer = stage.add({ '2d': px('pot-sheet.png'), '3d': render3d('pot-sheet.png') }, emptyPot);
const wizardLayer = stage.add(
  {
    'wizard-2d': px('wizard-sprites.png'),
    'witch-2d': px('witch-sprites.png'),
    'wizard-3d': render3d('wizard-sprites.png'),
    'witch-3d': render3d('witch-sprites.png'),
  },
  noStewShadow,
);
const wandLayer = stage.add({ '2d': px('wand-hand.png'), '3d': render3d('wand-hand.png') });
const poofLayer = stage.add({ '2d': px('wizard-poof.png'), '3d': render3d('wizard-poof.png') });
const presence = new Presence(stage, { wizard: wizardLayer, wand: wandLayer, pot: potLayer });

// ---------- saved preferences (this browser only; the page works without them) ----------

const prefs = (() => {
  try {
    return JSON.parse(localStorage.getItem('hocuspocus') || '{}');
  } catch {
    return {};
  }
})();
function savePrefs() {
  try {
    localStorage.setItem('hocuspocus', JSON.stringify(prefs));
  } catch {
    /* private window or blocked storage: fine */
  }
}

// ---------- looks: wizard or witch, 2D or 3D ----------

const LOOK_SHEETS = [
  [potLayer, (l) => l.style],
  [wizardLayer, (l) => `${l.character}-${l.style}`],
  [wandLayer, (l) => l.style],
  [poofLayer, (l) => l.style],
];
const loadLook = (l) => Promise.all(LOOK_SHEETS.map(([layer, key]) => layer.load(key(l))));
let look = {
  character: prefs.character === 'witch' ? 'witch' : 'wizard',
  style: prefs.style === '3d' ? '3d' : '2d',
};

function applyLook(l) {
  look = l;
  for (const [layer, key] of LOOK_SHEETS) layer.use(key(l));
  stage.pixel = l.style === '2d';
  document.documentElement.classList.toggle('look-3d', l.style === '3d');
  const other = l.character === 'wizard' ? 'witch' : 'wizard';
  $('character').textContent = `Turn into a ${other}`;
  $('character').setAttribute('aria-pressed', String(l.character === 'witch'));
  $('style3d').setAttribute('aria-pressed', String(l.style === '3d'));
  $('who').textContent = l.character;
  $('stage').setAttribute('aria-label', `The ${l.character}. Click to choose an audio file, or drop one here.`);
}
applyLook(look);

const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
let lookChange = 0;

async function changeLook(next) {
  const id = ++lookChange;
  $('character').disabled = $('style3d').disabled = true;
  try {
    await loadLook(next);
  } finally {
    $('character').disabled = $('style3d').disabled = false;
  }
  if (id !== lookChange) return;
  stage.finishSweep();
  prefs.character = next.character;
  prefs.style = next.style;
  savePrefs();
  if (reduceMotion.matches) return applyLook(next);
  if (next.character !== look.character) {
    // The old character sinks into the hat, a poof covers the swap, the new one rises.
    const resume = wizardLayer.loop;
    stage.burst(47, 30, 8);
    wizardLayer.play(WIZARD.vanish, 18, {
      once: true,
      onDone: () => {
        applyLook(next);
        poof();
        stage.burst(47, 64, 26);
        wizardLayer.play(WIZARD.appear, 16, { once: true, onDone: () => resume && wizardLayer.play(resume.frames, resume.fps) });
      },
    });
  } else {
    stage.sweepTo(() => applyLook(next));
  }
}

$('character').addEventListener('click', () =>
  changeLook({ ...look, character: look.character === 'wizard' ? 'witch' : 'wizard' }),
);
$('style3d').addEventListener('click', () => changeLook({ ...look, style: look.style === '3d' ? '2d' : '3d' }));

// ---------- voice lines (app/Assets/voice), only at big moments and only if sound is on ----------

const voice = new Voice(() => look.character);
let soundOn = prefs.sound !== false;
function renderSound() {
  $('sound').textContent = soundOn ? 'Voice on' : 'Voice off';
  $('sound').setAttribute('aria-pressed', String(soundOn));
}
renderSound();
$('sound').addEventListener('click', () => {
  soundOn = !soundOn;
  prefs.sound = soundOn;
  savePrefs();
  if (!soundOn) voice.stop();
  renderSound();
});
const say = (...lines) => soundOn && voice.say(...lines);
const sayNow = (...lines) => soundOn && voice.interrupt(...lines);
const VERDICT_LINES = { likely_synthetic: ['reveal', 'snark'], likely_real: ['real'], inconclusive: ['unsure'] };

// ---------- the speech bubble ----------

const COPY = {
  likely_synthetic: { title: 'This voice is likely synthetic.', report: 'Likely synthetic' },
  inconclusive: { title: 'I can’t tell from this clip.', report: 'Inconclusive' },
  likely_real: { title: 'This voice is likely real.', report: 'Likely real' },
};
const DIGIT_ROW = { inconclusive: 0, likely_synthetic: 1, likely_real: 2 };

function renderDigits(percent, verdict) {
  const el = $('digits');
  el.replaceChildren();
  const r = DIGIT_ROW[verdict] ?? 0;
  for (const ch of String(percent)) {
    const idx = ch === '0' ? 9 : Number(ch) - 1; // sheet order: 1 2 3 4 5 6 7 8 9 0
    const d = document.createElement('span');
    d.className = 'digit';
    d.style.backgroundPosition = `${-idx * 21}px ${-r * 33}px`;
    el.append(d);
  }
  el.setAttribute('aria-label', `${percent}`);
}

function bubble({ title, note = '', result = null, actions = false }) {
  const b = $('bubble');
  b.className = `bubble${result ? ' ' + result.overall.verdict : ''}`;
  // restart the pop animation
  b.style.animation = 'none';
  void b.offsetWidth;
  b.style.animation = '';
  $('bubble-title').textContent = title;
  $('bubble-score').hidden = !result;
  if (result) renderDigits(Math.round(result.overall.probability * 100), result.overall.verdict);
  $('bubble-note').textContent = note;
  $('bubble-actions').hidden = !actions;
}

function poof() {
  poofLayer.play(POOF.burst, 16, { once: true, onDone: () => poofLayer.hide() });
}

function wand(on) {
  if (on) wandLayer.play(WAND.cast, 8);
  else wandLayer.hide();
}

// ---------- states ----------

let mode = 'idle';
let health = null; // GET /health, once
const idleText = () => ({
  title: `Drop a voice clip on me, or click me to pick one.`,
  note: health?.mock
    ? 'Heads up: my detection model isn’t connected right now, so answers are demo data.'
    : 'I’ll tell you how likely it is that the voice was made by AI.',
});

function setMode(next, state = {}) {
  mode = next;
  presence.setMode(next, state);
}

function idle({ appear = false } = {}) {
  setMode('idle', { appear });
  wand(false);
  potLayer.play(POT.bubble, 6);
  if (appear && !reduceMotion.matches) {
    poof();
    wizardLayer.play(WIZARD.appear, 14, { once: true, onDone: () => wizardLayer.play(WIZARD.idle, 6) });
  } else {
    wizardLayer.play(WIZARD.idle, 6);
  }
  bubble(idleText());
}

function analyzing(name) {
  setMode('analyzing');
  wand(true);
  potLayer.play(POT.bubble, 12);
  wizardLayer.play(WIZARD.focus, 8);
  bubble({ title: `Hmm… let me listen to “${name}”.`, note: 'Consulting the cauldron… (your clip is on our server just long enough to check it)' });
  sayNow('drop');
}

function showResult(result, name) {
  setMode('result', { result });
  wand(false);
  potLayer.play(POT.bubble, 6);
  const { verdict } = result.overall;
  wizardLayer.play(verdict === 'likely_real' ? WIZARD.happy : WIZARD.idle, 6);
  poof();
  const notes = ['One clip isn’t proof. Check the source too.'];
  if (result.channel?.phone_like) notes.push('It sounds like a phone call, which lowers reliability.');
  if (result.mock) notes.push('Demo data: no detection model is connected.');
  bubble({ title: COPY[verdict].title, result, note: notes.join(' '), actions: true });
  say(...VERDICT_LINES[verdict]); // after "let me stir the cauldron" finishes
  renderReport(result, name);
}

function showError(title, note = '') {
  setMode('result', { message: null });
  wand(false);
  potLayer.play(POT.bubble, 6);
  wizardLayer.play(WIZARD.idle, 6);
  bubble({ title, note });
}

// ---------- checking a file ----------

const ERRORS = {
  too_short: ['That clip is too short.', 'Give me at least a second of speech.'],
  too_long: ['That clip is too long for me.', 'Keep it under 2 minutes and 25 MB. Trim it and try again.'],
  decode_failed: ['I couldn’t read that file.', 'Try wav, mp3, m4a, flac, ogg, webm, or a video with sound.'],
  rate_limited: ['My cauldron needs a breather.', 'You’ve checked a lot of clips. Try again in a while.'],
  bad_request: ['Something about that request was off.', 'Try choosing the file again.'],
};

let busy = false;

async function check(file) {
  if (busy || !file) return;
  const ext = (file.name.match(/\.[^.]+$/)?.[0] || '').toLowerCase();
  if (!EXTENSIONS.includes(ext)) return showError('That doesn’t look like audio I can read.', ERRORS.decode_failed[1]);
  if (file.size > MAX_BYTES) return showError(...ERRORS.too_long);
  if (!file.size) return showError(...ERRORS.too_short);

  busy = true;
  $('report').hidden = true;
  analyzing(file.name);
  const body = new FormData();
  body.append('file', file, file.name);
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch('/web/analyze', { method: 'POST', body, signal: ctl.signal });
    const data = await r.json().catch(() => null);
    if (r.ok && data?.overall) return showResult(data, file.name);
    const known = ERRORS[data?.error] || (r.status === 413 ? ERRORS.too_long : null);
    if (known) return showError(...known);
    showError('My spell fizzled.', 'Something went wrong on our server. Try again in a moment.');
  } catch (err) {
    showError(
      err.name === 'AbortError' ? 'That took too long.' : 'I can’t reach my cauldron.',
      'Our server may be busy or offline. Try again in a moment.',
    );
  } finally {
    clearTimeout(timer);
    busy = false;
    $('file').value = ''; // choosing the same file again still fires `change`
  }
}

function pickFile() {
  if (!busy) $('file').click();
}

$('file').addEventListener('change', () => check($('file').files[0]));

// Click (or Enter / Space) on the character: sparkle where it was touched, then pick a file.
const canvas = $('stage');
canvas.addEventListener('click', (e) => {
  const r = canvas.getBoundingClientRect();
  presence.click(((e.clientX - r.left) / r.width) * STAGE_W, ((e.clientY - r.top) / r.height) * STAGE_H);
  pickFile();
});
canvas.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  e.preventDefault();
  presence.click(STAGE_W / 2, STAGE_H / 3);
  pickFile();
});
canvas.addEventListener('pointerenter', () => presence.hover(true));
canvas.addEventListener('pointerleave', () => presence.hover(false));

// Drop anywhere on the page. dragleave also fires between child elements, so wait a moment before
// deciding the file really left.
let dragLeft = null;
let dragging = false;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
function dragState(on) {
  clearTimeout(dragLeft);
  if (on === dragging) return;
  dragging = on;
  $('drop-zone').classList.toggle('drop-hover', on);
  document.body.classList.toggle('drop-hover', on);
  presence.dragOver(on);
  if (!busy) {
    if (on) bubble({ title: 'Ooh, a file! Let go and I’ll check it.' });
    else if (mode === 'idle') bubble(idleText());
  }
}
document.addEventListener('dragover', (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
  dragState(true);
});
document.addEventListener('dragleave', () => {
  clearTimeout(dragLeft);
  dragLeft = setTimeout(() => dragState(false), 120);
});
document.addEventListener('drop', (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragState(false);
  check(e.dataTransfer.files[0]);
});

const again = () => {
  $('report').hidden = true;
  window.scrollTo({ top: 0 });
  idle();
  pickFile();
};
$('again').addEventListener('click', again);
$('again-2').addEventListener('click', again);
$('see-evidence').addEventListener('click', () => $('report').scrollIntoView({ block: 'start' }));

// ---------- the evidence report ----------

// What each technique is, in plain words. Unknown names still show, with their own finding.
const TECHNIQUES = {
  dl_detector: ['Neural detector', 'A speech model fine-tuned to tell real voices from AI-made ones.'],
  hf_detector: ['Open-source neural detector', 'A public deepfake-audio model standing in while ours loads.'],
  lfcc: ['Frequency-texture detector', 'Looks at fine texture in the sound’s frequencies (LFCC features).'],
  prosody: ['Prosody', 'Pitch range, pitch movement, jitter and shimmer.'],
  spectral: ['Spectral', 'How energy is spread across frequencies.'],
  voice: ['Voice quality', 'Breathiness and the voice’s harmonic structure.'],
  rhythm: ['Rhythm', 'Timing of syllables, pauses and speaking rate.'],
};
const LLR_CAP = Math.log(100);
const pct = (p) => `${Math.round(p * 100)}%`;
const colorFor = (p) => (p >= 0.75 ? 'var(--synthetic)' : p <= 0.25 ? 'var(--real)' : 'var(--unsure)');
const el = (tag, props = {}, ...kids) => append(Object.assign(document.createElement(tag), props), kids);
function append(node, kids) {
  for (const k of kids.flat()) if (k != null) node.append(k);
  return node;
}
const secs = (s) => `${Number(s).toFixed(s % 1 ? 1 : 0)} s`;

function renderReport(res, name) {
  const { overall } = res;
  $('report').className = `report v-${overall.verdict}`;
  $('report-title').textContent = COPY[overall.verdict].report;
  $('report-file').textContent = name;
  $('mock-badge').hidden = !res.mock;

  $('meter-pct').textContent = pct(overall.probability);
  $('meter-mark').style.left = '0%';
  requestAnimationFrame(() => requestAnimationFrame(() => ($('meter-mark').style.left = `${overall.probability * 100}%`)));
  $('meter').setAttribute('aria-label', `${pct(overall.probability)} chance synthetic: ${COPY[overall.verdict].report.toLowerCase()}`);

  const ch = res.channel;
  const channel = $('channel');
  if (ch?.phone_like || ch?.note) {
    channel.hidden = false;
    channel.className = `callout${ch.phone_like ? ' warn' : ''}`;
    channel.textContent = ch.phone_like
      ? `Sounds like a phone call or heavily compressed audio (${ch.note || 'narrow band'}). That lowers reliability.`
      : `Audio quality: ${ch.note}.`;
  } else channel.hidden = true;

  // Per-window likelihoods.
  const timeline = $('timeline');
  timeline.replaceChildren();
  for (const s of res.segments || []) {
    const row = el('div', { className: 'seg' },
      el('span', { textContent: `${secs(s.start_s)}–${secs(s.end_s)}` }),
      el('div', { className: 'seg-bar' }, el('div', { className: 'seg-fill' })),
      el('span', { className: 'seg-pct', textContent: pct(s.probability) }),
    );
    const fill = row.querySelector('.seg-fill');
    fill.style.width = `${Math.max(2, s.probability * 100)}%`;
    fill.style.background = colorFor(s.probability);
    timeline.append(row);
  }
  if (!timeline.children.length) timeline.append(el('p', { className: 'muted small', textContent: 'No per-window scores for this clip.' }));

  // Techniques: what ran, what it found, how much it moved the score.
  const list = $('techniques');
  list.replaceChildren();
  for (const a of res.analyzers || []) {
    const [label, what] = TECHNIQUES[a.name] || [a.name.replace(/_/g, ' '), ''];
    const votes = (a.role || 'vote') === 'vote';
    const c = Number(a.llr_contribution) || 0;
    let move;
    if (!a.ran) move = el('span', { className: 'tech-move none', textContent: 'Didn’t run' });
    else if (!votes || Math.abs(c) < 0.05) move = el('span', { className: 'tech-move none', textContent: votes ? 'No effect on the score' : 'Doesn’t change the score' });
    else move = el('span', { className: `tech-move ${c > 0 ? 'up' : 'down'}`, textContent: `${c > 0 ? '+' : '−'}${Math.abs(c).toFixed(1)} toward ${c > 0 ? 'synthetic' : 'real'}` });
    const item = el('li', { className: 'tech' },
      el('div', { className: 'tech-head' },
        el('span', { className: 'tech-name', textContent: label }),
        el('span', { className: `tag${a.ran ? '' : ' off'}`, textContent: votes ? 'votes' : 'evidence' }),
        move,
      ),
      what ? el('p', { className: 'muted', textContent: what }) : null,
      el('p', { textContent: a.finding || '' }),
    );
    if (a.ran && votes && Math.abs(c) >= 0.05) {
      const w = Math.min(Math.abs(c) / LLR_CAP, 1) * 50;
      const bar = el('span');
      bar.style.cssText = `${c > 0 ? 'left' : 'right'}:50%;width:${w}%;background:${c > 0 ? 'var(--synthetic)' : 'var(--real)'}`;
      item.append(el('div', { className: 'push', title: 'Push toward real (left) or synthetic (right)' }, bar));
    }
    list.append(item);
  }

  // Only name a manipulation type when the server is confident; a wrong label is worse than "unknown".
  const m = res.manipulation;
  $('manipulation').textContent = m && m.type && m.type !== 'unknown' && m.confidence >= 0.8 ? `${m.type} (${pct(m.confidence)} confident)` : 'unknown';
  const inp = res.input || {};
  $('clip-facts').textContent = [
    res.duration_s != null ? `${Number(res.duration_s).toFixed(1)} s` : null,
    inp.codec,
    inp.sample_rate ? `${(inp.sample_rate / 1000).toFixed(1)} kHz` : null,
    inp.channels ? (inp.channels === 1 ? 'mono' : `${inp.channels} channels`) : null,
  ].filter(Boolean).join(' · ');
  $('model-facts').textContent = [res.model?.name, res.timing_ms != null ? `${res.timing_ms < 100 ? 'under 0.1' : (res.timing_ms / 1000).toFixed(1)} s to check` : null]
    .filter(Boolean)
    .join(' · ');

  $('transcript-wrap').hidden = !res.transcript;
  $('transcript').textContent = res.transcript || '';

  // "What this can't tell you": the server's caveats, then the ones that always apply.
  const limits = $('limits');
  limits.replaceChildren();
  const always = [
    'It can’t prove a voice is real or fake. It gives a likelihood from this one clip.',
    'New voice clones of real people are the hardest case and can still come out “likely real”.',
    'Real speech cleaned up with a voice isolator or heavy noise removal often scores as synthetic.',
    'Phone calls, heavy compression and sped-up or slowed-down audio lower reliability.',
    'Your file was sent to our server, checked in memory and deleted. We don’t keep it or share it.',
  ];
  for (const t of [...new Set([...(res.limitations || []), ...always])]) limits.append(el('li', { textContent: t }));

  $('report').hidden = false;
}

// ---------- learn: the app's lessons, one short page at a time ----------

function renderLessons() {
  const box = $('lessons');
  for (const key of LESSON_TOPICS) {
    const { title, pages } = LESSONS[key];
    let page = 0;
    const text = el('p', { className: 'lesson-text' });
    const count = el('span', { className: 'lesson-page' });
    const back = el('button', { className: 'btn', type: 'button', textContent: 'Back' });
    const next = el('button', { className: 'btn btn-yes', type: 'button', textContent: 'Next' });
    const draw = () => {
      text.textContent = pages[page];
      count.textContent = `${page + 1} / ${pages.length}`;
      back.disabled = page === 0;
      next.disabled = page === pages.length - 1;
    };
    back.addEventListener('click', () => { page = Math.max(0, page - 1); draw(); });
    next.addEventListener('click', () => { page = Math.min(pages.length - 1, page + 1); draw(); });
    draw();
    box.append(el('article', { className: 'lesson' }, el('h3', { textContent: title }), text, el('div', { className: 'lesson-nav' }, back, count, next)));
  }
}
renderLessons();

// ---------- start ----------

loadLook(look).then(() => idle({ appear: true }));
fetch('/health')
  .then((r) => (r.ok ? r.json() : null))
  .then((h) => {
    health = h;
    if (mode === 'idle' && !dragging) bubble(idleText());
  })
  .catch(() => {});
