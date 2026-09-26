// Produces AnalyzeResponse objects (docs/INTERFACES.md v0.1).
//
// The server isn't built yet, so every result is a MOCK that flags the audio
// as likely synthetic after a short delay that stands in for inference time.
// When server/ exists, replace mockAnalyze() with a POST to
// http://127.0.0.1:8765/analyze and keep the same return shape.

const crypto = require('node:crypto');

const MOCK_LATENCY_MS = { file: 2500, call: 3500 };

// Placeholder thresholds from INTERFACES.md until the ML owner sets real ones.
const SYNTHETIC_AT = 0.75;
const REAL_AT = 0.25;

function verdictFor(probability) {
  if (probability >= SYNTHETIC_AT) return 'likely_synthetic';
  if (probability <= REAL_AT) return 'likely_real';
  return 'inconclusive';
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function mockAnalyze(source) {
  const started = Date.now();
  await sleep(MOCK_LATENCY_MS[source]);

  const probability = Math.round((0.86 + Math.random() * 0.12) * 1000) / 1000;
  const llr = Math.log(probability / (1 - probability));
  return {
    version: '0.1',
    clip_id: crypto.randomUUID(),
    duration_s: null,
    input: null,
    model: { name: 'mock', release: 'mock' },
    overall: { llr, prior: 0.5, probability, verdict: verdictFor(probability) },
    segments: [],
    manipulation: { type: 'unknown', confidence: 0 },
    channel: null,
    transcript: null,
    limitations: ['Mock result: no detection model is connected yet.'],
    timing_ms: Date.now() - started,
    mock: true,
  };
}

module.exports = { analyze: mockAnalyze, verdictFor, SYNTHETIC_AT };
