// Runs bin/callwatch (macOS) and emits call state changes:
//   'call'   ({ app, bounds })  a call app started using the mic
//   'move'   ({ app, bounds })  the call window moved or resized
//   'ended'  ()                 no call app is using the mic any more
//   'end-result' (ok)           reply to endCall(): whether the app was asked to quit
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
    this.state = { active: false, app: null, bounds: null, canEnd: false };
    this.simulated = false;
  }

  start() {
    if (process.platform !== 'darwin' || !fs.existsSync(HELPER)) {
      console.warn('[callwatch] helper unavailable; call detection is off');
      return false;
    }
    this.proc = spawn(HELPER, [], { stdio: ['pipe', 'pipe', 'inherit'] });
    readline.createInterface({ input: this.proc.stdout }).on('line', (line) => {
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        return;
      }
      if (msg.event === 'end') this.emit('end-result', Boolean(msg.ok));
      else if (!this.simulated) this.apply(msg);
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

  apply({ active, app, bounds, canEnd }) {
    const prev = this.state;
    this.state = { active: Boolean(active), app: app || null, bounds: bounds || null, canEnd: Boolean(canEnd) };
    if (this.state.active && !prev.active) this.emit('call', this.state);
    else if (!this.state.active && prev.active) this.emit('ended');
    else if (this.state.active && JSON.stringify(bounds) !== JSON.stringify(prev.bounds)) {
      this.emit('move', this.state);
    }
  }

  // Hang up by politely quitting the call app. The answer arrives as
  // 'end-result'; the call itself ends when the app lets go of the mic.
  endCall() {
    if (this.simulated) {
      this.endSimulated();
      this.emit('end-result', true);
    } else if (this.proc) {
      this.proc.stdin.write('end\n');
    } else {
      this.emit('end-result', false);
    }
  }

  // Demo helper: pretend a call is running in `bounds` until endSimulated().
  simulate(bounds) {
    this.simulated = true;
    this.apply({ active: true, app: 'Simulated call', bounds, canEnd: true });
  }

  endSimulated() {
    this.simulated = false;
    this.apply({ active: false });
  }

  // The simulated call's window was moved.
  moveSimulated(bounds) {
    if (this.simulated) this.apply({ ...this.state, bounds });
  }
}

module.exports = { CallWatch };
