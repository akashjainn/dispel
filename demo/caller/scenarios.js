// Loads scenarios.local.json (or the example) for server.js and setup-obs.js.

const fs = require('node:fs');
const path = require('node:path');

const ROOT = __dirname;
const FILE = fs.existsSync(path.join(ROOT, 'scenarios.local.json'))
  ? path.join(ROOT, 'scenarios.local.json')
  : path.join(ROOT, 'scenarios.example.json');
const config = JSON.parse(fs.readFileSync(FILE, 'utf8'));

// A caller's video, with OBS scene and source names filled in:
// { file?, scene, input } or null. `file` is only needed by setup-obs.js.
function videoOf(c) {
  if (!c.video) return null;
  return { file: c.video.file, scene: c.video.scene || c.label, input: c.video.input || `${c.label} video` };
}

module.exports = { ROOT, FILE, config, videoOf };
