// Produces AnalyzeResponse objects (docs/INTERFACES.md v0.4).
//
// File checks go to the server (POST /analyze) when a server URL is set in
// config.js; while the server has no model it answers with demo data
// (`mock: true`). Without a server URL, and for calls (no audio is captured
// yet), the result is a local MOCK after a short delay that stands in for
// inference time. The mock says "likely real" by default; the tray's
// "Mock result" switch (or DISPEL_MOCK_VERDICT=synthetic) flips it to
// "likely synthetic" to demo the deepfake flow.
//
// Errors thrown here carry `userMessage`, which the wizard shows as-is.

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { loadConfig, clientId } = require('./config');

const MOCK_LATENCY_MS = { file: 2500, call: 3500 };
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024; // server limit (INTERFACES.md)
const REQUEST_TIMEOUT_MS = 90_000; // CPU inference on a 2-minute clip, plus upload

// Placeholder thresholds from INTERFACES.md until the ML owner sets real ones.
const SYNTHETIC_AT = 0.75;
const REAL_AT = 0.25;

function verdictFor(probability) {
  if (probability >= SYNTHETIC_AT) return 'likely_synthetic';
  if (probability <= REAL_AT) return 'likely_real';
  return 'inconclusive';
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let mockVerdict = process.env.DISPEL_MOCK_VERDICT === 'synthetic' ? 'synthetic' : 'real';
const getMockVerdict = () => mockVerdict;
function setMockVerdict(v) {
  if (v === 'real' || v === 'synthetic') mockVerdict = v;
}

function userError(userMessage, detail) {
  const err = new Error(detail || userMessage);
  err.userMessage = userMessage;
  return err;
}

async function mockAnalyze(source) {
  const started = Date.now();
  await sleep(MOCK_LATENCY_MS[source]);

  // real: 2-14%, synthetic: 86-98%, so the verdict is never borderline.
  const base = mockVerdict === 'synthetic' ? 0.86 : 0.02;
  const probability = Math.round((base + Math.random() * 0.12) * 1000) / 1000;
  const llr = Math.log(probability / (1 - probability));
  return {
    version: '0.4',
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

// Server error codes (INTERFACES.md) in the wizard's words.
const SERVER_ERRORS = {
  decode_failed: 'I couldn’t read that file.',
  too_short: 'That clip is too short. Give me at least a second of audio.',
  too_long: 'That clip is too long. I can check up to 2 minutes (25 MB).',
  unauthorized: 'The server didn’t accept my key. Check the app’s config.',
};

async function remoteAnalyze(source, filePath, { serverUrl, apiKey }) {
  const { size } = await fs.stat(filePath);
  if (size > MAX_UPLOAD_BYTES) throw userError(SERVER_ERRORS.too_long);

  // Uploaded only because the user dropped or picked this file, and only to
  // our own server, which deletes it after answering (AGENTS.md).
  const form = new FormData();
  form.append('file', new Blob([await fs.readFile(filePath)]), path.basename(filePath));
  form.append('source', source);
  const headers = { 'X-Dispel-Client': clientId() };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

  let res;
  try {
    res = await fetch(`${serverUrl}/analyze`, {
      method: 'POST',
      headers,
      body: form,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    const timedOut = err.name === 'TimeoutError';
    throw userError(timedOut ? 'The server took too long to answer.' : 'I can’t reach the server right now.', err.message);
  }

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const code = body?.error;
    throw userError(SERVER_ERRORS[code] ?? 'The server couldn’t check that clip.', `HTTP ${res.status} ${code ?? ''}`);
  }
  if (!body?.overall) throw userError('The server sent an answer I don’t understand.', 'bad response shape');
  return body;
}

// source: "file" | "call". filePath is required for "file".
async function analyze(source, filePath) {
  const config = loadConfig();
  if (source === 'file' && config.serverUrl) return remoteAnalyze(source, filePath, config);
  return mockAnalyze(source);
}

module.exports = { analyze, verdictFor, SYNTHETIC_AT, getMockVerdict, setMockVerdict };
