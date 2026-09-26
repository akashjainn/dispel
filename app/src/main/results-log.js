// Appends one JSON line per result to <userData>/results.jsonl and echoes it
// to the console. Only scores and metadata are logged, never audio.

const fs = require('node:fs');
const path = require('node:path');
const { app } = require('electron');

function logPath() {
  return path.join(app.getPath('userData'), 'results.jsonl');
}

function logResult({ source, name, result }) {
  const entry = {
    ts: new Date().toISOString(),
    source, // "file" | "call"
    name, // file basename or call app name
    probability: result.overall.probability,
    verdict: result.overall.verdict,
    model: result.model.name,
    mock: Boolean(result.mock),
    clip_id: result.clip_id,
  };
  console.log('[result]', JSON.stringify(entry));
  try {
    fs.appendFileSync(logPath(), JSON.stringify(entry) + '\n');
  } catch (err) {
    console.error('[result] could not write log:', err.message);
  }
}

module.exports = { logResult, logPath };
