// Magic effects and the wizard's (or witch's) idle life, drawn on the sprite
// stage (sprites.js). Main still decides every state; this only makes the
// character feel alive inside it: blinks, cauldron bubbles, wand tricks,
// reactions to the pointer, and the hang-up spell.
//
// Effects are drawn in stage pixels (80x120). In the pixel look they land on
// the art's pixel grid; in the 3D look they're smooth and glow.

// Endesga 32, the palette the sprites are drawn in.
const PAL = {
  ink: '#181425',
  navy: '#262b44',
  plum: '#68386c',
  magenta: '#b55088',
  pink: '#f6757a',
  gold: '#feae34',
  yellow: '#fee761',
  white: '#ffffff',
  mist: '#c0cbdc',
  steel: '#8b9bb4',
  cyan: '#2ce8f5',
  blue: '#0099db',
  green: '#63c74d',
  red: '#e43b44',
};

// Where things are on the stage, measured on the art (stage pixels).
const AT = {
  wandTip: [21, 16], // wand-hand row 0: held up
  castTip: [10, 21], // wand-hand row 2, last cast frame: pointing up and out
  hatTip: [65, 30],
  heart: [40, 42], // middle of the character, for the aura
  mouth: { x0: 13, x1: 67, y: 76 }, // the cauldron's dark inside, in front of the robe
  lip: 79, // the pot's front lip: the wand comes up from behind it
};
const WAND_DOWN = 44; // how far below its spot the wand starts, inside the pot

// The wand star's own colors (wand-hand.png), brightest first: the wand's
// magic is drawn in these so it looks like it comes out of that star.
const WAND_STAR = ['#fee761', '#fec841', '#feae34', '#fe9e43'];

// The wand's magic moves in steps, like hand-drawn frames, not smoothly.
const STEP = 1000 / 12;
const stepped = (ms) => Math.floor(ms / STEP) * STEP;

const rand = (a, b) => a + Math.random() * (b - a);
const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const easeOut = (t) => 1 - (1 - t) ** 3;
const easeOutBack = (t) => 1 + 2.4 * (t - 1) ** 3 + 1.4 * (t - 1) ** 2;
const easeIn = (t) => t * t * t;

// ---------- drawing: each takes (ctx, pixel) and stage coordinates ----------

const draw = {
  dot(c, pixel, x, y, r, color, a = 1) {
    c.globalAlpha = a;
    c.fillStyle = color;
    if (pixel) {
      const s = Math.max(1, Math.round(r * 2));
      c.fillRect(Math.round(x - s / 2), Math.round(y - s / 2), s, s);
    } else {
      c.beginPath();
      c.arc(x, y, Math.max(0.25, r), 0, Math.PI * 2);
      c.fill();
    }
    c.globalAlpha = 1;
  },

  // Four-point sparkle, like the wand's.
  star(c, pixel, x, y, r, color, a = 1) {
    c.globalAlpha = a;
    c.fillStyle = color;
    if (pixel) {
      const X = Math.round(x);
      const Y = Math.round(y);
      const R = Math.max(1, Math.round(r));
      c.fillRect(X - R, Y, R * 2 + 1, 1);
      c.fillRect(X, Y - R, 1, R * 2 + 1);
      c.fillStyle = PAL.white;
      c.fillRect(X, Y, 1, 1);
    } else {
      const w = Math.max(0.35, r * 0.22);
      c.fillRect(x - r, y - w / 2, r * 2, w);
      c.fillRect(x - w / 2, y - r, w, r * 2);
      c.fillStyle = PAL.white;
      c.beginPath();
      c.arc(x, y, w * 1.1, 0, Math.PI * 2);
      c.fill();
    }
    c.globalAlpha = 1;
  },

  // The wand's star: long orange arms, a gold middle, a white core, and gold
  // corners once it's big. r is the arm length in stage pixels.
  wandStar(c, pixel, x, y, r) {
    if (r <= 0) return;
    const [yellow, amber, , orange] = WAND_STAR;
    const X = pixel ? Math.round(x) : x;
    const Y = pixel ? Math.round(y) : y;
    const cross = (len, w, color) => {
      c.fillStyle = color;
      c.fillRect(X - len, Y - (w - 1) / 2, len * 2 + 1, w);
      c.fillRect(X - (w - 1) / 2, Y - len, w, len * 2 + 1);
    };
    c.globalAlpha = 1;
    if (!pixel) this.glow(c, false, x, y, r * 1.6, r * 1.6, amber, 0.55);
    cross(r, 1, orange);
    if (r >= 2) cross(Math.ceil(r / 2), r >= 4 ? 3 : 1, amber);
    if (r >= 3) {
      const d = Math.floor(r / 2);
      c.fillStyle = yellow;
      for (const [dx, dy] of [[-d, -d], [d, -d], [-d, d], [d, d]]) c.fillRect(X + dx, Y + dy, 1, 1);
    }
    cross(r >= 4 ? 1 : 0, 1, yellow);
    c.fillStyle = PAL.white;
    c.fillRect(X, Y, 1, 1);
  },

  // An ellipse outline (a flat ring on the pot's mouth, or a round shockwave).
  ring(c, pixel, x, y, rx, ry, color, a = 1, w = 1) {
    c.globalAlpha = a;
    if (pixel) {
      c.fillStyle = color;
      const n = Math.max(8, Math.ceil(Math.PI * (rx + ry)));
      const seen = new Set();
      for (let i = 0; i < n; i++) {
        const t = (i / n) * Math.PI * 2;
        const px = Math.round(x + Math.cos(t) * rx);
        const py = Math.round(y + Math.sin(t) * ry);
        const k = px * 1000 + py;
        if (seen.has(k)) continue;
        seen.add(k);
        c.fillRect(px, py, w, w);
      }
    } else {
      c.strokeStyle = color;
      c.lineWidth = w * 0.8;
      c.beginPath();
      c.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), 0, 0, Math.PI * 2);
      c.stroke();
    }
    c.globalAlpha = 1;
  },

  // A soft glow. The pixel look gets hard-edged bands, like hand-drawn pixel light.
  glow(c, pixel, x, y, rx, ry, color, a = 1) {
    if (pixel) {
      c.fillStyle = color;
      for (const [k, band] of [[1, 0.22], [0.78, 0.3], [0.55, 0.42]]) {
        c.globalAlpha = a * band;
        const RY = Math.round(ry * k);
        for (let dy = -RY; dy <= RY; dy++) {
          const hw = Math.round(rx * k * Math.sqrt(1 - (dy / (RY + 0.5)) ** 2));
          c.fillRect(Math.round(x) - hw, Math.round(y) + dy, hw * 2, 1);
        }
      }
    } else {
      c.save();
      c.translate(x, y);
      c.scale(1, ry / rx);
      const g = c.createRadialGradient(0, 0, 0, 0, 0, rx);
      g.addColorStop(0, color);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      c.globalAlpha = a;
      c.fillStyle = g;
      c.beginPath();
      c.arc(0, 0, rx, 0, Math.PI * 2);
      c.fill();
      c.restore();
    }
    c.globalAlpha = 1;
  },
};

// ---------- effects: each is added to the stage and removes itself ----------

const fx = {
  // Calls fn(t) every frame for ms (t: 0..1), then done(). cancel() stops it
  // quietly. With fps, t moves in steps (a flip-book, like the sprites).
  tween(stage, ms, fn, done, fps) {
    const start = performance.now();
    const f = {
      pass: 'under', // before the layers, so a moved layer draws in its new spot
      cancelled: false,
      draw(_c, now) {
        if (f.cancelled) return false;
        const age = now - start;
        const t = clamp01((fps ? Math.floor(age / (1000 / fps)) * (1000 / fps) : age) / ms);
        fn(age >= ms ? 1 : t);
        if (age < ms) return true;
        done?.();
        return false;
      },
      cancel() {
        f.cancelled = true;
      },
    };
    return stage.addFx(f);
  },

  // A magic bubble rising out of the cauldron; it pops at the top.
  bubble(stage, { x, y = AT.mouth.y, color = PAL.mist, rise = rand(10, 22), r = rand(0.8, 1.8), life = rand(900, 1500) } = {}) {
    const born = performance.now();
    const wob = rand(0, Math.PI * 2);
    return stage.addFx({
      pass: 'over',
      draw(c, now, pixel) {
        const t = (now - born) / life;
        if (t >= 1.18) return false;
        if (t >= 1) {
          // pop: four dots flying out
          const k = (t - 1) / 0.18;
          const py = y - rise;
          for (const [dx, dy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
            draw.dot(c, pixel, x + dx * (r + 1 + k * 2.5), py + dy * (r + 1 + k * 2.5), 0.5, color, 1 - k);
          }
          return true;
        }
        const bx = x + Math.sin(wob + t * 7) * 1.2;
        const by = y - rise * easeOut(t);
        const rr = r * (0.6 + 0.4 * Math.min(1, t * 3));
        if (pixel && rr < 1.3) {
          draw.dot(c, pixel, bx, by, 0.5, color, 0.95);
        } else {
          draw.ring(c, pixel, bx, by, rr, rr, color, 0.95);
          draw.dot(c, pixel, bx - rr * 0.45, by - rr * 0.45, 0.45, PAL.white, 0.9);
        }
        return true;
      },
    });
  },

  // A flat ring spreading across the cauldron's mouth, or a round shockwave.
  ring(stage, { x, y, r0 = 2, r1 = 30, flat = 1, ms = 600, color = PAL.magenta, w = 1 }) {
    const born = performance.now();
    return stage.addFx({
      pass: 'glow',
      draw(c, now, pixel) {
        const t = (now - born) / ms;
        if (t >= 1) return false;
        const r = r0 + (r1 - r0) * easeOut(t);
        draw.ring(c, pixel, x, y, r, r * flat, color, 1 - t, w);
        return true;
      },
    });
  },

  // The wand's star flashing big and shrinking back, one frame at a time.
  starPop(stage, { x, y, sizes = [2, 4, 6, 5, 3, 2, 1] }) {
    const born = performance.now();
    return stage.addFx({
      pass: 'over',
      draw(c, now, pixel) {
        const i = Math.floor((now - born) / STEP);
        if (i >= sizes.length) return false;
        draw.wandStar(c, pixel, x, y, sizes[i]);
        return true;
      },
    });
  },

  // Specks of the wand's gold flying out of a point and falling, moved a
  // frame at a time. dir/spread in radians aim it (default: all around).
  spray(stage, { x, y, count = 12, speed = [20, 55], dir = null, spread = Math.PI, life = [380, 700] }) {
    const born = performance.now();
    const specks = Array.from({ length: count }, () => {
      const a = dir == null ? rand(0, Math.PI * 2) : dir + rand(-spread / 2, spread / 2);
      const v = rand(...speed);
      return { vx: Math.cos(a) * v, vy: Math.sin(a) * v - 10, life: rand(...life), color: pick(WAND_STAR), big: Math.random() < 0.25 };
    });
    return stage.addFx({
      pass: 'over',
      draw(c, now, pixel) {
        const age = stepped(now - born);
        let alive = false;
        for (const p of specks) {
          if (age >= p.life) continue;
          alive = true;
          const sec = age / 1000;
          const px = x + p.vx * sec;
          const py = y + p.vy * sec + 40 * sec * sec;
          if (p.big && age < p.life * 0.6) draw.star(c, pixel, px, py, 1, p.color);
          else draw.dot(c, pixel, px, py, 0.5, p.color);
        }
        return alive;
      },
    });
  },

  // A glow that follows the character: purple when it caught something,
  // cyan while it listens. stop() fades it out. Motes drift up through it.
  aura(stage, { color = PAL.magenta, strength = 1 } = {}) {
    const born = performance.now();
    let stopAt = null;
    let lastMote = 0;
    const f = stage.addFx({
      pass: 'under',
      draw(c, now, pixel) {
        const fadeIn = clamp01((now - born) / 400);
        const fadeOut = stopAt ? 1 - clamp01((now - stopAt) / 400) : 1;
        if (fadeOut <= 0) return false;
        const pulse = 0.75 + 0.25 * Math.sin(now / 260);
        const a = strength * fadeIn * fadeOut * pulse;
        draw.glow(c, pixel, AT.heart[0], AT.heart[1], 36, 40, color, a * 0.8);
        if (!stopAt && now - lastMote > 260 / strength) {
          lastMote = now;
          fx.mote(stage, { color: Math.random() < 0.5 ? color : PAL.yellow });
        }
        return true;
      },
      stop() {
        stopAt ??= performance.now();
      },
    });
    f.color = color;
    return f;
  },

  // A tiny sparkle drifting up around the character.
  mote(stage, { color = PAL.yellow } = {}) {
    const born = performance.now();
    const life = rand(900, 1600);
    const x = rand(6, 74);
    const y = rand(20, 70);
    const drift = rand(-4, 4);
    return stage.addFx({
      pass: 'glow',
      draw(c, now, pixel) {
        const t = (now - born) / life;
        if (t >= 1) return false;
        const a = Math.sin(t * Math.PI);
        draw.star(c, pixel, x + drift * t, y - 12 * t, a > 0.7 ? 1.5 : 0.8, color, a);
        return true;
      },
    });
  },

  // Specks of gold drawn in to the wand's star, which grows and twinkles
  // (the wand charging). Moves a frame at a time; stop() lets it go.
  charge(stage, x, y) {
    const born = performance.now();
    const specks = [];
    let lastStep = -1;
    let stopped = false;
    return stage.addFx({
      pass: 'over',
      draw(c, now, pixel) {
        if (stopped) return false;
        const step = Math.floor((now - born) / STEP);
        if (step !== lastStep) {
          lastStep = step;
          for (let i = 0; i < 2; i++) specks.push({ a: rand(0, Math.PI * 2), d: rand(9, 15), step, color: pick(WAND_STAR) });
        }
        for (let i = specks.length - 1; i >= 0; i--) {
          const p = specks[i];
          const t = (step - p.step) / 4; // four frames to reach the star
          if (t >= 1) {
            specks.splice(i, 1);
            continue;
          }
          const d = p.d * (1 - t);
          draw.dot(c, pixel, x + Math.cos(p.a) * d, y + Math.sin(p.a) * d, 0.5, p.color);
        }
        const size = Math.min(4, 1 + Math.floor(step / 3));
        draw.wandStar(c, pixel, x, y, step % 2 ? size : size - 1); // twinkle
        return true;
      },
      stop() {
        stopped = true;
      },
    });
  },
};

// ---------- presence: the character's life between (and during) states ----------

// layers: { wizard, wand, pot } SpriteLayers; frames: { WIZARD, WAND } tables
// from sprites.js.
class Presence {
  constructor(stage, layers) {
    this.stage = stage;
    this.l = layers;
    this.mode = 'hidden';
    this.hovered = false;
    this.seq = 0; // bumps on every state: stops any running sequence
    this.timers = new Set();
    this.aura = null;
    this.tweens = new Set();
    this.owned = new Set(); // effects that must stop with the state (charges)
    this.reduce = matchMedia('(prefers-reduced-motion: reduce)');
    this.idleLoop();
  }

  // ---- timing helpers that die with the current state ----

  later(ms, fn) {
    const seq = this.seq;
    const id = setTimeout(() => {
      this.timers.delete(id);
      if (seq === this.seq) fn();
    }, ms);
    this.timers.add(id);
  }

  tween(ms, fn, done, fps) {
    const seq = this.seq;
    const t = fx.tween(
      this.stage,
      ms,
      fn,
      () => {
        this.tweens.delete(t);
        if (seq === this.seq) done?.();
      },
      fps,
    );
    this.tweens.add(t);
    return t;
  }

  own(f) {
    this.owned.add(f);
    return f;
  }

  // Stop whatever sequence is running (timers, tweens, charges) and put the
  // layers back where they belong.
  interrupt() {
    this.seq += 1;
    for (const id of this.timers) clearTimeout(id);
    this.timers.clear();
    for (const t of this.tweens) t.cancel();
    this.tweens.clear();
    for (const f of this.owned) f.stop();
    this.owned.clear();
    const { wand, wizard } = this.l;
    wand.offset = { x: 0, y: 0 };
    wand.clipBelow = null;
    wizard.offset = { x: 0, y: 0 };
  }

  // ---- state changes (called before the state draws) ----

  setMode(mode, state = {}) {
    this.interrupt();
    this.dragging = false;
    this.mode = mode;
    this.smile(this.hovered && this.friendly());

    const auraColor = { analyzing: PAL.cyan, 'call-alert': PAL.magenta }[mode];
    if (auraColor !== this.aura?.color) {
      this.aura?.stop();
      this.aura = auraColor ? fx.aura(this.stage, { color: auraColor, strength: mode === 'analyzing' ? 0.6 : 1 }) : null;
    }

    if (state.appear) this.later(560, () => this.entrance());
    if (mode === 'result') this.react(state);
    if (mode === 'idle' || mode === 'greet') this.later(rand(9000, 16000), () => this.fidget());
  }

  friendly() {
    return ['idle', 'greet', 'result', 'learn'].includes(this.mode);
  }

  // Row 1 (smiling) in place of row 0 (idle); the witch's sheet has the same rows.
  smile(on) {
    this.l.wizard.swap = on ? { from: 0, to: 1 } : null;
    this.stage.requestDraw();
  }

  // ---- ambient life: blinks and bubbles, whatever the state ----

  idleLoop() {
    const blink = () => {
      const { wizard } = this.l;
      if (!wizard.swap && this.mode !== 'hidden' && this.mode !== 'vanish') {
        wizard.swap = { from: 0, to: 2 }; // row 2: eyes closed
        this.stage.requestDraw();
        setTimeout(() => {
          if (wizard.swap?.to === 2) wizard.swap = null;
          this.stage.requestDraw();
        }, 130);
      }
      setTimeout(blink, rand(2200, 5200) * (Math.random() < 0.2 ? 0.15 : 1)); // sometimes a double blink
    };
    setTimeout(blink, 1800);

    const bubbles = () => {
      const every = { analyzing: [90, 200], 'call-alert': [250, 600], hidden: null, vanish: null, 'call-watch': null }[this.mode];
      if (every !== null && !document.hidden) {
        const colors = { analyzing: [PAL.cyan, PAL.mist, PAL.white], 'call-alert': [PAL.magenta, PAL.pink, PAL.mist] }[this.mode] ?? [PAL.mist, PAL.steel, PAL.pink];
        fx.bubble(this.stage, { x: rand(AT.mouth.x0, AT.mouth.x1), color: pick(colors), rise: this.mode === 'analyzing' ? rand(16, 30) : undefined });
      }
      const [lo, hi] = every ?? [700, 1800];
      setTimeout(bubbles, rand(lo, hi));
    };
    setTimeout(bubbles, 600);
  }

  // Popping out of the hat: a ring across the cauldron and sparkles from the hat.
  entrance() {
    fx.ring(this.stage, { x: 40, y: AT.mouth.y - 2, r0: 4, r1: 42, flat: 0.28, ms: 700, color: PAL.yellow });
    this.stage.burst(AT.hatTip[0], AT.hatTip[1], 12);
  }

  // A little reaction to each answer (colors follow the bubble's verdict colors).
  react({ result, message }) {
    const verdict = result?.overall?.verdict;
    const colors = message
      ? [PAL.yellow, PAL.gold, PAL.white]
      : { likely_synthetic: [PAL.magenta, PAL.red, PAL.pink], likely_real: [PAL.green, PAL.yellow, PAL.mist], inconclusive: [PAL.blue, PAL.cyan, PAL.mist] }[verdict];
    if (!colors) return;
    for (let i = 0; i < 10; i++) {
      this.later(i * 40, () => fx.bubble(this.stage, { x: rand(AT.mouth.x0, AT.mouth.x1), color: pick(colors), rise: rand(18, 34), r: rand(1, 2.2) }));
    }
    fx.ring(this.stage, { x: 40, y: AT.mouth.y - 2, r0: 4, r1: 40, flat: 0.28, ms: 650, color: colors[0] });
    if (message || verdict === 'likely_real') this.stage.burst(AT.hatTip[0], AT.hatTip[1], 14);
  }

  // ---- the wand: up out of the cauldron, and back down ----

  wandUp(ms = 320, then) {
    const { wand } = this.l;
    wand.show(0, 0);
    wand.clipBelow = AT.lip;
    wand.offset = { x: 0, y: WAND_DOWN };
    this.tween(
      ms,
      (t) => {
        wand.offset = { x: 0, y: WAND_DOWN * (1 - easeOutBack(t)) };
      },
      () => {
        wand.offset = { x: 0, y: 0 };
        wand.clipBelow = null;
        fx.starPop(this.stage, { x: AT.wandTip[0], y: AT.wandTip[1], sizes: [1, 3, 2, 1] }); // a glint as it comes up
        then?.();
      },
      12,
    );
  }

  wandDown(ms = 260, then) {
    const { wand } = this.l;
    wand.stop();
    wand.show(0, 0);
    wand.clipBelow = AT.lip;
    this.tween(
      ms,
      (t) => {
        wand.offset = { x: 0, y: WAND_DOWN * easeIn(t) };
      },
      () => {
        wand.hide();
        wand.offset = { x: 0, y: 0 };
        wand.clipBelow = null;
        then?.();
      },
      12,
    );
  }

  // Now and then, while idle: pull the wand out, twirl a firework, put it away.
  fidget() {
    if (this.hovered || this.reduce.matches) {
      this.later(rand(8000, 14000), () => this.fidget());
      return;
    }
    const { wand } = this.l;
    this.smile(true);
    this.wandUp(320, () => {
      wand.play(row(1, [0, 1]), 8);
      this.firework();
      this.later(1100, () =>
        this.wandDown(260, () => {
          this.smile(this.hovered);
          this.later(rand(14000, 26000), () => this.fidget());
        }),
      );
    });
  }

  // A spark shoots up from the wand and bursts.
  firework() {
    const [x, y] = AT.wandTip;
    const top = y - rand(8, 12);
    const born = performance.now();
    this.stage.addFx({
      pass: 'over',
      draw: (c, now, pixel) => {
        const t = stepped(now - born) / 330;
        if (t >= 1) {
          fx.starPop(this.stage, { x: x + 1, y: top, sizes: [2, 4, 3, 2, 1] });
          fx.spray(this.stage, { x: x + 1, y: top, count: 10, speed: [15, 35] });
          return false;
        }
        draw.dot(c, pixel, x + t, y - (y - top) * easeOut(t), 0.5, WAND_STAR[0]);
        draw.dot(c, pixel, x + t * 0.5, y - (y - top) * easeOut(t) + 2, 0.5, WAND_STAR[3]);
        return true;
      },
    });
  }

  // ---- the pointer ----

  hover(on) {
    if (on === this.hovered) return;
    this.hovered = on;
    if (!this.friendly()) return;
    this.smile(on);
    if (!on) return;
    const { wizard } = this.l;
    this.tween(260, (t) => {
      wizard.offset = { x: 0, y: -3 * Math.sin(t * Math.PI) }; // a little hop
    });
    for (let i = 0; i < 3; i++) this.later(i * 70, () => fx.mote(this.stage, { color: pick([PAL.yellow, PAL.pink]) }));
    this.stage.spark(AT.hatTip[0] * 4, AT.hatTip[1] * 4, { vy: -50, gold: true });
  }

  // A file is being dragged over: wand up, eager.
  dragOver(on) {
    if (on === this.dragging) return;
    this.dragging = on;
    if (!['idle', 'greet', 'result'].includes(this.mode)) return;
    this.interrupt(); // stops a fidget in progress
    if (on) {
      this.smile(true);
      this.wandUp(220, () => {
        this.l.wand.play(row(1, [0, 1]), 10);
        this.own(fx.charge(this.stage, ...AT.wandTip));
      });
    } else {
      this.smile(this.hovered);
      this.wandDown(220, () => this.later(rand(14000, 26000), () => this.fidget()));
    }
  }

  // A click on the stage (x, y in stage pixels).
  click(x, y) {
    fx.ring(this.stage, { x, y, r0: 1, r1: 10, ms: 360, color: PAL.yellow });
    this.stage.burst(x, y, 6);
  }

  // ---- the hang-up spell ----

  // Wand out of the cauldron, charge, cast. onFire(tip) is called the moment
  // the spell leaves the wand (tip in stage pixels); main takes it from there.
  obliterate(onFire) {
    const { wizard, wand } = this.l;
    this.aura?.stop();
    this.aura = fx.aura(this.stage, { color: PAL.magenta, strength: 1.3 });
    this.aura.color = null; // not the call-alert aura: the next state replaces it
    const fire = () => {
      wand.show(3, 2);
      const [x, y] = AT.castTip;
      fx.starPop(this.stage, { x, y, sizes: [3, 6, 8, 7, 5, 3, 2, 1] });
      // the kick: specks thrown back up the wand's line, away from the target
      fx.spray(this.stage, { x, y, count: 18, speed: [25, 70], dir: -Math.PI / 4, spread: Math.PI * 1.2 });
      this.stage.shake(2, 250);
      wizard.play(WIZARD.happy, 8);
      onFire(AT.castTip);
      this.later(1500, () => this.wandDown(300));
    };
    if (this.reduce.matches) {
      fire();
      return;
    }
    wizard.play(WIZARD.focus, 10);
    this.wandUp(330, () => {
      wand.play(row(1, [0, 1]), 8); // the sheet's own sparkly wand frames
      const charge = this.own(fx.charge(this.stage, ...AT.wandTip));
      this.later(750, () => {
        charge.stop();
        wand.play(WAND.cast, 10, { once: true, onDone: fire }); // the sheet's swing, at sprite speed
      });
    });
  }
}
