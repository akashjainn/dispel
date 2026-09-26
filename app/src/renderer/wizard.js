// Draws whatever state the main process sends. All decisions live in main.

const $ = (id) => document.getElementById(id);

const wizardLayer = new SpriteLayer($('wizard'), 16);
const potLayer = new SpriteLayer($('pot'), 96);
const wandLayer = new SpriteLayer($('wand'));
const poofLayer = new SpriteLayer($('poof'));

const COPY = {
  likely_synthetic: { title: 'This voice is likely synthetic.', label: 'chance it’s synthetic' },
  inconclusive: { title: 'I can’t tell from this clip.', label: 'chance it’s synthetic' },
  likely_real: { title: 'This voice is likely real.', label: 'chance it’s synthetic' },
};
const DIGIT_ROW = { inconclusive: 0, likely_synthetic: 1, likely_real: 2 };
let mode = 'hidden';

// ---------- drawing helpers ----------

function setBody(...classes) {
  document.body.className = classes.join(' ');
}

function poof() {
  $('poof').hidden = false;
  poofLayer.play(POOF.burst, 16, { once: true, onDone: () => ($('poof').hidden = true) });
}

function wand(on) {
  $('wand').hidden = !on;
  if (on) wandLayer.play(WAND.cast, 8);
  else wandLayer.stop();
}

function renderDigits(percent, verdict) {
  const el = $('digits');
  el.replaceChildren();
  const row = DIGIT_ROW[verdict] ?? 0;
  for (const ch of String(percent)) {
    const idx = ch === '0' ? 9 : Number(ch) - 1; // sheet order: 1 2 3 4 5 6 7 8 9 0 :
    const d = document.createElement('span');
    d.className = 'digit';
    d.style.backgroundPosition = `${-idx * 21}px ${-row * 33}px`;
    el.append(d);
  }
}

function showBubble({ title, result, note = '', alert = false }) {
  const b = $('bubble');
  b.className = `bubble${alert ? ' alert' : ''}${result ? ' ' + result.overall.verdict : ''}`;
  $('bubble-title').textContent = title;
  $('bubble-score').hidden = !result;
  if (result) {
    const { probability, verdict } = result.overall;
    renderDigits(Math.round(probability * 100), verdict);
    $('score-label').textContent = COPY[verdict].label;
  }
  const notes = [note, ...(result?.mock ? ['Mock result: no detection model is connected yet.'] : [])];
  $('bubble-note').textContent = notes.filter(Boolean).join(' ');
  b.hidden = false;
}

function hideBubble() {
  $('bubble').hidden = true;
}

function enter(appear, then) {
  if (!appear) return then();
  poof();
  wizardLayer.play(WIZARD.appear, 14, { once: true, onDone: then });
}

// ---------- states ----------

const states = {
  hidden() {
    [wizardLayer, potLayer, wandLayer, poofLayer].forEach((l) => l.stop());
    hideBubble();
  },

  vanish() {
    hideBubble();
    wand(false);
    wizardLayer.play(WIZARD.vanish, 14, { once: true, onDone: () => window.wizard.vanished() });
  },

  idle({ appear }) {
    setBody();
    hideBubble();
    wand(false);
    potLayer.play(POT.bubble, 6);
    enter(appear, () => wizardLayer.play(WIZARD.idle, 6));
  },

  analyzing({ name }) {
    setBody();
    wand(true);
    potLayer.play(POT.bubble, 12);
    wizardLayer.play(WIZARD.focus, 8);
    showBubble({ title: `Hmm… let me listen to “${name}”.`, note: 'Stirring the cauldron…' });
  },

  result({ result, error }) {
    setBody();
    wand(false);
    potLayer.play(POT.bubble, 6);
    if (error || !result) {
      wizardLayer.play(WIZARD.idle, 6);
      showBubble({ title: error || 'Something went wrong.' });
      return;
    }
    const { verdict } = result.overall;
    wizardLayer.play(verdict === 'likely_real' ? WIZARD.happy : WIZARD.idle, 6);
    poof();
    showBubble({ title: COPY[verdict].title, result, note: 'One clip isn’t proof. Check the source too.' });
  },

  'call-watch'({ appear }) {
    setBody('call', 'watching');
    hideBubble();
    wand(false);
    potLayer.stop();
    enter(appear, () => wizardLayer.play(WIZARD.focus, 4));
  },

  'call-alert'({ app, result, bubble = true }) {
    setBody('call');
    if (!bubble) {
      hideBubble();
      wand(false);
      return;
    }
    poof();
    wand(true);
    setTimeout(() => mode === 'call-alert' && wand(false), 2500);
    wizardLayer.play(WIZARD.idle, 8);
    showBubble({
      title: 'This is likely not a real person speaking.',
      result,
      note: `Heard on ${app}. Call audio is compressed, which makes this less reliable.`,
      alert: true,
    });
  },
};

window.wizard.onState((state) => {
  mode = state.mode;
  states[state.mode]?.(state);
});

// ---------- input: click to choose a file, drag to move, drop to analyze ----------

$('bubble-close').addEventListener('click', () => window.wizard.dismissBubble());
$('pot').addEventListener('click', () => window.wizard.pickFile());

const wiz = $('wizard');
let press = null;

wiz.addEventListener('pointerdown', (e) => {
  if (document.body.classList.contains('call')) return;
  press = { x: e.screenX, y: e.screenY, dragging: false };
  wiz.setPointerCapture(e.pointerId);
});

wiz.addEventListener('pointermove', (e) => {
  if (!press) return;
  if (!press.dragging && Math.hypot(e.screenX - press.x, e.screenY - press.y) > 4) {
    press.dragging = true;
    wiz.style.cursor = 'grabbing';
    window.wizard.drag('start', press.x, press.y);
  }
  if (press.dragging) window.wizard.drag('move', e.screenX, e.screenY);
});

wiz.addEventListener('pointerup', () => {
  if (!press) return;
  if (press.dragging) window.wizard.drag('end', 0, 0);
  else if (mode === 'idle' || mode === 'result') window.wizard.pickFile();
  wiz.style.cursor = '';
  press = null;
});

document.addEventListener('dragover', (e) => {
  e.preventDefault();
  document.body.classList.add('drop-hover');
});
document.addEventListener('dragleave', () => document.body.classList.remove('drop-hover'));
document.addEventListener('drop', (e) => {
  e.preventDefault();
  document.body.classList.remove('drop-hover');
  const file = e.dataTransfer.files[0];
  if (file && !document.body.classList.contains('call')) window.wizard.analyzeFile(file);
});
