# INTERFACES: version 0.2 (draft)

Change this only through a PR that bumps the version and names the change.
Both `app/` and `server/` code against this file. A mock response is in
`docs/examples/analyze_response.example.json`.

## Server (Python, FastAPI) at http://127.0.0.1:8765

### GET /health
Returns `{"ok": true, "model": "v2e", "device": "cuda|cpu", "version": "0.1"}`.

### POST /analyze
Request: `multipart/form-data` with the field `file` (wav, mp3, m4a, webm or
ogg). An optional form field `prior` (float between 0 and 1, default 0.5) is
the user's prior belief that the clip is synthetic.

The server:
- decodes the file with ffmpeg and converts it to 16 kHz mono
- splits the audio into segments
- scores each segment and the whole clip

Response 200:

| Field | Type | Meaning |
|---|---|---|
| `version` | string | `"0.1"` |
| `clip_id` | string | uuid |
| `duration_s` | float | clip length in seconds |
| `input` | object | `{ "sample_rate": int, "channels": int, "codec": str }` |
| `model` | object | `{ "name": "v2e", "release": str }` |
| `overall.llr` | float | natural-log likelihood ratio (synthetic vs real), capped at ±ln(100) |
| `overall.prior` | float | the prior that was used |
| `overall.probability` | float | sigmoid(llr + logit(prior)), between 0 and 1 |
| `overall.verdict` | enum | `likely_synthetic` \| `inconclusive` \| `likely_real` |
| `segments[]` | array | each item is `{ "start_s", "end_s", "llr", "probability" }` |
| `manipulation` | object | `{ "type": str, "confidence": float }`. `type` is `"unknown"` until we have the NSA label schema. |
| `channel` | object | `{ "bandwidth_hz": int, "phone_like": bool, "note": str }` |
| `transcript` | string or null | optional |
| `limitations[]` | string[] | plain-language caveats to show in the report |
| `timing_ms` | int | processing time |

The ML owner sets the verdict thresholds in `server/`, and they are recorded in
DECISIONS.md. **Placeholder until they're set:** `inconclusive` whenever
0.25 < probability < 0.75.

Errors: `{"error": "<code>", "message": str}` with status 400 (bad audio), 413
(too long), or 500. Error codes: `decode_failed`, `too_short` (< 1 s),
`too_long` (> 120 s), `internal`.

## Electron IPC (preload bridge `window.wizard`, app in `app/`)
Changed in 0.2: the bridge now matches what the app does. The main process
makes every decision; the renderer only draws the state it's sent.

Renderer → main (each argument is validated in main):
- `wizard.pickFile()` opens a file dialog, then analyzes the chosen file.
- `wizard.analyzeFile(file: File)` analyzes a dropped file. The preload turns
  it into a path; main checks the extension, that it's a file, and its size.
- `wizard.dismissBubble()`, `wizard.vanished()`, `wizard.drag(phase, x, y)` are UI only.

Main → renderer:
- `wizard.onState(cb)` receives `{ mode, ... }`, where `mode` is one of
  `hidden | vanish | idle | analyzing | result | call-watch | call-alert`.
  `result` and `call-alert` carry an AnalyzeResponse as `result`.

Not built yet: `captureLast(seconds)` (system-audio capture). Until then no
audio is captured at all, and call-mode results are mocks (see
`app/src/main/analyzer.js`).

The renderer never talks to the network directly. All HTTP calls go through the
main process.
