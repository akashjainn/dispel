# INTERFACES: version 0.3 (draft)

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

## Electron IPC (preload bridge `window.wizard`)
- `wizard.captureLast(seconds: number): Promise<ArrayBuffer>` records system
  audio. It only runs after the user clicks.
- `wizard.analyze(audio: ArrayBuffer | string /* file path */, prior?: number): Promise<AnalyzeResponse>`
- `wizard.health(): Promise<Health>`

The renderer never talks to the network directly. All HTTP calls go through the
main process, which also holds the API key (never expose it to the renderer).

## Changelog
- 0.3: added `analyzers[]` and `pipeline_version`; `model.name` is the release name (no longer fixed to v2e); `/health` returns `"model": "mock"` and may include `load_error`; `flac` accepted.
- 0.2 (no bump): added the `/` landing page.
- 0.2: configurable base URL, bearer auth, `mock`/`weights_found` in /health, `bad_request`/`unauthorized` errors.
