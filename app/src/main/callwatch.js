// Runs bin/callwatch (macOS) and emits call state changes:
//   'call'   ({ app, bounds })  a call app started using the mic
//   'move'   ({ app, bounds })  the call window moved or resized
//   'ended'  ()                 no call app is using the mic any more
// On other platforms, or if the helper isn't built, nothing is emitted and
// only the tray's "Simulate call" drives call mode.

const { spawn } = require('node:child_process');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const HELPER = path.join(__dirname, '..', '..', 'bin', 'callwatch');

class CallWatch extends EventEmitter {
  constructor() {
    super();
    this.proc = null;
    this.state = { active: false, app: null, bounds: null };
    this.simulated = false;
  }

  start() {
    if (process.platform !== 'darwin' || !fs.existsSync(HELPER)) {
      console.warn('[callwatch] helper unavailable; call detection is off');
      return false;
    }
    this.proc = spawn(HELPER, [], { stdio: ['ignore', 'pipe', 'inherit'] });
    readline.createInterface({ input: this.proc.stdout }).on('line', (line) => {
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        return;
      }
      if (!this.simulated) this.apply(msg);
    });
    this.proc.on('exit', (code) => {
      console.warn('[callwatch] helper exited', code);
      this.proc = null;
    });
    return true;
  }

  stop() {
    this.proc?.kill();
    this.proc = null;
  }

  apply({ active, app, bounds }) {
    const prev = this.state;
    this.state = { active: Boolean(active), app: app || null, bounds: bounds || null };
    if (this.state.active && !prev.active) this.emit('call', this.state);
    else if (!this.state.active && prev.active) this.emit('ended');
    else if (this.state.active && JSON.stringify(bounds) !== JSON.stringify(prev.bounds)) {
      this.emit('move', this.state);
    }
  }

  // Demo helper: pretend a call is running in `bounds` until endSimulated().
  simulate(bounds) {
    this.simulated = true;
    this.apply({ active: true, app: 'Simulated call', bounds });
  }

  endSimulated() {
    this.simulated = false;
    this.apply({ active: false });
  }
}

module.exports = { CallWatch };
