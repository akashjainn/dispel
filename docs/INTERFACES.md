# INTERFACES: version 0.2 (draft)

Change this only through a PR that bumps the version and names the change.
Both `app/` and `server/` code against this file. A mock response is in
`docs/examples/analyze_response.example.json`.

## Server (Python, FastAPI)

**Base URL is configurable.** Default for local dev: `http://127.0.0.1:8765`.
Deployed (Vultr): `https://<host>` from `terraform output base_url` (see
`infra/vultr/README.md`). The app reads it from config, never hard-codes it.

**Auth (deployed only).** `POST /analyze` needs `Authorization: Bearer <API_KEY>`.
`GET /health` is public. With no `API_KEY` set on the server (local dev), auth is off.
A wrong or missing key gives 401 `{"error": "unauthorized", ...}`.

### GET /
A public HTML landing page ("Team Gemini") for people who open the server URL in a browser. Not part of the API; the app never calls it.

### GET /health
Returns `{"ok": true, "model": "<release name, e.g. v3p>" | "mock", "device": "cuda|cpu", "version": "0.3", "mock": bool, "weights_found": bool}`, plus `load_error` (string) if weights were found but could not be loaded.
`mock: true` means the response is the canned example, not a real model result. The UI must show a "demo data" badge when it is true.

### POST /analyze
Request: `multipart/form-data` with the field `file` (wav, flac, mp3, m4a, webm or
ogg). An optional form field `prior` (float between 0 and 1, default 0.5) is
the user's prior belief that the clip is synthetic.

The server:
- decodes the file with ffmpeg and converts it to 16 kHz mono
- splits the audio into segments
- scores each segment and the whole clip

Response 200:

| Field | Type | Meaning |
|---|---|---|
| `version` | string | `"0.3"` |
| `clip_id` | string | uuid |
| `duration_s` | float | clip length in seconds |
| `input` | object | `{ "sample_rate": int, "channels": int, "codec": str }` |
| `model` | object | `{ "name": str, "release": str }` (e.g. `v3p`) |
| `overall.llr` | float | natural-log likelihood ratio (synthetic vs real), capped at ±ln(100) |
| `overall.prior` | float | the prior that was used |
| `overall.probability` | float | sigmoid(llr + logit(prior)), between 0 and 1 |
| `overall.verdict` | enum | `likely_synthetic` \| `inconclusive` \| `likely_real` |
| `segments[]` | array | each item is `{ "start_s", "end_s", "llr", "probability" }`: the neural detector alone on each 4 s window (up to 3) |
| `analyzers[]` | array | each item is `{ "name", "ran": bool, "finding": str, "llr_contribution": float, "ms": int }`: which techniques ran, what each found, and how much each moved the LLR (uncapped; they sum to the fused LLR before the cap) |
| `manipulation` | object | `{ "type": str, "confidence": float }`. `type` is `"unknown"` until we have the NSA label schema. |
| `channel` | object | `{ "bandwidth_hz": int, "phone_like": bool, "note": str }` |
| `transcript` | string or null | optional |
| `limitations[]` | string[] | plain-language caveats to show in the report |
| `timing_ms` | int | processing time |
| `pipeline_version` | string | hearsay package version |

The ML owner sets the verdict thresholds in `server/`, and they are recorded in
DECISIONS.md. **Placeholder until they're set:** `inconclusive` whenever
0.25 < probability < 0.75.

Errors: `{"error": "<code>", "message": str}` with status 400 (bad input), 401,
413 (too long or too large), or 500. Error codes: `decode_failed`, `too_short`
(< 1 s or empty), `too_long` (> 120 s or over the upload limit, 25 MB),
`bad_request` (e.g. `prior` outside 0..1), `unauthorized`, `internal`.

## Electron IPC (preload bridge `window.wizard`, app in `app/`)
Changed in 0.2: the bridge now matches what the app does. The main process
makes every decision; the renderer only draws the state it's sent.

Renderer → main (each argument is validated in main):
- `wizard.pickFile()` opens a file dialog, then analyzes the chosen file.
- `wizard.endCall()` answers "Yes, hang up" on a flagged call. Main quits the
  call app politely (like Cmd+Q) through the callwatch helper. Browsers are never
  quit; for them the wizard asks the user to close the call tab.
- Dropped files never cross the bridge: the preload catches the drop and sends
  the file's path to main, which checks the extension, that it's a file, and its size.
- `wizard.dismissBubble()`, `wizard.vanished()`, `wizard.drag(phase, x, y)` are UI only.

Main → renderer:
- `wizard.onState(cb)` receives `{ mode, ... }`, where `mode` is one of
  `hidden | vanish | idle | analyzing | result | call-watch | call-alert`.
  `result` and `call-alert` carry an AnalyzeResponse as `result`.

Not built yet: `captureLast(seconds)` (system-audio capture). Until then no
audio is captured at all, and call-mode results are mocks (see
`app/src/main/analyzer.js`).

The renderer never talks to the network directly. All HTTP calls go through the
main process, which also holds the API key (never expose it to the renderer).

## Changelog
- 0.3: added `analyzers[]` and `pipeline_version`; `model.name` is the release name (no longer fixed to v2e); `/health` returns `"model": "mock"` and may include `load_error`; `flac` accepted.
- 0.2 (no bump): added the `/` landing page.
- 0.2: configurable base URL, bearer auth, `mock`/`weights_found` in /health, `bad_request`/`unauthorized` errors.
