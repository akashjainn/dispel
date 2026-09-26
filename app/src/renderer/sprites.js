// Canvas sprite stage, same layout as focus-wizard: every sheet is a grid of
// 80x128 frames, and all layers are drawn at the SAME position on an 80x120
// stage (frames start 8px above the top). The art is drawn to line up, so the
// wizard stands in the cauldron's stew with no offsets or clipping.
//
// The canvas is 4x that (320x480) and shown at 160x240 CSS px (see .stage in
// wizard.css). Pixel sheets are drawn 4x with nearest-neighbor, so they stay
// crisp; the 3D sheets (Assets/3d/, made by scripts/make_3d_sprites.py) are
// already 4x and draw 1:1.

const FRAME_W = 80;
const FRAME_H = 128;
const STAGE_W = 80;
const STAGE_H = 120;
const SCALE = 4; // canvas pixels per stage pixel
const CANVAS_W = STAGE_W * SCALE;
const CANVAS_H = STAGE_H * SCALE;
const ORIGIN_X = Math.floor((STAGE_W - FRAME_W) / 2) * SCALE; // 0
const ORIGIN_Y = (STAGE_H - FRAME_H) * SCALE; // -32

const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const offscreen = () => Object.assign(document.createElement('canvas'), { width: CANVAS_W, height: CANVAS_H });

class Stage {
  constructor(canvas) {
    this.ctx = canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;
    this.layers = []; // drawn in order: first is at the back
    this.pending = false;
    this.sweep = null; // an in-progress look change, see sweepTo()
    this.sparks = [];
    this.buf = { from: offscreen(), to: offscreen(), glow: offscreen() };
    // Effects (magic.js): { pass: 'under' | 'over' | 'glow', draw(ctx, now, pixel) -> keep? },
    // drawn in stage pixels. In the pixel look they're drawn on an 80x120
    // canvas and scaled up like the art; in the 3D look, smooth at 4x.
    this.fx = [];
    this.pixel = true;
    this.buf.px = Object.assign(document.createElement('canvas'), { width: STAGE_W, height: STAGE_H });
    this.shakeFx = null; // { amp, start, ms }: the whole stage trembles
  }

  addFx(fx) {
    this.fx.push(fx);
    this.requestDraw();
    return fx;
  }

  // Shake the stage for ms, amp stage pixels at the start, fading out.
  shake(amp, ms) {
    this.shakeFx = { amp, start: performance.now(), ms };
    this.requestDraw();
  }

  // src is one sheet, or { key: sheet } for a layer that can switch sheets
  // with use(key). A sheet is a path (pixel art, 1x) or { src, scale }.
  // recolor(ImageData) edits a pixel sheet's pixels once, after it loads.
  add(src, recolor) {
    const layer = new SpriteLayer(this, src, recolor);
    this.layers.push(layer);
    return layer;
  }

  requestDraw() {
    if (this.pending) return;
    this.pending = true;
    requestAnimationFrame((now) => {
      this.pending = false;
      this.render(now);
      if (this.sweep || this.sparks.length || this.fx.length || this.shakeFx) this.requestDraw(); // keep effects moving
    });
  }

  render(now) {
    const { ctx } = this;
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    ctx.save();
    const sh = this.shakeFx;
    if (sh) {
      const t = (now - sh.start) / sh.ms;
      if (t >= 1) this.shakeFx = null;
      else {
        const a = sh.amp * SCALE * (1 - t);
        const step = this.pixel ? SCALE : 1; // the pixel look shakes by whole art pixels
        ctx.translate(Math.round(((Math.random() * 2 - 1) * a) / step) * step, Math.round(((Math.random() * 2 - 1) * a) / step) * step);
      }
    }
    this.renderFx(now, 'under');
    if (this.sweep) this.renderSweep(now);
    else for (const l of this.layers) l.draw(ctx);
    this.renderFx(now, 'over');
    this.renderFx(now, 'glow');
    this.renderSparks(now);
    ctx.restore();
  }

  renderFx(now, pass) {
    const list = this.fx.filter((f) => (f.pass || 'over') === pass);
    if (!list.length) return;
    const { ctx } = this;
    const done = new Set();
    const run = (c) => {
      for (const f of list) if (f.draw(c, now, this.pixel) === false) done.add(f);
    };
    ctx.save();
    if (pass === 'glow') ctx.globalCompositeOperation = 'lighter';
    if (this.pixel) {
      const b = this.buf.px.getContext('2d');
      b.clearRect(0, 0, STAGE_W, STAGE_H);
      b.save();
      run(b);
      b.restore();
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(this.buf.px, 0, 0, CANVAS_W, CANVAS_H);
    } else {
      ctx.scale(SCALE, SCALE);
      run(ctx);
    }
    ctx.restore();
    if (done.size) this.fx = this.fx.filter((f) => !done.has(f));
  }

  // ---------- look change: a glowing line sweeps up from the cauldron ----------

  // apply() switches the layers to the new look (their sheets must be loaded,
  // see SpriteLayer.load). The new look rises from the bottom behind the line;
  // the old one stays above it until the line passes.
  sweepTo(apply, { duration = 900, onDone } = {}) {
    this.finishSweep();
    const from = this.layers.map((l) => l.key);
    apply();
    this.sweep = { from, start: performance.now(), duration, onDone, lastSpark: 0 };
    this.requestDraw();
  }

  finishSweep() {
    const s = this.sweep;
    if (!s) return;
    this.sweep = null;
    s.onDone?.();
  }

  renderSweep(now) {
    const s = this.sweep;
    const t = Math.min(1, (now - s.start) / s.duration);
    const band = 44; // glow height, canvas px
    const line = CANVAS_H + band - easeInOut(t) * (CANVAS_H + band * 2);
    const { from, to, glow } = this.buf;
    const draw = (c, keys) => {
      const x = c.getContext('2d');
      x.imageSmoothingEnabled = false;
      x.clearRect(0, 0, CANVAS_W, CANVAS_H);
      this.layers.forEach((l, i) => l.draw(x, keys?.[i]));
      return x;
    };
    draw(from, s.from);
    const toCtx = draw(to);

    const { ctx } = this;
    const y = Math.max(0, Math.min(CANVAS_H, Math.round(line)));
    if (y > 0) ctx.drawImage(from, 0, 0, CANVAS_W, y, 0, 0, CANVAS_W, y);
    if (y < CANVAS_H) ctx.drawImage(to, 0, y, CANVAS_W, CANVAS_H - y, 0, y, CANVAS_W, CANVAS_H - y);

    // Glow only on the art (both looks), strongest at the line.
    const g = glow.getContext('2d');
    g.globalCompositeOperation = 'source-over';
    g.clearRect(0, 0, CANVAS_W, CANVAS_H);
    g.drawImage(from, 0, 0);
    g.drawImage(to, 0, 0);
    g.globalCompositeOperation = 'source-in';
    const grad = g.createLinearGradient(0, line - band, 0, line + band);
    grad.addColorStop(0, 'rgba(183,140,255,0)');
    grad.addColorStop(0.45, 'rgba(214,190,255,0.85)');
    grad.addColorStop(0.5, 'rgba(255,255,255,1)');
    grad.addColorStop(0.55, 'rgba(214,190,255,0.85)');
    grad.addColorStop(1, 'rgba(183,140,255,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, CANVAS_W, CANVAS_H);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.drawImage(glow, 0, 0);
    ctx.restore();

    // Sparks fly off the art where the line crosses it.
    if (y > 0 && y < CANVAS_H && now - s.lastSpark > 30) {
      s.lastSpark = now;
      const row = toCtx.getImageData(0, y, CANVAS_W, 1).data;
      const solid = [];
      for (let x = 0; x < CANVAS_W; x += 4) if (row[x * 4 + 3] > 40) solid.push(x);
      for (let i = 0; i < 3 && solid.length; i++) {
        const x = solid[Math.floor(Math.random() * solid.length)];
        this.spark(x, y, { vx: (Math.random() - 0.5) * 60, vy: -40 - Math.random() * 70 });
      }
    }
    if (t >= 1) this.finishSweep();
  }

  // ---------- sparkles ----------

  spark(x, y, { vx = 0, vy = 0, life = 500 + Math.random() * 400, size = 3 + Math.random() * 4, gold = Math.random() < 0.5 } = {}) {
    this.sparks.push({ x, y, vx, vy, life, size, gold, born: performance.now() });
    this.requestDraw();
  }

  // A ring of sparkles bursting out from (x, y), in stage (1x) pixels.
  burst(x, y, count = 22) {
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2 + Math.random() * 0.3;
      const v = 90 + Math.random() * 110;
      this.spark(x * SCALE, y * SCALE, { vx: Math.cos(a) * v, vy: Math.sin(a) * v - 30, size: 4 + Math.random() * 5 });
    }
  }

  renderSparks(now) {
    const { ctx } = this;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    this.sparks = this.sparks.filter((p) => {
      const age = (now - p.born) / p.life;
      if (age >= 1) return false;
      const secs = (now - p.born) / 1000;
      const x = p.x + p.vx * secs;
      const y = p.y + p.vy * secs + 60 * secs * secs; // a little gravity
      const r = p.size * (1 - age * 0.6);
      ctx.globalAlpha = 1 - age * age;
      ctx.fillStyle = p.gold ? '#ffe27a' : '#d9c2ff';
      // four-point star: a long cross and a bright core
      ctx.fillRect(x - r, y - 1, r * 2, 2);
      ctx.fillRect(x - 1, y - r, 2, r * 2);
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
      return true;
    });
    ctx.restore();
  }
}

// Loads a sheet into a canvas, recolored if asked. Resolves to { img, scale }.
function loadSheet({ src, scale }, recolor) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.width;
      c.height = img.height;
      const ctx = c.getContext('2d', { willReadFrequently: Boolean(recolor) });
      ctx.drawImage(img, 0, 0);
      if (recolor) {
        const data = ctx.getImageData(0, 0, c.width, c.height);
        recolor(data);
        ctx.putImageData(data, 0, 0);
      }
      resolve({ img: c, scale });
    };
    img.onerror = () => reject(new Error(`could not load ${src}`));
    img.src = src;
  });
}

class SpriteLayer {
  constructor(stage, src, recolor) {
    this.stage = stage;
    const srcs = typeof src === 'string' ? { main: src } : src;
    this.specs = {}; // key -> { src, scale, recolor }
    for (const [key, s] of Object.entries(srcs)) {
      const spec = typeof s === 'string' ? { src: s, scale: 1 } : s;
      // Recolors are written for pixel sheets; 3D sheets are baked already recolored.
      this.specs[key] = { ...spec, recolor: spec.scale === 1 ? recolor : null };
    }
    this.sheets = {}; // key -> Promise of { img, scale }
    this.loaded = {}; // key -> { img, scale }, once loaded
    this.key = Object.keys(this.specs)[0];
    this.load(this.key);
    this.frame = null; // [col, row] or null when hidden
    this.timer = null;
    this.loop = null; // the last looping animation, { frames, fps }
    this.offset = { x: 0, y: 0 }; // stage px: hops, the wand rising out of the pot (magic.js)
    this.clipBelow = null; // stage y: nothing below it is drawn (the pot's front lip)
    this.swap = null; // { from, to }: draw row `to` in place of row `from` (blinks, smiles)
  }

  // Loads a sheet once (on first use); resolves when it can be drawn.
  load(key) {
    if (!this.specs[key]) return Promise.resolve();
    this.sheets[key] ??= loadSheet(this.specs[key], this.specs[key].recolor).then(
      (sheet) => {
        this.loaded[key] = sheet;
        if (key === this.key) this.stage.requestDraw();
      },
      (err) => console.error('[sprites]', err.message),
    );
    return this.sheets[key];
  }

  // Switch sheets; the current animation carries on from the same frame. Until
  // the new sheet has loaded, the old one keeps drawing (never a blank frame).
  use(key) {
    if (!this.specs[key] || key === this.key) return;
    if (this.loaded[this.key]) this.prevKey = this.key;
    this.key = key;
    this.load(key);
    this.stage.requestDraw();
  }

  draw(ctx, key = this.key) {
    const sheet = this.loaded[key] ?? this.loaded[this.prevKey];
    if (!this.frame || !sheet) return;
    let [col, row] = this.frame;
    if (this.swap && row === this.swap.from) row = this.swap.to;
    const w = FRAME_W * sheet.scale;
    const h = FRAME_H * sheet.scale;
    // Pixel sheets move by whole art pixels so they stay on the grid.
    const snap = (v) => (sheet.scale === 1 ? Math.round(v) : v) * SCALE;
    const x = ORIGIN_X + snap(this.offset.x);
    const y = ORIGIN_Y + snap(this.offset.y);
    if (this.clipBelow != null) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, CANVAS_W, this.clipBelow * SCALE);
      ctx.clip();
    }
    ctx.drawImage(sheet.img, col * w, row * h, w, h, x, y, FRAME_W * SCALE, FRAME_H * SCALE);
    if (this.clipBelow != null) ctx.restore();
  }

  show(col, row) {
    this.frame = [col, row];
    this.stage.requestDraw();
  }

  // frames: [[col, row], ...]. Loops unless `once`; calls onDone after a once run.
  play(frames, fps, { once = false, onDone } = {}) {
    this.stop();
    if (!once) this.loop = { frames, fps };
    let i = 0;
    this.show(...frames[0]);
    this.timer = setInterval(() => {
      i += 1;
      if (i >= frames.length) {
        if (once) {
          this.stop();
          onDone?.();
          return;
        }
        i = 0;
      }
      this.show(...frames[i]);
    }, 1000 / fps);
  }

  stop() {
    clearInterval(this.timer);
    this.timer = null;
  }

  hide() {
    this.stop();
    this.frame = null;
    this.stage.requestDraw();
  }
}

// ---------- recoloring: an empty cauldron, no gems, no stew ----------

const POT_INSIDE = [22, 29, 40]; // the pot's darkest outline color
// The cauldron's own colors (slate body, rim, outline, highlight). Anything else
// on the pot is stew (green and its pink bits) or a gem.
const POT_COLORS = new Set(['57,74,80', '32,46,55', '22,29,40', '21,29,40', '87,114,119']);
const isGreen = (r, g, b) => g > r + 15 && g > b;

// Stew, and everything inside the stew's outline, becomes the dark inside of an
// empty pot. Gems on the body are painted over with the pot color around them.
function emptyPot({ data, width, height }) {
  const at = (x, y) => (y * width + x) * 4;
  const key = (i) => `${data[i]},${data[i + 1]},${data[i + 2]}`;
  const setRGB = (i, [r, g, b]) => {
    data[i] = r;
    data[i + 1] = g;
    data[i + 2] = b;
    data[i + 3] = 255;
  };

  for (let fx = 0; fx < width; fx += FRAME_W) {
    // 1. Stew: fill each row between its leftmost and rightmost green pixel.
    for (let y = 0; y < height; y++) {
      let lo = -1;
      let hi = -1;
      for (let x = fx; x < fx + FRAME_W; x++) {
        const i = at(x, y);
        if (data[i + 3] && isGreen(data[i], data[i + 1], data[i + 2])) {
          if (lo < 0) lo = x;
          hi = x;
        }
      }
      for (let x = lo; lo >= 0 && x <= hi; x++) {
        const i = at(x, y);
        if (!POT_COLORS.has(key(i)) || isGreen(data[i], data[i + 1], data[i + 2])) setRGB(i, POT_INSIDE);
      }
    }
    // 2. Gems: take the most common pot color among the neighbors, repeating
    //    until every gem pixel is covered.
    for (let pass = 0; pass < 8; pass++) {
      let left = 0;
      for (let y = 0; y < height; y++) {
        for (let x = fx; x < fx + FRAME_W; x++) {
          const i = at(x, y);
          if (!data[i + 3] || POT_COLORS.has(key(i))) continue;
          const votes = new Map();
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              const nx = x + dx;
              const ny = y + dy;
              if (nx < fx || nx >= fx + FRAME_W || ny < 0 || ny >= height) continue;
              const k = key(at(nx, ny));
              if (POT_COLORS.has(k)) votes.set(k, (votes.get(k) || 0) + 1);
            }
          }
          if (!votes.size) {
            left++;
            continue;
          }
          const best = [...votes].sort((a, b) => b[1] - a[1])[0][0];
          setRGB(i, best.split(',').map(Number));
        }
      }
      if (!left) break;
    }
    // 3. Gem outlines: they use the pot's dark outline color, so step 2 leaves
    //    them behind. Paint over any dark pixel sitting on the body (3+ of its
    //    4 neighbors are body color) until none are left.
    const BODY = new Set(['57,74,80', '87,114,119']);
    for (let changed = true; changed; ) {
      changed = false;
      for (let y = 1; y < height - 1; y++) {
        for (let x = fx + 1; x < fx + FRAME_W - 1; x++) {
          const i = at(x, y);
          const k = key(i);
          if (k !== '22,29,40' && k !== '21,29,40') continue;
          const around = [at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1)].map(key);
          const body = around.filter((n) => BODY.has(n));
          if (body.length >= 3) {
            setRGB(i, body[0].split(',').map(Number));
            changed = true;
          }
        }
      }
    }
  }
}

// The wizard's hem has a dark-green stew shadow; make it the pot's inside.
function noStewShadow({ data }) {
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] && isGreen(data[i], data[i + 1], data[i + 2])) {
      data[i] = POT_INSIDE[0];
      data[i + 1] = POT_INSIDE[1];
      data[i + 2] = POT_INSIDE[2];
    }
  }
}

const row = (r, cols) => cols.map((c) => [c, r]);
const BOB = [0, 1, 2, 3, 4, 3, 2, 1];

// wizard-sprites.png rows: 0 idle, 1 smiling, 2 eyes closed, 3 sinking into
// the hat, 4 hat with rising smoke. witch-sprites.png has the same frames
// (built from the wizard's by app/scripts/make_witch_sprites.py), so both use
// this table.
const WIZARD = {
  idle: row(0, BOB),
  happy: row(1, BOB),
  focus: row(2, BOB),
  vanish: [...row(3, [0, 1, 2, 3, 4]), ...row(4, [0, 1, 2, 3, 4])],
  appear: [...row(4, [4, 3, 2, 1, 0]), ...row(3, [4, 3, 2, 1, 0])],
};
const POT = { bubble: row(0, [0, 1, 2, 3]) };
const WAND = { idle: row(0, [0, 1]), cast: row(2, [0, 1, 2, 3]) };
const POOF = { burst: [...row(0, [0, 1, 2, 3, 4, 5]), ...row(1, [0, 1, 2, 3, 4, 5])] };
