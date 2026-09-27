// Runs bin/callwatch (macOS) and emits call state changes:
//   'call'   ({ app, bounds, prefixes })  a call app started using the mic
//                               (prefixes: its bundle IDs, for callcapture)
//   'move'   ({ app, bounds, front })  the call window moved or resized, or
//                               came to / left the front (front: bool)
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
    this.state = { active: false, app: null, bounds: null, canEnd: false, prefixes: [] };
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

  apply({ active, app, bounds, canEnd, front = true, prefixes = [] }) {
    const prev = this.state;
    this.state = {
      active: Boolean(active),
      app: app || null,
      bounds: bounds || null,
      canEnd: Boolean(canEnd),
      front: Boolean(front),
      prefixes: Array.isArray(prefixes) ? prefixes : [],
    };
    if (this.state.active && !prev.active) this.emit('call', this.state);
    else if (!this.state.active && prev.active) this.emit('ended');
    else if (
      this.state.active &&
      (JSON.stringify(bounds) !== JSON.stringify(prev.bounds) || this.state.front !== prev.front)
    ) {
      this.emit('move', this.state);
    }
  }

  // Hang up by politely quitting the call app (appName: the call's "app", so
  // it still works if the app let go of the mic for a moment). The answer
  // arrives as 'end-result'; the call itself ends when the app lets go of the mic.
  endCall(appName) {
    if (this.simulated) {
      this.endSimulated();
      this.emit('end-result', true);
    } else if (this.proc) {
      const name = String(appName || '').replace(/[\r\n]/g, '');
      this.proc.stdin.write(name ? `end ${name}\n` : 'end\n');
    } else {
      this.emit('end-result', false);
    }
  }

  // Bring the call app to the front (its window may be behind others).
  focus(appName) {
    if (this.simulated || !this.proc) return;
    const name = String(appName || '').replace(/[\r\n]/g, '');
    this.proc.stdin.write(name ? `focus ${name}\n` : 'focus\n');
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
}

module.exports = { CallWatch };
