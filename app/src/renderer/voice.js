// Spoken lines for the big moments only: a file's verdict and the hang-up
// spell. Nothing is said while idle, watching or listening. The clips are
// ElevenLabs lines in Assets/voice/<wizard|witch>/<line>.mp3 (voices and text
// in its README); a missing clip is skipped silently.

// Lines with several takes: 'snark' plays one of snark1..snark3, never the
// same take twice in a row.
const TAKES = { snark: 3, real: 3, cast: 2, gone: 2 };

class Voice {
  constructor(character) {
    this.character = character; // () => 'wizard' | 'witch'
    this.queue = [];
    this.audio = null;
    this.lastTake = {};
  }

  // Say these lines in order, after whatever is already playing.
  say(...lines) {
    this.queue.push(...lines);
    if (!this.audio) this.next();
  }

  // Cut off whatever is playing and say these instead.
  interrupt(...lines) {
    this.stop();
    this.say(...lines);
  }

  stop() {
    this.queue = [];
    if (!this.audio) return;
    this.audio.onended = this.audio.onerror = null;
    this.audio.pause();
    this.audio = null;
  }

  next() {
    const line = this.queue.shift();
    if (!line) {
      this.audio = null;
      return;
    }
    const a = new Audio(`../../Assets/voice/${this.character()}/${this.take(line)}.mp3`);
    this.audio = a;
    const done = () => this.audio === a && this.next();
    a.onended = a.onerror = done;
    a.play().catch(done);
  }

  take(line) {
    const n = TAKES[line];
    if (!n) return line;
    let i;
    do i = 1 + Math.floor(Math.random() * n);
    while (n > 1 && i === this.lastTake[line]);
    this.lastTake[line] = i;
    return `${line}${i}`;
  }
}
