// Draws whatever state the main process sends. All decisions live in main.

const $ = (id) => document.getElementById(id);

// Back to front, as in focus-wizard: pot, wizard (or witch), wand, poof.
const stage = new Stage($('stage'));
const potLayer = stage.add('../../Assets/pot-sheet.png', emptyPot);
const wizardLayer = stage.add(
  { wizard: '../../Assets/wizard-sprites.png', witch: '../../Assets/witch-sprites.png' },
  noStewShadow,
);
// Main passes the saved character in the page URL so the first frame is right.
wizardLayer.use(new URLSearchParams(location.search).get('character'));
const wandLayer = stage.add('../../Assets/wand-hand.png');
const poofLayer = stage.add('../../Assets/wizard-poof.png');

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
  poofLayer.play(POOF.burst, 16, { once: true, onDone: () => poofLayer.hide() });
}

function wand(on) {
  if (on) wandLayer.play(WAND.cast, 8);
  else wandLayer.hide();
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

// ask: { text, yes: bool, noLabel } shows a question with buttons, or null.
function showBubble({ title, result, note = '', alert = false, ask = null, learnMore = false }) {
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
  $('bubble-ask').hidden = !ask;
  $('lesson').hidden = true;
  $('learn-more').hidden = !learnMore;
  if (ask) {
    $('ask-text').textContent = ask.text;
    $('ask-yes').hidden = !ask.yes;
    $('ask-no').hidden = !ask.noLabel;
    $('ask-no').textContent = ask.noLabel || '';
  }
  b.hidden = false;
  placeBubble();
}

// Keep the tail pointing at the wizard's face: sit the bubble's bottom at
// face height, unless it's too tall for that, then pin it to the top.
const FACE_FROM_BOTTOM = 120; // px from the window bottom to just below the wizard's face
function placeBubble() {
  const b = $('bubble');
  b.style.top = '';
  const h = b.offsetHeight;
  const top = Math.max(6, window.innerHeight - FACE_FROM_BOTTOM - h);
  b.style.top = `${top}px`;
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
    showBubble({ title: `Hmm… let me listen to “${name}”.`, note: 'Consulting the cauldron…' });
  },

  result({ result, error, message }) {
    setBody();
    wand(false);
    potLayer.play(POT.bubble, 6);
    if (message) {
      wizardLayer.play(WIZARD.happy, 6);
      poof();
      showBubble({ title: message });
      return;
    }
    if (error || !result) {
      wizardLayer.play(WIZARD.idle, 6);
      showBubble({ title: error || 'Something went wrong.' });
      return;
    }
    const { verdict } = result.overall;
    wizardLayer.play(verdict === 'likely_real' ? WIZARD.happy : WIZARD.idle, 6);
    poof();
    showBubble({
      title: COPY[verdict].title,
      result,
      note: 'One clip isn’t proof. Check the source too.',
      learnMore: true,
    });
  },

  // Learn mode: the wizard teaches, one short page at a time. Paging happens
  // here; main only knows the bubble is open.
  learn({ topic }) {
    setBody(...(document.body.classList.contains('call') ? ['call'] : [])); // full color while teaching
    wand(false);
    wizardLayer.play(WIZARD.happy, 6);
    lesson = { topic: LESSONS[topic] ? topic : null, page: 0 };
    showBubble({ title: '' });
    renderLesson();
  },

  'call-watch'({ appear }) {
    setBody('call', 'watching');
    hideBubble();
    wand(false);
    potLayer.show(0, 0); // still, not bubbling, while watching a call
    enter(appear, () => wizardLayer.play(WIZARD.focus, 4));
  },

  'call-alert'({ app, result, bubble = true, prompt = 'ask' }) {
    setBody('call');
    if (!bubble) {
      hideBubble();
      wand(false);
      return;
    }
    const ASK = {
      ask: { text: 'Do you want me to end the call?', yes: true, noLabel: 'No' },
      ending: { text: `Hanging up ${app}…`, yes: false, noLabel: null },
      failed: { text: `I couldn’t hang up. End the call in ${app}.`, yes: false, noLabel: 'OK' },
      manual: { text: `To end it, close the call in ${app}.`, yes: false, noLabel: 'OK' },
    };
    if (prompt === 'ask') {
      poof();
      wand(true);
      setTimeout(() => mode === 'call-alert' && wand(false), 2500);
    }
    wizardLayer.play(WIZARD.idle, 8);
    showBubble({
      title: 'This is likely not a real person speaking.',
      result,
      note: `Heard on ${app}. Call audio is compressed, so this is less reliable.`,
      alert: true,
      ask: ASK[prompt] ?? ASK.ask,
    });
  },
};

// Wizard <-> witch: sink into the hat, swap sheets, rise out with a poof, then
// carry on with whatever loop was playing. When hidden, just swap, so the next
// appearance is the new character. A state change mid-morph cuts it short.
let morphTo = null;
window.wizard.onCharacter((character) => {
  if (mode === 'hidden' || mode === 'vanish') {
    wizardLayer.use(character);
    return;
  }
  const resume = wizardLayer.loop;
  morphTo = character;
  wizardLayer.play(WIZARD.vanish, 20, {
    once: true,
    onDone: () => {
      finishMorph();
      poof();
      wizardLayer.play(WIZARD.appear, 20, { once: true, onDone: () => resume && wizardLayer.play(resume.frames, resume.fps) });
    },
  });
});

function finishMorph() {
  if (morphTo) wizardLayer.use(morphTo);
  morphTo = null;
}

window.wizard.onState((state) => {
  finishMorph();
  mode = state.mode;
  states[state.mode]?.(state);
});

// ---------- input: click to choose a file, drag to move, drop to analyze ----------

$('bubble-close').addEventListener('click', () => window.wizard.dismissBubble());
$('ask-yes').addEventListener('click', () => window.wizard.endCall());
$('ask-no').addEventListener('click', () => window.wizard.dismissBubble());
$('learn-more').addEventListener('click', () => window.wizard.learn('scams'));
$('lesson-back').addEventListener('click', () => {
  if (lesson.page > 0) lesson.page -= 1;
  else lesson.topic = null; // back to the topic list
  renderLesson();
});
$('lesson-next').addEventListener('click', () => {
  const pages = LESSONS[lesson.topic].pages;
  if (lesson.page < pages.length - 1) {
    lesson.page += 1;
  } else {
    // Last page: offer the next topic, or return to the list after the last one.
    const next = LESSON_TOPICS[LESSON_TOPICS.indexOf(lesson.topic) + 1];
    lesson = { topic: next ?? null, page: 0 };
  }
  renderLesson();
});
$('stage').addEventListener('contextmenu', (e) => {
  e.preventDefault();
  window.wizard.contextMenu();
});

// ---------- learn mode ----------

let lesson = { topic: null, page: 0 };

function renderLesson() {
  $('bubble-score').hidden = true;
  $('bubble-note').textContent = '';
  $('bubble-ask').hidden = true;
  $('learn-more').hidden = true;
  $('lesson').hidden = false;

  const topics = $('lesson-topics');
  topics.replaceChildren();
  if (!lesson.topic) {
    $('bubble-title').textContent = 'What would you like to learn?';
    $('lesson-text').textContent = 'Voice cloning scams are rising. A few minutes here can protect you and the people you love.';
    for (const key of LESSON_TOPICS) {
      const b = document.createElement('button');
      b.className = 'btn topic-btn';
      b.textContent = LESSONS[key].title;
      b.addEventListener('click', () => {
        lesson = { topic: key, page: 0 };
        renderLesson();
      });
      topics.append(b);
    }
    $('lesson-nav').hidden = true;
  } else {
    const { title, pages } = LESSONS[lesson.topic];
    const last = lesson.page === pages.length - 1;
    const nextTopic = LESSON_TOPICS[LESSON_TOPICS.indexOf(lesson.topic) + 1];
    $('bubble-title').textContent = title;
    $('lesson-text').textContent = pages[lesson.page];
    $('lesson-page').textContent = `${lesson.page + 1} / ${pages.length}`;
    $('lesson-next').textContent = !last ? 'Next' : nextTopic ? 'Next topic' : 'All topics';
    $('lesson-nav').hidden = false;
  }
  placeBubble();
}

const wiz = $('stage');
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
// The preload sends the dropped file to main; this only clears the glow.
document.addEventListener('drop', () => document.body.classList.remove('drop-hover'));
