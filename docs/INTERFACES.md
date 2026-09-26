# INTERFACES: version 0.1 (draft)

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

## Electron IPC (preload bridge `window.wizard`)
- `wizard.captureLast(seconds: number): Promise<ArrayBuffer>` records system
  audio. It only runs after the user clicks.
- `wizard.analyze(audio: ArrayBuffer | string /* file path */, prior?: number): Promise<AnalyzeResponse>`
- `wizard.health(): Promise<Health>`

The renderer never talks to the network directly. All HTTP calls go through the
main process.
