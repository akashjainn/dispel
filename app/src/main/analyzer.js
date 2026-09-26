// Produces AnalyzeResponse objects (docs/INTERFACES.md v0.4).
//
// Where results come from is picked in the tray's "Results from" menu:
//   server     (default) checks go to POST /analyze on the server in
//              config.local.json. Files are uploaded when dropped or picked;
//              calls upload the few seconds the wizard was asked to listen to
//              (source=call, see callcapture.js). While the server has no
//              model it answers with demo data (`mock: true`).
//   real       local MOCK that says "likely real" (2-14%) after a short delay
//   synthetic  local MOCK that says "likely synthetic" (86-98%)
// DISPEL_RESULTS=real|synthetic picks a mock at launch (demos, tests).
//
// Errors thrown here carry `userMessage`, which the wizard shows as-is.

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { loadConfig, clientId } = require('./config');

const MOCK_LATENCY_MS = { file: 2500, call: 3500 }; // mocks don't record, so a call answers sooner
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

const RESULT_SOURCES = ['server', 'real', 'synthetic'];
let resultSource = RESULT_SOURCES.includes(process.env.DISPEL_RESULTS) ? process.env.DISPEL_RESULTS : 'server';
const getResultSource = () => resultSource;
function setResultSource(v) {
  if (RESULT_SOURCES.includes(v)) resultSource = v;
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
  const base = resultSource === 'synthetic' ? 0.86 : 0.02;
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
  const form = new FormData();
  const { size } = await fs.stat(filePath);
  if (size > MAX_UPLOAD_BYTES) throw userError(SERVER_ERRORS.too_long);
  // Uploaded only because the user dropped or picked this file, or asked the
  // wizard to listen to a call, and only to our own server, which deletes it
  // after answering (AGENTS.md).
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

// source: "file" | "call". filePath is the clip to upload (a call's is the
// temporary recording from callcapture.js). Mocks never read it.
async function analyze(source, filePath) {
  if (resultSource !== 'server') return mockAnalyze(source);
  const config = loadConfig();
  if (!config.serverUrl) {
    throw userError('I’m not connected to a server. Add it to app/config.local.json, or pick a mock in the tray menu.');
  }
  return remoteAnalyze(source, filePath, config);
}

const usesServer = () => resultSource === 'server';

module.exports = { analyze, usesServer, verdictFor, SYNTHETIC_AT, getResultSource, setResultSource };
