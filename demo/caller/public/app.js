// Phone remote for server.js. Keeps the token (from ?t=) in localStorage.
const $ = (id) => document.getElementById(id);

const params = new URLSearchParams(location.search);
let token = params.get('t');
try {
  if (token) localStorage.setItem('caller-token', token);
  else token = localStorage.getItem('caller-token');
} catch {}

let cfg = null;
let platform = null;
let flash = null; // { text, error, until }

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { 'X-Token': token || '', 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const out = await res.json().catch(() => ({}));
  if (res.status === 401) $('auth').hidden = false;
  if (!res.ok) throw new Error(out.error || `HTTP ${res.status}`);
  return out;
}

function say(text, error = false) {
  flash = { text, error, until: Date.now() + 4000 };
  renderStatus(null);
}

async function act(fn) {
  try {
    await fn();
  } catch (err) {
    say(err.message, true);
  }
}

function renderPlatforms() {
  const box = $('platforms');
  box.replaceChildren();
  for (const p of cfg.platforms) {
    const b = document.createElement('button');
    b.textContent = p.label;
    b.className = p.id === platform ? 'on' : '';
    b.onclick = () => {
      platform = p.id;
      try {
        localStorage.setItem('caller-platform', p.id);
      } catch {}
      renderPlatforms();
    };
    box.append(b);
  }
  const p = cfg.platforms.find((x) => x.id === platform);
  $('dial').textContent = p?.canDial ? `Call on ${p.label}` : 'Call (dial by hand)';
  $('hangup').disabled = !p?.canHangUp;
  $('platform-note').textContent = p?.note || '';
}

function renderCallers() {
  const box = $('callers');
  box.replaceChildren();
  for (const c of cfg.callers) {
    const b = document.createElement('button');
    b.className = 'card';
    b.dataset.id = c.id;
    b.disabled = !c.ready;
    b.innerHTML = '<span class="name"></span><span class="meta"></span><span class="bar"><i></i></span>';
    b.querySelector('.name').textContent = c.label;
    b.querySelector('.meta').textContent = c.ready
      ? [c.subtitle, c.hasVideo && cfg.video ? 'has video' : ''].filter(Boolean).join(' · ')
      : 'clip missing on the laptop';
    b.onclick = () =>
      act(async () => {
        const { duration } = await api('POST', '/api/play', { caller: c.id, video: $('video').checked });
        say(`Playing ${c.label} (${duration.toFixed(0)} s)`);
      });
    box.append(b);
  }
}

function renderStatus(st) {
  if (st) {
    document.querySelectorAll('.card').forEach((el) => {
      const on = st.playing?.id === el.dataset.id;
      el.classList.toggle('playing', on);
      const pct = on && st.playing.duration ? Math.min(100, (st.playing.elapsed / st.playing.duration) * 100) : 0;
      el.querySelector('.bar i').style.width = `${pct}%`;
    });
  }
  const el = $('status');
  if (flash && Date.now() < flash.until) {
    el.textContent = flash.text;
    el.className = `status${flash.error ? ' error' : ''}`;
  } else if (st) {
    const c = st.playing && cfg.callers.find((x) => x.id === st.playing.id);
    el.textContent = c ? `On air: ${c.label}` : st.lastError ? `Last error: ${st.lastError}` : 'Ready.';
    el.className = `status${c ? ' live' : st.lastError ? ' error' : ''}`;
  }
}

$('dial').onclick = () =>
  act(async () => {
    const out = await api('POST', '/api/dial', { platform, video: $('video').checked });
    say(out.dialed ? (out.note ? `Dialing… ${out.note}` : 'Dialing… answer on the judge’s laptop.') : out.note);
  });
$('hangup').onclick = () => act(() => api('POST', '/api/hangup', { platform }).then(() => say('Hung up.')));
$('stop').onclick = () => act(() => api('POST', '/api/stop').then(() => say('Stopped.')));

async function poll() {
  try {
    renderStatus(await api('GET', '/api/status'));
  } catch {}
  setTimeout(poll, 700);
}

act(async () => {
  cfg = await api('GET', '/api/config');
  try {
    platform = localStorage.getItem('caller-platform');
  } catch {}
  if (!cfg.platforms.some((p) => p.id === platform)) platform = cfg.platforms[0]?.id ?? null;
  $('video-row').hidden = !cfg.video;
  renderPlatforms();
  renderCallers();
  poll();
});
