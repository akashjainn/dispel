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
  // Calls fn(t) every frame for ms (t: 0..1), then done(). cancel() stops it quietly.
  tween(stage, ms, fn, done) {
    const start = performance.now();
    const f = {
      pass: 'under', // before the layers, so a moved layer draws in its new spot
      cancelled: false,
      draw(_c, now) {
        if (f.cancelled) return false;
        const t = clamp01((now - start) / ms);
        fn(t);
        if (t < 1) return true;
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

  // A bright star flaring at a point (the wand firing).
  flare(stage, { x, y, r = 10, ms = 380, color = PAL.yellow }) {
    const born = performance.now();
    return stage.addFx({
      pass: 'glow',
      draw(c, now, pixel) {
        const t = (now - born) / ms;
        if (t >= 1) return false;
        draw.glow(c, pixel, x, y, r * (0.6 + t), r * (0.6 + t), color, (1 - t) * 0.9);
        draw.star(c, pixel, x, y, r * (1.2 - t * 0.6), PAL.white, 1 - easeIn(t));
        return true;
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

  // Sparkles gathering into a point, and a growing orb there (the wand
  // charging). stop() lets it go; at(x, y) moves it.
  charge(stage, x, y) {
    const born = performance.now();
    const motes = [];
    let lastSpawn = 0;
    let stopped = false;
    const f = stage.addFx({
      pass: 'glow',
      draw(c, now, pixel) {
        if (stopped) return false;
        const age = now - born;
        if (now - lastSpawn > 35) {
          lastSpawn = now;
          const a = rand(0, Math.PI * 2);
          motes.push({ a, d: rand(14, 24), born: now, color: pick([PAL.yellow, PAL.gold, PAL.pink, PAL.white]) });
        }
        for (let i = motes.length - 1; i >= 0; i--) {
          const m = motes[i];
          const t = (now - m.born) / 380;
          if (t >= 1) {
            motes.splice(i, 1);
            continue;
          }
          const d = m.d * (1 - easeIn(t));
          const a = m.a + t * 2.2; // spiral in
          draw.dot(c, pixel, f.x + Math.cos(a) * d, f.y + Math.sin(a) * d, 0.5, m.color, 0.4 + t * 0.6);
        }
        const r = Math.min(5, 1 + age / 170) * (0.85 + 0.15 * Math.sin(now / 40));
        draw.glow(c, pixel, f.x, f.y, r * 2.2, r * 2.2, PAL.magenta, 0.9);
        draw.dot(c, pixel, f.x, f.y, r * 0.6, PAL.yellow);
        draw.dot(c, pixel, f.x, f.y, r * 0.3, PAL.white);
        return true;
      },
      at(nx, ny) {
        f.x = nx;
        f.y = ny;
      },
      stop() {
        stopped = true;
      },
    });
    f.x = x;
    f.y = y;
    return f;
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

  tween(ms, fn, done) {
    const seq = this.seq;
    const t = fx.tween(this.stage, ms, fn, () => {
      this.tweens.delete(t);
      if (seq === this.seq) done?.();
    });
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
        this.stage.spark(AT.wandTip[0] * 4, AT.wandTip[1] * 4, { vy: -60 }); // a glint as it comes up
        then?.();
      },
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
    const color = pick([PAL.yellow, PAL.pink, PAL.cyan]);
    const born = performance.now();
    this.stage.addFx({
      pass: 'glow',
      draw: (c, now, pixel) => {
        const t = (now - born) / 320;
        if (t >= 1) {
          this.stage.burst(x + 1, top, 10);
          fx.ring(this.stage, { x: x + 1, y: top, r0: 1, r1: 8, ms: 380, color });
          return false;
        }
        draw.dot(c, pixel, x + t, y - (y - top) * easeOut(t), 0.6, color);
        draw.dot(c, pixel, x + t * 0.5, y - (y - top) * easeOut(t) + 2, 0.4, color, 0.5);
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
      fx.flare(this.stage, { x, y, r: 12 });
      fx.ring(this.stage, { x, y, r0: 2, r1: 26, ms: 420, color: PAL.yellow, w: 2 });
      this.stage.burst(x, y, 16);
      this.stage.shake(2.5, 320);
      wizard.play(WIZARD.happy, 8);
      onFire(AT.castTip);
      this.later(1500, () => this.wandDown(300));
    };
    if (this.reduce.matches) {
      fire();
      return;
    }
    wizard.play(WIZARD.focus, 10);
    this.wandUp(300, () => {
      wand.play(row(1, [0, 1]), 12);
      const charge = this.own(fx.charge(this.stage, ...AT.wandTip));
      this.stage.shake(0.8, 750);
      this.later(750, () => {
        charge.stop();
        wand.play(WAND.cast, 16, { once: true, onDone: fire });
      });
    });
  }
}
