// The hang-up spell, outside the wizard's window. A bolt leaves the wand and
// hits the call window, which turns to crystal tile by tile; the call app
// quits behind the crystal; then the crystal shatters in a burst of poof
// clouds and sparkles. Drawn in a transparent, click-through window over the
// call's display (src/main/obliterate.js). Main sends the cast and the
// shatter; the page says when it's done.
//
// Pixel look: the canvas is half the window's size and scaled up, so every
// canvas pixel is a 2x2 block like the sprites' pixels. 3D look: full
// resolution, smooth, glowing.

// Endesga 32, the sprites' palette; the clouds use the poof sheet's colors.
const PAL = {
  ink: '#181425',
  slate: '#3a4466',
  steel: '#5a6988',
  plum: '#68386c',
  magenta: '#b55088',
  pink: '#f6757a',
  gold: '#feae34',
  yellow: '#fee761',
  white: '#ffffff',
  cloud: ['#a8b5b2', '#c7cfcc', '#ebede9'],
};

// ms from the cast. The window is fully covered at BOLT + COVER + JITTER.
const BOLT = 200;
const COVER = 520;
const JITTER = 90;
const COVERED = BOLT + COVER + JITTER;
const MIN_HOLD = 220; // keep the crystal up at least this long
const MAX_HOLD = 1800; // shatter by then even if main hasn't asked
const SHATTER = 1250;

const canvas = document.getElementById('fx');
const ctx = canvas.getContext('2d');
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
let current = null; // the spell being drawn (not window.spell, the bridge)

const rand = (a, b) => a + Math.random() * (b - a);
const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const easeOut = (t) => 1 - (1 - t) ** 3;
const easeIn = (t) => t * t;

window.spell.onCast((cast) => start(cast));
window.spell.onShatter(() => {
  if (current) current.shatterAsked ??= performance.now() - current.start;
});

// ---------- setup ----------

// cast: { from: {x, y}, rect: {x, y, width, height}, view: {width, height},
// style: '2d' | '3d', snapshot: data URL | null }, all in window px.
function start({ from, rect, view, style, snapshot }) {
  const pixel = style !== '3d';
  const k = pixel ? 0.5 : devicePixelRatio || 1; // canvas px per window px
  canvas.width = Math.round(view.width * k);
  canvas.height = Math.round(view.height * k);
  canvas.classList.toggle('pixel', pixel);
  ctx.imageSmoothingEnabled = !pixel;

  const r = { x: rect.x * k, y: rect.y * k, w: rect.width * k, h: rect.height * k };
  const impact = { x: r.x + r.w * 0.42, y: r.y + r.h * 0.42 };
  const size = pixel ? 12 : Math.round(26 * k);
  const dmax = Math.max(
    ...[[r.x, r.y], [r.x + r.w, r.y], [r.x, r.y + r.h], [r.x + r.w, r.y + r.h]].map(([x, y]) => Math.hypot(x - impact.x, y - impact.y)),
  );

  const tiles = [];
  for (let ty = 0; ty < r.h; ty += size) {
    for (let tx = 0; tx < r.w; tx += size) {
      const w = Math.min(size, r.w - tx);
      const h = Math.min(size, r.h - ty);
      const x = r.x + tx;
      const y = r.y + ty;
      const d = Math.hypot(x + w / 2 - impact.x, y + h / 2 - impact.y);
      const dir = Math.atan2(y + h / 2 - impact.y, x + w / 2 - impact.x);
      const speed = rand(260, 780) * (0.35 + 0.65 * (1 - d / dmax)) * k; // near the hit flies fastest
      tiles.push({
        x, y, w, h, tx, ty, d,
        at: BOLT + COVER * (d / dmax) + rand(0, JITTER), // when the crystal reaches it
        delay: (d / dmax) * 160, // it breaks from the middle out
        vx: Math.cos(dir) * speed + rand(-60, 60) * k,
        vy: Math.sin(dir) * speed - rand(120, 340) * k,
        spin: rand(-9, 9),
        life: rand(700, 1150),
        variant: Math.random() < 0.72 ? 0 : Math.random() < 0.6 ? 1 : 2,
      });
    }
  }

  current = {
    pixel, k, r, impact, size, dmax, tiles,
    from: { x: from.x * k, y: from.y * k },
    cracks: makeCracks(impact, r, 9),
    sprites: makeTileSprites(size, pixel),
    sparks: [],
    puffs: [],
    snap: null,
    bolt: null,
    boltRolled: 0,
    start: performance.now(),
    shatterAsked: null,
    shatterAt: null,
    calm: reduceMotion.matches,
  };
  if (snapshot) loadSnapshot(snapshot, current);
  requestAnimationFrame(frame);
}

// The call window's own pixels (only for the demo's simulated call, which is
// our window), so the tiles are pieces of it.
function loadSnapshot(url, s) {
  const img = new Image();
  img.onload = () => {
    const c = Object.assign(document.createElement('canvas'), { width: Math.round(s.r.w), height: Math.round(s.r.h) });
    const x = c.getContext('2d');
    x.imageSmoothingEnabled = !s.pixel;
    x.drawImage(img, 0, 0, c.width, c.height);
    s.snap = c;
  };
  img.src = url;
}

// Crystal tiles: a lit face, a light top-left edge, a dark bottom-right edge.
// Three stones (plum, slate, magenta) plus a white flash and, for snapshot
// tiles, just the edges.
function makeTileSprites(size, pixel) {
  const stones = [
    [PAL.plum, PAL.magenta, PAL.ink],
    [PAL.slate, PAL.steel, PAL.ink],
    [PAL.magenta, PAL.pink, PAL.plum],
  ];
  const make = (paint) => {
    const c = Object.assign(document.createElement('canvas'), { width: size, height: size });
    paint(c.getContext('2d'));
    return c;
  };
  const edges = (x, light, dark, e) => {
    x.fillStyle = light;
    x.fillRect(0, 0, size, e);
    x.fillRect(0, 0, e, size);
    x.fillStyle = dark;
    x.fillRect(0, size - e, size, e);
    x.fillRect(size - e, 0, e, size);
  };
  const e = pixel ? 1 : Math.max(1, Math.round(size / 20));
  const stone = ([base, light, dark]) =>
    make((x) => {
      if (pixel) {
        x.fillStyle = base;
        x.fillRect(0, 0, size, size);
        x.fillStyle = light; // a facet catching the light
        for (let i = 0; i < size / 2; i++) x.fillRect(e, e + i, size / 2 - i, 1);
      } else {
        const g = x.createLinearGradient(0, 0, size, size);
        g.addColorStop(0, light);
        g.addColorStop(0.45, base);
        g.addColorStop(1, dark);
        x.fillStyle = g;
        x.fillRect(0, 0, size, size);
      }
      edges(x, light, dark, e);
      x.fillStyle = PAL.white;
      x.globalAlpha = pixel ? 1 : 0.75;
      x.fillRect(e * 2, e * 2, e * 2, e); // glint
      x.fillRect(e * 2, e * 2, e, e * 2);
    });
  return {
    stones: stones.map(stone),
    flash: make((x) => {
      x.fillStyle = PAL.white;
      x.fillRect(0, 0, size, size);
    }),
    edges: make((x) => {
      x.globalAlpha = 0.85;
      edges(x, 'rgba(246,117,122,0.9)', PAL.ink, e);
    }),
  };
}

// Cracks running out from the hit, with a few forks.
function makeCracks(o, r, n) {
  const inside = (x, y) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
  const step = Math.max(r.w, r.h) / 14;
  const run = (x, y, a, max) => {
    const pts = [{ x, y, d: Math.hypot(x - o.x, y - o.y) }];
    for (let i = 0; i < max && inside(x, y); i++) {
      a += rand(-0.45, 0.45);
      x += Math.cos(a) * step * rand(0.6, 1.25);
      y += Math.sin(a) * step * rand(0.6, 1.25);
      pts.push({ x, y, d: Math.hypot(x - o.x, y - o.y) });
    }
    return pts;
  };
  const cracks = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + rand(-0.25, 0.25);
    const main = run(o.x, o.y, a, 40);
    cracks.push(main);
    if (main.length > 3 && Math.random() < 0.7) {
      const p = main[1 + Math.floor(Math.random() * (main.length - 2))];
      cracks.push(run(p.x, p.y, a + pick([-1, 1]) * rand(0.5, 1.1), 3));
    }
  }
  return cracks;
}

// ---------- drawing helpers (canvas px) ----------

function line(s, x0, y0, x1, y1, w, color, a = 1) {
  ctx.globalAlpha = a;
  if (s.pixel) {
    ctx.fillStyle = color;
    const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0)));
    const o = Math.floor(w / 2);
    for (let i = 0; i <= n; i++) {
      ctx.fillRect(Math.round(x0 + ((x1 - x0) * i) / n) - o, Math.round(y0 + ((y1 - y0) * i) / n) - o, w, w);
    }
  } else {
    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function disk(s, x, y, r, color, a = 1) {
  if (r <= 0) return;
  ctx.globalAlpha = a;
  ctx.fillStyle = color;
  if (s.pixel) {
    const R = Math.round(r);
    for (let dy = -R; dy <= R; dy++) {
      const hw = Math.round(Math.sqrt(Math.max(0, R * R - dy * dy)));
      ctx.fillRect(Math.round(x) - hw, Math.round(y) + dy, hw * 2 + 1, 1);
    }
  } else {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function ring(s, x, y, r, w, color, a = 1) {
  if (s.pixel) {
    ctx.globalAlpha = a;
    ctx.fillStyle = color;
    const n = Math.max(12, Math.ceil(r * 7));
    for (let i = 0; i < n; i++) {
      const t = (i / n) * Math.PI * 2;
      ctx.fillRect(Math.round(x + Math.cos(t) * r), Math.round(y + Math.sin(t) * r), w, w);
    }
    ctx.globalAlpha = 1;
  } else {
    ctx.globalAlpha = a;
    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
}

function star(s, x, y, r, color, a = 1) {
  ctx.globalAlpha = a;
  ctx.fillStyle = color;
  if (s.pixel) {
    const X = Math.round(x);
    const Y = Math.round(y);
    const R = Math.max(1, Math.round(r));
    ctx.fillRect(X - R, Y, R * 2 + 1, 1);
    ctx.fillRect(X, Y - R, 1, R * 2 + 1);
    ctx.fillStyle = PAL.white;
    ctx.fillRect(X, Y, 1, 1);
  } else {
    const w = Math.max(1, r * 0.22);
    ctx.fillRect(x - r, y - w / 2, r * 2, w);
    ctx.fillRect(x - w / 2, y - r, w, r * 2);
    ctx.fillStyle = PAL.white;
    ctx.beginPath();
    ctx.arc(x, y, w, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function spark(s, x, y, vx, vy) {
  s.sparks.push({ x, y, vx, vy, born: performance.now(), life: rand(500, 1000), color: pick([PAL.yellow, PAL.gold, PAL.pink, PAL.white]), size: rand(1.5, 3.5) * (s.pixel ? 1 : 2 * s.k) });
}

// ---------- the frame ----------

function frame(now) {
  const s = current;
  if (!s) return;
  const t = now - s.start;

  if (s.shatterAt == null) {
    const asked = s.shatterAsked != null && t >= COVERED + MIN_HOLD;
    if (asked || t >= COVERED + MAX_HOLD) boom(s, t);
  }
  if (s.shatterAt != null && t > s.shatterAt + SHATTER) {
    finish();
    return;
  }

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!s.calm) {
    const shake = Math.max(0, 1 - (t - BOLT) / 320) * (t >= BOLT ? 1 : 0) + (s.shatterAt != null ? Math.max(0, 1 - (t - s.shatterAt) / 300) : 0);
    if (shake > 0) {
      const a = shake * (s.pixel ? 3 : 8 * s.k);
      ctx.translate(Math.round(rand(-a, a)), Math.round(rand(-a, a)));
    }
  }

  drawTiles(s, t);
  if (s.shatterAt == null) drawCracks(s, t);
  drawImpact(s, t);
  if (!s.calm && t < BOLT + 160) drawBolt(s, t, now);
  drawPuffs(s, now);
  drawSparks(s, now);
  requestAnimationFrame(frame);
}

function drawTiles(s, t) {
  const { tiles, sprites, snap, r } = s;
  const glint = s.shatterAt == null && t > COVERED ? ((t - COVERED) / 750) % 1.6 - 0.3 : null;
  for (const tile of tiles) {
    if (t < tile.at) continue;
    const since = t - tile.at;
    let x = tile.x;
    let y = tile.y;
    let a = s.calm ? clamp01(since / 200) : 1;
    let scale = 1;
    let angle = 0;
    if (s.shatterAt != null) {
      const u = (t - s.shatterAt - tile.delay) / 1000; // seconds in flight
      if (u > 0) {
        const prog = (u * 1000) / tile.life;
        if (prog >= 1) continue;
        if (s.calm) {
          a = 1 - prog;
        } else {
          x += tile.vx * u;
          y += tile.vy * u + 0.5 * 1500 * s.k * u * u;
          a = prog > 0.65 ? 1 - (prog - 0.65) / 0.35 : 1;
          scale = 1 - prog * 0.6;
          angle = tile.spin * u;
          if (s.pixel && prog > 0.7 && Math.floor(t / 50) % 2) continue; // flicker out
        }
      }
    }
    ctx.globalAlpha = a;
    const img = snap ? null : sprites.stones[tile.variant];
    if (s.pixel || !angle) {
      const w = s.pixel ? Math.max(1, Math.round(tile.w * scale)) : tile.w * scale;
      const h = s.pixel ? Math.max(1, Math.round(tile.h * scale)) : tile.h * scale;
      const dx = s.pixel ? Math.round(x + (tile.w - w) / 2) : x + (tile.w - w) / 2;
      const dy = s.pixel ? Math.round(y + (tile.h - h) / 2) : y + (tile.h - h) / 2;
      paintTile(s, tile, img, dx, dy, w, h, since);
    } else {
      ctx.save();
      ctx.translate(x + tile.w / 2, y + tile.h / 2);
      ctx.rotate(angle);
      ctx.scale(Math.cos(angle * 0.7) * scale, scale); // tumbling
      paintTile(s, tile, img, -tile.w / 2, -tile.h / 2, tile.w, tile.h, since);
      ctx.restore();
    }
    if (glint != null) {
      const p = (tile.tx + tile.ty) / (r.w + r.h);
      if (Math.abs(p - glint) < 0.035) {
        ctx.globalAlpha = 0.45;
        ctx.drawImage(sprites.flash, 0, 0, tile.w, tile.h, x, y, tile.w, tile.h);
      }
    }
  }
  ctx.globalAlpha = 1;
}

function paintTile(s, tile, img, x, y, w, h, since) {
  const { sprites, snap } = s;
  if (snap) {
    ctx.drawImage(snap, tile.tx, tile.ty, tile.w, tile.h, x, y, w, h);
    ctx.drawImage(sprites.edges, 0, 0, tile.w, tile.h, x, y, w, h);
  } else {
    ctx.drawImage(img, 0, 0, tile.w, tile.h, x, y, w, h);
  }
  if (since < 90 && !s.calm) {
    const a = ctx.globalAlpha;
    ctx.globalAlpha = a * (1 - since / 90);
    ctx.drawImage(sprites.flash, 0, 0, tile.w, tile.h, x, y, w, h);
    ctx.globalAlpha = a;
  }
}

function drawCracks(s, t) {
  if (s.calm || t < BOLT) return;
  const R = s.dmax * clamp01((t - BOLT) / COVER) * 1.05;
  const w = s.pixel ? 1 : Math.max(1.5, 2 * s.k);
  ctx.save();
  ctx.beginPath();
  ctx.rect(s.r.x, s.r.y, s.r.w, s.r.h);
  ctx.clip();
  for (const pts of s.cracks) {
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i - 1];
      let q = pts[i];
      if (p.d > R) break;
      if (q.d > R) {
        const f = (R - p.d) / Math.max(1e-3, q.d - p.d);
        q = { x: p.x + (q.x - p.x) * f, y: p.y + (q.y - p.y) * f };
      }
      line(s, p.x + w, p.y + w, q.x + w, q.y + w, w, PAL.pink, 0.9); // lit edge
      line(s, p.x, p.y, q.x, q.y, w, PAL.ink);
    }
  }
  ctx.restore();
}

function drawBolt(s, t, now) {
  const { from, impact } = s;
  const head = clamp01(t / BOLT);
  const hx = from.x + (impact.x - from.x) * easeIn(head);
  const hy = from.y + (impact.y - from.y) * easeIn(head);
  if (!s.bolt || now - s.boltRolled > 45) {
    // re-roll the zigzag so it crackles
    s.boltRolled = now;
    const len = Math.hypot(impact.x - from.x, impact.y - from.y);
    const n = Math.max(3, Math.ceil(len / (s.pixel ? 14 : 30 * s.k)));
    const jag = s.pixel ? 6 : 14 * s.k;
    const nx = -(impact.y - from.y) / len;
    const ny = (impact.x - from.x) / len;
    s.bolt = Array.from({ length: n + 1 }, (_, i) => {
      const f = i / n;
      const off = i === 0 || i === n ? 0 : rand(-1, 1) * jag * Math.sin(f * Math.PI);
      return { f, off, nx, ny };
    });
  }
  const fade = t > BOLT ? 1 - (t - BOLT) / 160 : 1;
  // Points along from -> impact, cut off at the head.
  const pts = [];
  for (const b of s.bolt) {
    if (b.f > easeIn(head) + 1e-6) break;
    pts.push({ x: from.x + (impact.x - from.x) * b.f + b.nx * b.off, y: from.y + (impact.y - from.y) * b.f + b.ny * b.off });
  }
  pts.push({ x: hx, y: hy });
  const widths = s.pixel ? [[5, PAL.magenta, 0.9], [3, PAL.pink, 1], [1, PAL.white, 1]] : [[12 * s.k, PAL.magenta, 0.55], [6 * s.k, PAL.pink, 0.9], [2.5 * s.k, PAL.white, 1]];
  if (!s.pixel) {
    ctx.save();
    ctx.shadowColor = PAL.magenta;
    ctx.shadowBlur = 24 * s.k;
  }
  for (const [w, color, a] of widths) {
    for (let i = 1; i < pts.length; i++) line(s, pts[i - 1].x, pts[i - 1].y, pts[i].x, pts[i].y, w, color, a * fade);
  }
  if (!s.pixel) ctx.restore();
  if (t < BOLT) {
    star(s, hx, hy, s.pixel ? 5 : 16 * s.k, PAL.yellow);
    if (Math.random() < 0.6) spark(s, hx, hy, rand(-80, 80) * s.k, rand(-80, 40) * s.k);
  }
}

function drawImpact(s, t) {
  if (t < BOLT) return;
  const u = (t - BOLT) / 420;
  if (u >= 1) return;
  const { impact, r } = s;
  const big = Math.max(r.w, r.h);
  if (!s.calm) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(r.x, r.y, r.w, r.h);
    ctx.clip();
    ctx.globalAlpha = 0.8 * (1 - u) ** 2; // the window flashes white
    ctx.fillStyle = PAL.white;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.restore();
    ctx.globalAlpha = 1;
    ring(s, impact.x, impact.y, big * 0.7 * easeOut(u), s.pixel ? 2 : 5 * s.k, PAL.yellow, 1 - u);
    ring(s, impact.x, impact.y, big * 0.45 * easeOut(u), s.pixel ? 1 : 3 * s.k, PAL.magenta, 1 - u);
  }
  disk(s, impact.x, impact.y, (s.pixel ? 16 : 40 * s.k) * (1 - u), PAL.white, 1 - u);
}

function drawPuffs(s, now) {
  s.puffs = s.puffs.filter((p) => {
    const age = now - p.born;
    if (age < 0) return true;
    const u = age / p.life;
    if (u >= 1) return false;
    const grow = easeOut(clamp01(age / 240));
    const rise = u * 30 * s.k;
    const a = u > 0.55 ? 1 - (u - 0.55) / 0.45 : 1;
    for (const b of p.blobs) {
      const x = p.x + b.dx * grow;
      const y = p.y + b.dy * grow - rise;
      const rr = b.r * grow * (1 + u * 0.25);
      disk(s, x + rr * 0.15, y + rr * 0.15, rr, PAL.cloud[0], a); // shade
      disk(s, x, y, rr * 0.85, PAL.cloud[1], a);
      disk(s, x - rr * 0.3, y - rr * 0.3, rr * 0.45, PAL.cloud[2], a); // light
    }
    return true;
  });
}

function drawSparks(s, now) {
  if (!s.pixel) ctx.globalCompositeOperation = 'lighter';
  s.sparks = s.sparks.filter((p) => {
    const u = (now - p.born) / p.life;
    if (u >= 1) return false;
    const sec = (now - p.born) / 1000;
    star(s, p.x + p.vx * sec, p.y + p.vy * sec + 0.5 * 500 * s.k * sec * sec, p.size * (1 - u * 0.5), p.color, 1 - u * u);
    return true;
  });
  ctx.globalCompositeOperation = 'source-over';
}

// ---------- shatter ----------

function boom(s, t) {
  s.shatterAt = t;
  if (s.calm) return;
  const now = performance.now();
  const { impact, r, k } = s;
  const puff = (x, y, size, delay) => {
    const blobs = Array.from({ length: 6 }, () => ({ dx: rand(-1, 1) * size * 0.7, dy: rand(-0.6, 0.6) * size * 0.6, r: size * rand(0.35, 0.6) }));
    s.puffs.push({ x, y, blobs, born: now + delay, life: rand(750, 1000) });
  };
  const unit = s.pixel ? 1 : 2 * k; // canvas px per pixel-look px
  puff(impact.x, impact.y, 34 * unit, 0);
  for (let i = 0; i < 7; i++) puff(r.x + rand(0.1, 0.9) * r.w, r.y + rand(0.1, 0.9) * r.h, rand(16, 28) * unit, rand(40, 220));
  for (let i = 0; i < 60; i++) {
    const a = rand(0, Math.PI * 2);
    const v = rand(150, 600) * k;
    spark(s, impact.x, impact.y, Math.cos(a) * v, Math.sin(a) * v - 120 * k);
  }
}

function finish() {
  current = null;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  window.spell.done();
}
