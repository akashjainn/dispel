// JXA, run by server.js through `osascript -l JavaScript`: clicks the "Call"
// button that macOS shows after a facetime:// link is opened, so the caller
// laptop dials with no click. The prompt is either a FaceTime window or a
// notification banner, depending on the macOS version, so both are searched.
// Needs Accessibility for the app running the rig (Terminal, iTerm, VS Code).
// Prints "clicked", "timeout" or "error: ...".

function run(argv) {
  const timeoutS = Number(argv[0]) || 10;
  const se = Application('System Events');
  const LABELS = ['Call', 'Anrufen', 'Appeler', 'Llamar'];
  const isCall = (e) => {
    try {
      if (e.role() !== 'AXButton') return false;
      return LABELS.includes(e.name()) || LABELS.includes(e.description());
    } catch {
      return false;
    }
  };
  const findIn = (procName) => {
    let proc;
    try {
      proc = se.processes.byName(procName);
      proc.name();
    } catch {
      return null; // not running
    }
    for (const w of proc.windows()) {
      let els;
      try {
        els = w.entireContents();
      } catch {
        continue;
      }
      const btn = els.find(isCall);
      if (btn) return btn;
    }
    return null;
  };

  const deadline = Date.now() + timeoutS * 1000;
  while (Date.now() < deadline) {
    try {
      const btn = findIn('FaceTime') || findIn('NotificationCenter');
      if (btn) {
        btn.click();
        return 'clicked';
      }
    } catch (err) {
      return `error: ${err.message}`; // usually: no Accessibility permission
    }
    delay(0.3);
  }
  return 'timeout';
}
