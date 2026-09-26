# STATUS: update this at the end of every task

## Owners
Fill this in at kickoff. One owner per directory. The owner approves changes to it.

| Person | GitHub | Owns | Current task | Branch | Blocked on |
|---|---|---|---|---|---|
| Akash (repo owner) | akashjainn | `ml/`, model loading in `server/` | NSA data profiling; score v0/v2/v2e on public ElevenLabs sets | | NSA metric and labels |
| Aniket | aniketgarg1 | TBD | | | |
| David | DavidPopesc | `app/` | Wizard app: menu-bar wizard, file check, call watch (mock results) | david-frontend | `server/` for real scores |
| Israel | Israel-Jauregui | `server/`, `infra/`, `docker/Dockerfile.server` | App ↔ server link (install id, history, file checks to Vultr) | israel/app-server-link | weights on the Vultr volume (server serves mock until then) |
| Teammate 4 | TBD | TBD (pitch, demo clips, Devpost) | | | |

## Current state
- Model: v3p (v3 + prosody fusion), see DECISIONS.md and ml/README.md. Calibration on new voices is a known gap.
- Live server: see the latest `infra` run summary or `terraform output base_url` (the URL changes when the server is replaced). Deploys to it are automatic on merge to `main`.
- Server: `/health`, `/analyze` and (0.4) `/history` run on Vultr with bearer auth. `hearsay/` is wired in, but no weights are on the volume yet, so every answer is the canned example with `mock: true`.
- App: `app/` runs on macOS. Menu-bar wizard; drop or pick a file to check it; detects calls (Zoom, FaceTime, Teams, Discord, Slack, browsers holding the mic) and highlights the call window purple when flagged. With a server configured (`app/config.local.json`), file checks go to it with an anonymous install id; otherwise, and for calls, scores are local mocks. No call audio is captured yet. Results are logged to `~/Library/Application Support/dispel-wizard/results.jsonl`.
- NSA submission: TSV writer + validator in `hearsay/cli.py`; metric known (minDCF, see CHALLENGE.md). Test audio delivery still unknown.

## Requests (changes needed outside your own directory)
- David → Akash: approve INTERFACES.md 0.2 (IPC section rewritten to match the app) and the call-watch decision in DECISIONS.md.
- Israel → David: review the `app/` part of israel/app-server-link (`src/main/analyzer.js`, new `src/main/config.js`, two lines in `main.js`).
- Israel → Akash, David: approve INTERFACES.md 0.4 and the install-id decision in DECISIONS.md.
- Akash: please review the AGENTS.md privacy-rule change (audio now goes to our Vultr server).
- Akash: put the v3p release on the Vultr volume (`/opt/dispel/models`) so the server stops serving mock data.

## Log (newest first; one line each: time · who · what · branch/PR)
- Sat 10:10 · Israel · server replaced via infra `replace_server` (#6 bootstrap + models volume; new URL `https://66-42-83-221.sslip.io`); `/health` no longer counts `lost+found` on the empty volume as weights (it failed the deploy health check) · israel/weights-found-fix (#9)
- Sat 09:40 · Israel · server: `X-Dispel-Client` install id, check history in SQLite + `GET /history`, `mock` flag in responses, more containers accepted; app: file checks POST to the configured server; INTERFACES 0.4; STATUS.md de-duplicated after the #7 merge · israel/app-server-link
- Sat · David · app: file drop works during calls too (drops were ignored while any app held the mic); flagged calls ask "end the call?" and Yes quits the call app (not browsers) · david-frontend
- Sat · David · app: sprites drawn like focus-wizard (one 80x120 canvas, shared origin), shown at 2x (160x240); cauldron recolored on load to an empty pot with no stew or gems · david-frontend
- Sat 03:14 · Israel · repo-driven server (docker/remote-deploy.sh, compose.prod.yml), persistent models volume (deploys refuse without it), replace_server guard; no settings push/Gemini yet · israel/repo-driven-server (#6)
- Sat 02:50 · Akash · hearsay/ pipeline (v3 + prosody fusion, TSV writer/validator), server wired to it (mock when no weights), CPU torch in Dockerfile.server, INTERFACES 0.3 · akash/hearsay-pipeline
- Sat 02:50 · David · app: fix file drop (handled in preload), wizard now sits inside the cauldron, purple call ring drawn outside the call window and tracks it every 80 ms · david-frontend
- Sat 02:25 · David · app: Electron menu-bar wizard, mock analyzer, results log, macOS call detection helper (`native/callwatch.swift`), purple call highlight; INTERFACES 0.2 · david-frontend
- Sat · David · CHALLENGE.md: add Discord post as source [D], correct the slides' 50/50 split to ~70/30, log [D]-vs-[I] conflicts (CSV, 0–100%, manipulation type) under Unknown · david-frontend
- Sat · Israel · landing page at /, deploy-on-merge workflow (SSH via temporary firewall rule), `deploy` user on the server · israel/deploy-workflow
- Sat · Israel · server/ API scaffold (mock), Vultr Terraform, INTERFACES 0.2, AGENTS/DECISIONS updated for Vultr hosting · israel/backend-infra-setup
- Fri 20:00 · Akash · repo initialized with docs only ·
