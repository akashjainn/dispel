// Canvas sprite stage, same layout as focus-wizard: every sheet is a grid of
// 80x128 frames, and all layers are drawn at the SAME position on an 80x120
// canvas (frames start 8px above the top). The art is drawn to line up, so the
// wizard stands in the cauldron's stew with no offsets or clipping. The canvas
// is scaled up with CSS (see .stage in wizard.css).

const FRAME_W = 80;
const FRAME_H = 128;
const CANVAS_W = 80;
const CANVAS_H = 120;
const ORIGIN_X = Math.floor((CANVAS_W - FRAME_W) / 2); // 0
const ORIGIN_Y = CANVAS_H - FRAME_H; // -8

class Stage {
  constructor(canvas) {
    this.ctx = canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;
    this.layers = []; // drawn in order: first is at the back
    this.pending = false;
  }

  // src is one sheet, or { key: src } for a layer that can switch sheets with
  // use(key) (all load up front, so a switch never shows a blank frame).
  // recolor(ImageData) may edit each sheet's pixels once, after it loads.
  add(src, recolor) {
    const layer = new SpriteLayer(this, src, recolor);
    this.layers.push(layer);
    return layer;
  }

  requestDraw() {
    if (this.pending) return;
    this.pending = true;
    requestAnimationFrame(() => {
      this.pending = false;
      this.ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
      for (const l of this.layers) l.draw(this.ctx);
    });
  }
}

// Loads a sheet into a canvas, recolored if asked. Calls done(canvas).
function loadSheet(src, recolor, done) {
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    if (recolor) {
      const data = ctx.getImageData(0, 0, c.width, c.height);
      recolor(data);
      ctx.putImageData(data, 0, 0);
    }
    done(c);
  };
  img.onerror = () => console.error('[sprites] could not load', src);
  img.src = src;
}

class SpriteLayer {
  constructor(stage, src, recolor) {
    this.stage = stage;
    const srcs = typeof src === 'string' ? { main: src } : src;
    this.keys = Object.keys(srcs);
    this.key = this.keys[0];
    this.sheets = {}; // key -> canvas, once loaded
    for (const [key, s] of Object.entries(srcs)) {
      loadSheet(s, recolor, (c) => {
        this.sheets[key] = c;
        if (key === this.key) stage.requestDraw();
      });
    }
    this.frame = null; // [col, row] or null when hidden
    this.timer = null;
    this.loop = null; // the last looping animation, { frames, fps }
  }

  // Switch to another sheet; the current animation carries on from the same frame.
  use(key) {
    if (!this.keys.includes(key) || key === this.key) return;
    this.key = key;
    this.stage.requestDraw();
  }

  draw(ctx) {
    const img = this.sheets[this.key];
    if (!this.frame || !img) return;
    const [col, row] = this.frame;
    ctx.drawImage(img, col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H, ORIGIN_X, ORIGIN_Y, FRAME_W, FRAME_H);
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
