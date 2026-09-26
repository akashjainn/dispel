// Frame-by-frame sprite animation on a div with a sprite-sheet background.
// Each sheet is a grid of 80x128 frames drawn at 2x (160x256 per cell).

const CELL_W = 160;
const CELL_H = 256;

class SpriteLayer {
  // yOffset: the first visible row of the cell (px at 2x), matching the CSS crop.
  constructor(el, yOffset = 0) {
    this.el = el;
    this.yOffset = yOffset;
    this.timer = null;
  }

  show(col, row) {
    this.el.style.backgroundPosition = `${-col * CELL_W}px ${-(row * CELL_H + this.yOffset)}px`;
  }

  // frames: [[col, row], ...]. Loops unless `once`; calls onDone after a once run.
  play(frames, fps, { once = false, onDone } = {}) {
    this.stop();
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
}

const row = (r, cols) => cols.map((c) => [c, r]);
const BOB = [0, 1, 2, 3, 4, 3, 2, 1];

// wizard-sprites.png rows: 0 idle, 1 smiling, 2 eyes closed, 3 sinking into
// the hat, 4 hat with rising smoke.
const WIZARD = {
  idle: row(0, BOB),
  happy: row(1, BOB),
  focus: row(2, BOB),
  vanish: [...row(3, [0, 1, 2, 3, 4]), ...row(4, [0, 1, 2, 3, 4])],
  appear: [...row(4, [4, 3, 2, 1, 0]), ...row(3, [4, 3, 2, 1, 0])],
};
const POT = { bubble: row(0, [0, 1, 2, 3]) };
const WAND = { cast: row(2, [0, 1, 2, 3]), sparkle: row(1, [0, 1]) };
const POOF = { burst: [...row(0, [0, 1, 2, 3, 4, 5]), ...row(1, [0, 1, 2, 3, 4, 5])] };
