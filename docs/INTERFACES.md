# INTERFACES: version 0.6 (draft)

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

**Install id.** The app sends `X-Dispel-Client: <uuid>` on every request: a random UUID
made on first launch, with no account behind it. It is optional on `/analyze` (curl,
tests) and required on `/history`. A value that isn't a UUID gives 400 `bad_request`.
When present, the server records the check's metadata (never audio or file names).

### GET /
A public HTML landing page ("Team Gemini") for people who open the server URL in a browser. Not part of the API; the app never calls it.

### GET /health
Returns `{"ok": true, "model": "<release name, e.g. v4p6>" | "hf:<repo id>" | "mock", "device": "cuda|cpu", "version": "0.6", "mock": bool, "weights_found": bool}`, plus `load_error` (string) if weights were found but could not be loaded.
`mock: true` means answers are demo data built from the canned example, not a real model result. The UI must show a "demo data" badge when it is true.
`"hf:<repo id>"` (e.g. `hf:mo-thecreator/Deepfake-audio-detection`) means our own release is not loaded and a
third-party open model from Hugging Face is answering instead (`server/app/hf_model.py`); `mock` is `false`.

### POST /analyze
Request: `multipart/form-data` with the field `file` (wav, flac, mp3, m4a, aac,
webm, ogg, oga, opus, or the audio track of mp4/mov). Optional form fields:
- `prior` (float between 0 and 1, default 0.5): the user's prior belief that the clip is synthetic.
- `source` (`file` | `call`, default `file`): what the clip is, for history.

`file` may be left out only when `source` is `call`, because no call audio is captured
yet. A mocked server answers such a request with demo data; a server with a real model
returns 400 `too_short`. Leaving out `file` for a `file` check gives 400 `bad_request`.

**Demo data (`mock: true`).** With no model loaded, the server answers every check with
the canned example turned into a random demo answer: about 70% `likely_synthetic` and
30% `likely_real` (probability, LLR, segments, analyzer contributions and caveats all
agree with the verdict, and `prior` is applied). The app's local mock uses the same mix.

The server:
- decodes the file with ffmpeg and converts it to 16 kHz mono
- splits the audio into segments
- scores each segment and the whole clip

Response 200:

| Field | Type | Meaning |
|---|---|---|
| `version` | string | `"0.6"` |
| `clip_id` | string | uuid |
| `duration_s` | float | clip length in seconds |
| `input` | object | `{ "sample_rate": int, "channels": int, "codec": str }` |
| `model` | object | `{ "name": "<release>/<profile>", "release": str }`, e.g. `{"name": "v4p6/app", "release": "2026-09-26"}`. With the Hugging Face stand-in: `{"name": "hf:<repo id>", "release": "<first 7 chars of the pinned commit>"}`. `/health` `model` is the release alone (`v4p6`); the profile is `app` on the server (`FUSION_PROFILE`) and `nsa` for the TSV, unless the release pins one (`profile_override` in `hearsay.json`; v5c pins `nn`, so both read `v5c/nn`) |
| `overall.llr` | float | natural-log likelihood ratio (synthetic vs real), capped at ±ln(100) |
| `overall.prior` | float | the prior that was used |
| `overall.probability` | float | sigmoid(llr + logit(prior)), between 0 and 1 |
| `overall.verdict` | enum | `likely_synthetic` \| `inconclusive` \| `likely_real` |
| `overall.fusion_bias` | float | optional; the fusion intercept, which belongs to no analyzer. `fusion_bias` + the `llr_contribution`s = the LLR before the cap |
| `segments[]` | array | each item is `{ "start_s", "end_s", "llr", "probability" }`: the neural detector alone on each 4 s window (up to 3) |
| `analyzers[]` | array | each item is `{ "name", "ran": bool, "finding": str, "llr_contribution": float, "ms": int }`: which techniques ran, what each found, and how much each moved the LLR (uncapped; with `overall.fusion_bias` they sum to the fused LLR before the cap). The Hugging Face stand-in reports one entry, `hf_detector`, with `fusion_bias` 0. Additive since release v5c: `"role": "vote" | "evidence"`; `evidence` analyzers ran and their `finding` is shown, but they carry `llr_contribution` 0 (profile `nn`: only `dl_detector` votes) |
| `manipulation` | object | `{ "type": str, "confidence": float }`. `type` is `"unknown"` until we have the NSA label schema. |
| `channel` | object | `{ "bandwidth_hz": int, "phone_like": bool, "note": str }` |
| `transcript` | string or null | optional |
| `limitations[]` | string[] | plain-language caveats to show in the report |
| `timing_ms` | int | processing time |
| `pipeline_version` | string | hearsay package version |
| `mock` | bool | `true` when this is demo data rather than a model result; the UI must say so |

The ML owner sets the verdict thresholds in `server/`, and they are recorded in
DECISIONS.md. **Placeholder until they're set:** `inconclusive` whenever
0.25 < probability < 0.75.

Errors: `{"error": "<code>", "message": str}` with status 400 (bad input), 401,
413 (too long or too large), or 500. Error codes: `decode_failed`, `too_short`
(< 1 s or empty), `too_long` (> 120 s or over the upload limit, 25 MB),
`bad_request` (e.g. `prior` outside 0..1, bad `source` or install id), `unauthorized`, `internal`.

### GET /history
Needs the bearer key and `X-Dispel-Client`. Query `limit` (1..100, default 20).
Returns this install's checks, newest first:
`{"client_id": str, "items": [{"ts": ISO-8601 UTC, "clip_id", "source", "probability", "verdict", "model", "mock": bool, "duration_s"}]}`.

## Electron IPC (preload bridge `window.wizard`, app in `app/`)
Changed in 0.2: the bridge now matches what the app does. The main process
makes every decision; the renderer only draws the state it's sent.

Renderer → main (each argument is validated in main):
- `wizard.pickFile()` opens a file dialog, then analyzes the chosen file.
- `wizard.autoCheck(yes)` answers the one-time "Check my calls automatically?"
  question (saved as `autoCheckCalls` in settings). Once it's yes, main checks
  each call as it starts.
- `wizard.listen()` ("Listen again", "Try again") checks the call now: main
  records the call app's audio output for 12 s (`app/native/callcapture.swift`,
  macOS 14.2+), uploads it as `POST /analyze` with `source=call`, and deletes it.
  Also in the tray menu and on ⌘⇧L during a call. Nothing is recorded without
  the opt-in or one of these.
- `wizard.endCall()` answers "Yes, hang up" on a flagged call. Main quits the
  call app politely (like Cmd+Q) through the callwatch helper. Browsers are never
  quit; for them the wizard asks the user to close the call tab.
- Dropped files never cross the bridge: the preload catches the drop and sends
  the file's path to main, which checks the extension, that it's a file, and its size.
- `wizard.notify()` is the "Notify trusted contact" / "Notify my manager"
  button on a flagged call: main texts the contact from Settings through the
  Mac's Messages app (or opens Settings if nobody is set up).
- The Settings window has its own bridge (`window.settings`: `get`, `save`,
  `sendTest`); main answers it only for that window.
- `wizard.learn(topic?)` opens Learn mode (`deepfake | scams | protect`, or the
  topic list). The lesson text lives in `app/src/renderer/lessons.js`.
- `wizard.contextMenu()` opens the right-click menu (built in main). It includes
  "Turn into a witch" / "Turn into a wizard".
- `wizard.dismissBubble()`, `wizard.vanished()`,
  `wizard.drag(phase, x, y)` are UI only.
- `wizard.blastFire(x, y)`: after "Yes, hang up" the wizard pulls out its wand
  and casts; this says the spell left the wand at (x, y), in page px. Main
  checks the point is inside the wizard window, draws the rest in a
  click-through window over the call (`renderer/obliterate.html`, its own
  preload `window.spell`), and quits the call app once the window is covered.
  If it never arrives, main hangs up after 3 s anyway. The callwatch helper's
  stdin command is now `end <app>` (the `app` it reported), so an app that
  let go of the mic for a moment still gets quit; if the app refuses or is
  still up 2.5 s later it gets SIGTERM. New `focus <app>` brings the call app
  to the front when "Yes, hang up" is clicked, so the spell hits a visible window.

Main → renderer:
- `wizard.onState(cb)` receives `{ mode, ... }`, where `mode` is one of
  `hidden | vanish | idle | greet | analyzing | result | learn | call-watch | call-listen | call-alert`.
  `greet` is `idle` plus a short hello (`text`) when summoned; main folds it
  away after about 5 s. `call-alert` with `prompt: "ending"` plays the hang-up spell.
  `result` and `call-alert` carry an AnalyzeResponse as `result`. `call-listen`
  carries `{ app, step: offer | listening | checking | result | error, seconds, result?, error? }`
  (`offer` is the one-time automatic-check question);
  a likely-synthetic result goes to `call-alert` instead.
- `wizard.onLook(cb)` receives `{ character: "wizard" | "witch", style: "2d" | "3d" }`
  when the user changes the look (right-click or tray menu: "Turn into a witch/wizard",
  "3D look"). The renderer plays the transition: a morph through the hat for a new
  character, a glowing sweep for 2D <-> 3D. The saved look also comes in the page URL
  (`wizard.html?character=witch&style=3d`) so the first frame is right. Main saves it
  in `<userData>/prefs.json`.

File and call checks go to the server set in `app/config.local.json` or
`DISPEL_SERVER_URL`, unless the tray's "Results from" picks a local mock (then
nothing is recorded or uploaded; see `app/src/main/analyzer.js`).

The renderer never talks to the network directly. All HTTP calls go through the
main process, which also holds the API key (never expose it to the renderer).

## Changelog
  `hidden | vanish | idle | greet | analyzing | result | learn | call-watch | call-listen | call-alert`.
  `greet` is `idle` plus a short hello (`text`) when summoned; main folds it
  away after about 5 s. `call-alert` with `prompt: "ending"` plays the hang-up spell.
  `result` and `call-alert` carry an AnalyzeResponse as `result`. `call-listen`
  carries `{ app, step: offer | listening | checking | result | error, seconds, result?, error? }`
  (`offer` is the one-time automatic-check question);
  a likely-synthetic result goes to `call-alert` instead.
- `wizard.onLook(cb)` receives `{ character: "wizard" | "witch", style: "2d" | "3d" }`
  when the user changes the look (right-click or tray menu: "Turn into a witch/wizard",
  "3D look"). The renderer plays the transition: a morph through the hat for a new
  character, a glowing sweep for 2D <-> 3D. The saved look also comes in the page URL
  (`wizard.html?character=witch&style=3d`) so the first frame is right. Main saves it
  in `<userData>/prefs.json`.
- 0.5: `POST /analyze` accepts `source=call` with no `file` (mocked server only; a real model gives `too_short`). Demo answers are now about 70% likely synthetic, 30% likely real, instead of always the same likely-synthetic example. The app sends call checks to the server too.
- 0.4 (no bump): documented that `model.name` is `<release>/<profile>` when the real pipeline runs (e.g. `v4p6/app`), and that `analyzers[]` lists all six techniques; added optional `overall.fusion_bias` (additive, clients may ignore it).
- 0.4: `X-Dispel-Client` install id, `source` form field, `mock` in the response, `GET /history`; accepts aac, oga, opus, mp4, mov. The app now calls the server for file checks.
- 0.3: added `analyzers[]` and `pipeline_version`; `model.name` is the release name (no longer fixed to v2e); `/health` returns `"model": "mock"` and may include `load_error`; `flac` accepted.
- 0.2 (no bump): added the `/` landing page.
- 0.2: configurable base URL, bearer auth, `mock`/`weights_found` in /health, `bad_request`/`unauthorized` errors.
